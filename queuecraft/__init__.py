"""QueueCraft: reproducible static job-shop scheduling experiments."""

import os

# Bound this process's numerical-library parallelism on a small local CPU.
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

__version__ = "0.1.0"

