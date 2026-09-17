"""Process-pool helper.

Episodes are independent, so everything that sweeps parameters or seeds maps over a
pool. numpy inside each worker is pinned to one thread, otherwise BLAS oversubscribes
and the pool runs slower than serial.
"""
from __future__ import annotations

import os

_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def pin_threads(n=1):
    """Pin every BLAS/OpenMP layer AND torch to `n` threads.

    Setting the environment variables alone is not enough in a forked worker: torch
    and the BLAS backends read them at import time, and the worker inherits an
    already-imported torch through the fork, so the variables are ignored. Torch then
    runs its own intra-op pool per worker and the OpenMP threads busy-wait, which
    burns CPU without doing work - 6 workers were measured at >300% CPU each,
    spending roughly three quarters of their time spinning rather than simulating.
    torch.set_num_threads is a runtime call and does take effect.
    """
    for k in _ENV:
        os.environ[k] = str(n)
    # OpenBLAS sizes its pool when the shared library LOADS, which in a forked worker
    # already happened in the parent, so the env vars above are ignored and each
    # worker spins up 20 threads. threadpoolctl resizes the loaded pools at runtime,
    # which is the only thing that actually works here.
    try:
        import threadpoolctl
        threadpoolctl.threadpool_limits(n)
    except ImportError:
        pass
    try:
        import torch
        torch.set_num_threads(n)
    except (ImportError, RuntimeError):
        pass


def n_workers(reserve=2):
    return max(1, (os.cpu_count() or 2) - reserve)


def pmap(fn, items, workers=None, chunksize=1, desc=None, progress=True):
    """Ordered parallel map with a light progress line."""
    import multiprocessing as mp
    import sys

    import time

    items = list(items)
    n = len(items)
    workers = workers or min(n_workers(), max(1, n))
    tty = sys.stdout.isatty()
    t0 = time.time()

    def tick(i):
        """Progress that stays readable when stdout is a pipe."""
        if not (progress and desc):
            return
        last = i >= n
        if tty:
            sys.stdout.write(f"\r   {desc}: {i}/{n} ({workers}w)")
            if last:
                sys.stdout.write(f"  {time.time()-t0:.0f}s\n")
            sys.stdout.flush()
        elif last:
            print(f"   {desc}: {n}/{n} done in {time.time()-t0:.0f}s "
                  f"({workers} workers)")

    if workers == 1 or n <= 1:
        out = [fn(it) for it in items]
        tick(n)
        return out

    ctx = mp.get_context("fork")
    out = [None] * n
    with ctx.Pool(workers, initializer=pin_threads) as pool:
        for i, r in enumerate(pool.imap(fn, items, chunksize=chunksize)):
            out[i] = r
            if (i + 1) % max(1, n // 20) == 0:
                tick(i + 1)
    tick(n)
    return out
