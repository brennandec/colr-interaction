"""Conformance checks for axis interaction in OpenType COLR v1 variable fonts."""
from .check import check_font, Report, Finding, interaction_regions  # noqa: F401

__version__ = "0.1.0"
__all__ = ["check_font", "Report", "Finding", "interaction_regions"]
