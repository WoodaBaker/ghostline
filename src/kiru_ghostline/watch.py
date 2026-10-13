"""Watch: continuous monitoring for drift and disorder signatures — STUB.

Intended shape: subscribe to a target's event stream, run lightweight
heuristic checks on every N events (cheap — not full batteries), and
raise alerts when a disorder signature crosses its policy threshold.
Full batteries run on schedule or on alert. See kiru#509.
"""


def watch_stream(target_spec: str):
    raise NotImplementedError("watch not yet implemented (kiru#509)")
