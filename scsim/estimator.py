"""Estimator surrogate (build_scSim.md Sec 8).

This is deliberately NOT a good estimator. Its lag is the dominant contributor to
the measured error and therefore to the certificate's estimation envelope, so it is
reproduced exactly as specified:

  1 VO surrogate for ROVIO, modelled at the MEASUREMENT level: pose plus noise, bias
    drift, and dropout. No absolute reference after initialisation.
  2 One-shot alignment at t0 against ground truth, then never again.
  3 The controller's own filter layer, which matters most:
      - position LPF, hardcoded tau = 0.5 s (the declared 0.4 is dead code)
      - yaw LPF, tau = 0.5 s, on the sin/cos pair
      - velocity  = 0.8*d(LPF pos)/dt + 0.2*VO twist, clipped to +/-2 m/s
      - yaw rate  = 0.7*d(filtered yaw)/dt + 0.3*VO angular.z, clipped to +/-2 rad/s

The IMU does NOT enter the controller's state estimate at all: the callback
subscribes to the wrong topic and never fires. There is no IMU channel here.

Perception degradation is modelled HERE, at the measurement/estimator level. The
occlusion was physical tape on the lens with no code path, no logged onset and no
logged duration, so it is described as a measurement-level perception-degradation
experiment and never as reproduced visual occlusion.
"""
from __future__ import annotations

import numpy as np

from . import config as C
from .plant import wrap_pi


class VOSurrogate:
    """Monocular VO measurement model: noise, bias random walk, dropout blocks."""

    def __init__(self, rng, mode="healthy", override=None):
        self.rng = rng
        self.mode = mode
        self.bias = np.zeros(2)
        self.yaw_bias = 0.0
        self.degraded = False
        self._dropout_left = 0
        self._override = dict(override) if override else None
        self._cfg = self._config(mode)
        if self._override:
            self._cfg.update(self._override)
        self._healthy = self._config("healthy")
        if self._override and mode == "healthy":
            self._healthy.update(self._override)

    @staticmethod
    def _config(mode):
        """Degradation levels. Fitted to the Sec 7 envelopes, not measured from ROVIO.

        'occluded' targets the V2 zero-context band, |dx| p95 0.79-4.86 m: a large
        band because it spans runs, so the surrogate reproduces its scale rather
        than any single run.
        """
        if mode not in C.VO_PROFILES:
            raise ValueError(f"unknown perception mode {mode!r}")
        return dict(C.VO_PROFILES[mode])

    def set_degraded(self, on):
        self.degraded = bool(on)

    def _active_cfg(self):
        """Before onset the vehicle is healthy; the degradation is a step at onset."""
        if self.mode == "healthy" or not self.degraded:
            return self._healthy
        return self._cfg

    def observe(self, x_true, k):
        cfg = self._active_cfg()
        dt = C.TS
        # bias random walk, in m per sqrt(s)
        self.bias = self.bias + cfg["bias_rw"] * np.sqrt(dt) * self.rng.standard_normal(2)
        self.yaw_bias += cfg["yaw_bias_rw"] * np.sqrt(dt) * self.rng.standard_normal()

        # dropout blocks
        if self._dropout_left > 0:
            self._dropout_left -= 1
            return {"valid": False}
        if self.rng.random() < cfg["dropout_p"]:
            lo, hi = cfg["dropout_len"]
            self._dropout_left = int(self.rng.integers(lo, hi + 1))
            return {"valid": False}

        # monocular scale error, a known VO failure mode; the two camera
        # calibrations in the tree disagree by ~16% in focal length
        s = 1.0 + cfg["scale_err"]
        pos = x_true[:2] * s + self.bias + cfg["pos_noise"] * self.rng.standard_normal(2)
        yaw = wrap_pi(x_true[4] + self.yaw_bias
                      + cfg["yaw_noise"] * self.rng.standard_normal())
        twist = x_true[2:4] * s + cfg["twist_noise"] * self.rng.standard_normal(2)
        omega = x_true[5] + cfg["yaw_noise"] * self.rng.standard_normal()
        return {"valid": True, "pos": pos, "yaw": yaw, "twist": twist, "omega": omega}


class EstimatorStack:
    """The controller's own filter layer, plus the one-shot t0 alignment."""

    def __init__(self):
        self.p_lpf = None
        self.sc_lpf = None  # (sin, cos) pair
        self.p_prev = None
        self.yaw_prev = None
        self.v = np.zeros(2)
        self.r = 0.0
        self.offset = np.zeros(2)
        self.yaw_offset = 0.0
        self._t_since_valid = 0.0
        self._last_accepted_pos = None
        self._last_accepted_yaw = None
        self.n_gate_reject = 0
        # modality innovation zeta^o: the observed pose minus the filter's prior.
        # This is a controller-visible quantity and is one of the encoder inputs.
        self.innov = np.zeros(2)

    def align(self, x_true):
        """One-shot alignment at t0 against ground truth, then never again.

        This anchors the origin and initial heading, so drift is measured relative
        to a truth-defined origin. It also means the system is not fully Vicon-free,
        which should be stated in the paper.
        """
        self._align_target = x_true[:2].copy()
        self._align_yaw = float(x_true[4])
        self._aligned = False

    def update(self, obs, dt):
        if not obs.get("valid", False):
            # the `hold` branch re-assigns an already-filtered state, so it is
            # functionally a no-op and the `predict` branch is unreachable. On a
            # missing pose the filter simply does not update and the LPF continues
            # from its last value.
            self._t_since_valid += dt
            return self.state()

        pos = np.asarray(obs["pos"], dtype=float)
        yaw = float(obs["yaw"])

        if not getattr(self, "_aligned", False):
            # apply the one-shot offset so t0 matches ground truth
            self.offset = self._align_target - pos
            self.yaw_offset = wrap_pi(self._align_yaw - yaw)
            self._aligned = True

        pos = pos + self.offset
        yaw = wrap_pi(yaw + self.yaw_offset)

        # ---- gating: jump > 0.5 m within < 0.2 s rejected, previous retained ----
        if self._last_accepted_pos is not None and self._t_since_valid < C.GATE_DT:
            if np.linalg.norm(pos - self._last_accepted_pos) > C.GATE_POS_JUMP:
                self.n_gate_reject += 1
                self._t_since_valid += dt
                return self.state()
            if abs(wrap_pi(yaw - self._last_accepted_yaw)) > C.GATE_YAW_JUMP:
                self.n_gate_reject += 1
                self._t_since_valid += dt
                return self.state()
        self._last_accepted_pos = pos.copy()
        self._last_accepted_yaw = yaw

        # ---- position LPF, tau = 0.5 s ----
        alpha_p = 1.0 - np.exp(-dt / C.POS_LPF_TAU)
        if self.p_lpf is None:
            self.p_lpf = pos.copy()
            self.innov = np.zeros(2)
        else:
            self.innov = pos - self.p_lpf   # innovation before the update
            self.p_lpf = self.p_lpf + alpha_p * (pos - self.p_lpf)

        # ---- yaw LPF on the sin/cos pair, tau = 0.5 s ----
        alpha_y = 1.0 - np.exp(-dt / C.YAW_LPF_TAU)
        sc = np.array([np.sin(yaw), np.cos(yaw)])
        if self.sc_lpf is None:
            self.sc_lpf = sc.copy()
        else:
            self.sc_lpf = self.sc_lpf + alpha_y * (sc - self.sc_lpf)
        yaw_f = np.arctan2(self.sc_lpf[0], self.sc_lpf[1])

        # ---- velocity: 0.8 * d(LPF pos)/dt + 0.2 * VO twist ----
        fd_dt = max(dt + self._t_since_valid, C.MIN_FD_DT)
        if self.p_prev is not None:
            fd = (self.p_lpf - self.p_prev) / fd_dt
            fd = np.clip(fd, -C.VEL_CLIP, C.VEL_CLIP)
            twist = np.asarray(obs.get("twist", np.zeros(2)), dtype=float)
            self.v = C.VEL_BLEND_LPF * fd + (1.0 - C.VEL_BLEND_LPF) * twist
            self.v = np.clip(self.v, -C.VEL_CLIP, C.VEL_CLIP)
        self.p_prev = self.p_lpf.copy()

        # ---- yaw rate: 0.7 * d(filtered yaw)/dt + 0.3 * VO angular.z ----
        if self.yaw_prev is not None:
            fd_r = wrap_pi(yaw_f - self.yaw_prev) / fd_dt
            fd_r = np.clip(fd_r, -C.YAWRATE_CLIP, C.YAWRATE_CLIP)
            self.r = (C.YAWRATE_BLEND_LPF * fd_r
                      + (1.0 - C.YAWRATE_BLEND_LPF) * float(obs.get("omega", 0.0)))
            self.r = float(np.clip(self.r, -C.YAWRATE_CLIP, C.YAWRATE_CLIP))
        self.yaw_prev = yaw_f

        self._t_since_valid = 0.0
        self._yaw_f = yaw_f
        return self.state()

    def state(self):
        p = np.zeros(2) if self.p_lpf is None else self.p_lpf
        yaw = getattr(self, "_yaw_f", 0.0)
        return np.array([p[0], p[1], self.v[0], self.v[1], yaw, self.r])
