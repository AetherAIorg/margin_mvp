"""Domain packs: declarative specializations of the core ontology.

Only the neutral `widgets` example ships here. Downstream teams add their own.
"""

from pathlib import Path

from .loader import (
    BenchmarkDef,
    MetricDef,
    Pack,
    load_pack,
    load_pack_file,
    pack_from_dict,
)

WIDGETS_PACK_PATH = Path(__file__).parent / "widgets.yaml"

__all__ = [
    "BenchmarkDef",
    "MetricDef",
    "Pack",
    "load_pack",
    "load_pack_file",
    "pack_from_dict",
    "WIDGETS_PACK_PATH",
]
