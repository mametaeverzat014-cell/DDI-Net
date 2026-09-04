"""Constants shared by the serving paths. Imports nothing.

This module exists because of a production bug worth not repeating: the request
handler pulled its tolerance from serving/parity.py, which imports pandas. In
the lean image — numpy only — every request died with ModuleNotFoundError
before any logic ran, while /api/health kept reporting the model as loaded.

Anything the request path needs at runtime belongs here, where it cannot drag a
dependency along with it.
"""

from __future__ import annotations

#: Probability-space tolerance against the frozen predictions. Measured, not
#: chosen: see serving/parity.py for the CPU-vs-GPU derivation.
PROB_TOLERANCE = 1e-5

#: What the target would be on identical hardware. Kept visible so a future
#: GPU deployment can tighten the assertion rather than inherit this one.
IDEAL_TOLERANCE = 1e-6

#: Modules the lean request path must never import. Asserted by a test that
#: runs the handler with these blocked, which is the check that was missing.
FORBIDDEN_AT_REQUEST_TIME = (
    "torch",
    "torch_geometric",
    "rdkit",
    "pandas",
    "sklearn",
)
