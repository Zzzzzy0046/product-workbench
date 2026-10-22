"""Portable, source-preserving competitor store-material collection."""

__version__ = "0.1.0"


def collect(payload: dict) -> dict:
    """Collect public store materials; no desktop tool or workbench required."""
    from competitor_collector.engine import collect as run

    return run(payload)
