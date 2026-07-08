"""
Registry writer (app-side). The Glossary Generator authors the Registry at export
time; the standalone Policy Generator reads it to build the Data Identification
policy. This package intentionally contains only the writer — not the emit/drift
engine, which lives in the Policy Generator.
"""
from .model import Sensitivity
from .bridge import build_registry, build_and_save_registry, backfill_term_ids

__all__ = ["Sensitivity", "build_registry", "build_and_save_registry", "backfill_term_ids"]
