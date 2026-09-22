"""Context encoder, dynamics residual, and the behavioural supervision loss.

Architecture follows the manuscript: modality input projection, a temporal
transformer with L=10, d_z=32, three layers, four heads, width 128, mean pooling,
and a bounded six-state residual with per-state clipping to +/-0.5.

The residual predicts the next ESTIMATE, matching the state the MPC uses, and it is
predicted in BODY-frame canonical coordinates so that

    d_theta(T_g x, u, z) = L_g d_theta(x, u, z),  L_g = blkdiag(R_g, 1, R_g, 1)

holds by construction. Componentwise world-frame clipping would break that
equivariance, which is why the clip is applied in the body frame.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from . import config as C
from .scenarios import FEATURE_SCALE, N_FEAT_PER_STEP


def set_seed(s):
    torch.manual_seed(s)
    np.random.seed(s)


class ContextEncoder(nn.Module):
    """iota_k -> z_k. Invalid features are attention-masked and their availability
    flag stays visible as an input channel."""

    def __init__(self, n_feat=N_FEAT_PER_STEP, d_model=C.D_WIDTH, n_layers=C.N_LAYERS,
                 n_heads=C.N_HEADS, d_z=C.D_LATENT, L=C.HISTORY_L):
        super().__init__()
        self.inp = nn.Linear(n_feat, d_model)
        self.pos = nn.Parameter(torch.zeros(1, L + 1, d_model))
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=d_model,
            dropout=0.0, batch_first=True, norm_first=True,
            activation="gelu",
        )
        self.tf = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Sequential(nn.LayerNorm(d_model), nn.Linear(d_model, d_z))

    def forward(self, feats, mask):
        # feats (B, L+1, F), mask (B, L+1) with 1 = valid
        h = self.inp(feats) + self.pos
        pad = mask < 0.5
        # a fully padded row would make softmax NaN; keep the first slot alive
        pad = pad.clone()
        pad[:, 0] = False
        h = self.tf(h, src_key_padding_mask=pad)
        w = mask.clone()
        w[:, 0] = torch.clamp(w[:, 0], min=1e-6)
        h = (h * w.unsqueeze(-1)).sum(1) / w.sum(1, keepdim=True).clamp(min=1e-6)
        return self.head(h)


class DynamicsResidual(nn.Module):
    """d_theta(xhat, u, z) in body-frame coordinates, clipped to +/-0.5 per state."""

    def __init__(self, d_z=C.D_LATENT, hidden=C.D_WIDTH, clip=C.RESIDUAL_CLIP):
        super().__init__()
        # input: body-frame velocity (2), yaw rate (1), body-frame wrench (3), z
        self.net = nn.Sequential(
            nn.Linear(3 + 3 + d_z, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, 6),
        )
        self.clip = float(clip)
        # scale so the raw output is O(1) while the residual is physically small
        self.out_scale = nn.Parameter(torch.full((6,), 0.05), requires_grad=False)

    def forward(self, xb, ub, z):
        h = torch.cat([xb, ub, z], dim=-1)
        raw = self.net(h) * self.out_scale
        return torch.tanh(raw / self.clip) * self.clip


class ContextModel(nn.Module):
    """Encoder + residual.

    `constant_context=True` gives the trained constant-context baseline: the encoder
    is bypassed entirely and a single LEARNED context vector is shared by every
    transition. That answers "does inferring a CHANGING context help?", which
    deployment-time z=0 cannot answer, because z=0 is an untrained diagnostic rather
    than a retrained model.
    """

    def __init__(self, constant_context=False, feat_mask=None, **kw):
        super().__init__()
        self.enc = ContextEncoder(**kw.get("enc", {}))
        self.res = DynamicsResidual(**kw.get("res", {}))
        self.constant_context = bool(constant_context)
        self.const_z = nn.Parameter(torch.zeros(C.D_LATENT))
        # Sec 4/5.3 modality ablation. Registered as a BUFFER, so it travels inside the
        # checkpoint: a model trained without the diagnostic channels must not be
        # deployed with them, and an ablation whose mask lived only in the training
        # script would silently become the full model at evaluation time.
        from .scenarios import feature_mask as _fm
        m = _fm("full") if feat_mask is None else np.asarray(feat_mask,
                                                             dtype=np.float32)
        self.register_buffer("feat_mask", torch.tensor(m, dtype=torch.float32))
        self.feat_mask_name = "full" if feat_mask is None else "custom"

    def encode(self, feats, mask):
        if self.constant_context:
            return self.const_z.unsqueeze(0).expand(feats.shape[0], -1)
        # Masking is applied here, at the single entry point every caller uses, rather
        # than at each call site, so training and deployment cannot disagree.
        return self.enc(feats * self.feat_mask, mask)

    def residual(self, xb, ub, z):
        return self.res(xb, ub, z)

    def trainable(self):
        """The constant-context variant must not waste its optimiser budget on an
        encoder it never uses."""
        if self.constant_context:
            return list(self.res.parameters()) + [self.const_z]
        return list(self.parameters())


# ==========================================================================
# behavioural signature, manuscript Eq. (5)
# ==========================================================================
def probe_signature(probe_log, w_a=None, eps_G=1e-3, eps_exc=1e-4):
    """q_s from a probe branch.

    Combines body-frame command response (Ghat, chat) by regularised least squares
    of physical body-frame acceleration against the NOMINAL-EQUIVALENT TRANSMITTED
    wrench, estimator behaviour (innovation moments and availability), and the
    physical probe tracking cost J_p.

    The regressor choice is what makes the signature informative. Regressing the
    physical response against the already fault-reduced wrench, as an earlier
    version did, divides out the very impairment the signature is supposed to
    describe: Ghat then comes back near nominal whatever the actuation fault is
    doing. Physical ground truth on the left-hand side is allowed here because this
    is an offline probe branch, not a deployment input.

    Returns (q, ok, excitation). `ok` is False when the branch is under-excited, in
    which case the branch is omitted from the signature loss but its ordinary
    transitions remain available for one-step prediction.
    """
    a = probe_log
    xt = a["x_true"]
    u = a["u_nom_tx"]
    n = len(xt) - 1
    if n < 8:
        return None, False, 0.0

    # physical body-frame acceleration and body-frame wrench
    A_rows, b_rows = [], []
    for k in range(n):
        psi = xt[k, 4]
        c, s = np.cos(psi), np.sin(psi)
        R = np.array([[c, s], [-s, c]])  # world -> body
        acc_w = np.array([(xt[k + 1, 2] - xt[k, 2]) / C.TS,
                          (xt[k + 1, 3] - xt[k, 3]) / C.TS])
        alpha = (xt[k + 1, 5] - xt[k, 5]) / C.TS
        acc_b = R @ acc_w
        u_b = np.concatenate([R @ u[k, :2], [u[k, 2]]])
        A_rows.append(u_b)
        b_rows.append(np.array([acc_b[0], acc_b[1], alpha]))
    U = np.array(A_rows)          # (n, 3)
    Y = np.array(b_rows)          # (n, 3)

    # excitation test on the centred command Gramian
    Uc = U - U.mean(0, keepdims=True)
    gram = Uc.T @ Uc / max(n, 1)
    exc = float(np.linalg.eigvalsh(gram).min())
    ok = exc >= eps_exc

    # regularised least squares for [G | c]
    X = np.hstack([U, np.ones((n, 1))])
    reg = eps_G * np.eye(4)
    reg[3, 3] = eps_G * 1e-2
    theta = np.linalg.solve(X.T @ X + reg * n, X.T @ Y)   # (4, 3)
    Ghat = theta[:3].T.ravel()    # 9
    chat = theta[3]               # 3

    # estimator behaviour
    innov = a["innov"]
    valid = a["pose_valid"].astype(float)
    mu = innov.mean(0)
    covm = np.cov(innov.T) if len(innov) > 2 else np.zeros((2, 2))
    vech = np.array([covm[0, 0], covm[0, 1], covm[1, 1]])
    p_avail = np.array([valid.mean()])

    # physical probe tracking cost
    ref = a["ref_score"]
    Qp = np.array([1.0, 1.0, 0.1, 0.1, 0.5, 0.05])
    e = xt[:, :6] - ref[:, :6]
    e[:, 4] = (e[:, 4] + np.pi) % (2 * np.pi) - np.pi
    Jp = np.array([float(np.mean(np.sum(Qp * e ** 2, axis=1)))])

    q = np.concatenate([Ghat, chat, mu, vech, p_avail, Jp])
    return q.astype(np.float64), ok, exc


SIG_COMPONENT_WEIGHTS = np.concatenate([
    np.full(9, 1.0),    # Ghat
    np.full(3, 1.0),    # chat
    np.full(2, 0.5),    # innovation mean
    np.full(3, 0.5),    # innovation covariance
    np.full(1, 1.0),    # availability
    np.full(1, 0.5),    # probe tracking cost
])


def signature_distance(q1, q2, mu, sd, weights=SIG_COMPONENT_WEIGHTS):
    """d_q with fixed component weights on training-set standardised entries."""
    a = (q1 - mu) / sd
    b = (q2 - mu) / sd
    return float(np.sqrt(np.sum(weights * (a - b) ** 2) / weights.sum()))
