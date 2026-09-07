"""Conformance checks for axis interaction in OpenType COLR v1 variable fonts."""
from .check import check_font, Report, Finding  # noqa: F401
from .store import Store, var_stores  # noqa: F401

__version__ = "0.2.0"
__all__ = ["check_font", "Report", "Finding", "Store", "var_stores"]
