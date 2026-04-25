"""Helpers to join GoldSrc log physical lines split mid-record (e.g. Rcon strings)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_scripts = Path(__file__).resolve().parents[1]
_module_path = _scripts / "hlstats_py" / "goldsrc_physical_lines.py"
_spec = importlib.util.spec_from_file_location("_hlstats_goldsrc_physical_lines", _module_path)
assert _spec and _spec.loader
_goldsrc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_goldsrc)
line_starts_new_goldsrc_record = _goldsrc.line_starts_new_goldsrc_record

__all__ = ["line_starts_new_goldsrc_record"]
