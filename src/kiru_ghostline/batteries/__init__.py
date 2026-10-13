from . import sycophancy  # noqa: F401 — registers the battery on import
from .base import Battery, BatteryResult
from .registry import all_batteries, disorders, get, register

__all__ = [
    "Battery",
    "BatteryResult",
    "all_batteries",
    "disorders",
    "get",
    "register",
]
