"""Чистый модуль DXF R12 (AC1009) ASCII.

Здесь нет ни OCC, ни Qt — только текст DXF: чтение, запись, примитивы.
Конвертер OCC <-> DXF живёт в cad_io.converters.dxf.
"""

from cad_io.dxf.entities import (
    DxfArc,
    DxfCircle,
    DxfLine,
    DxfPolyline,
    bulge_to_arc,
    fmt_number,
)
from cad_io.dxf.parser import parse, parse_file
from cad_io.dxf.writer import DxfWriter

__all__ = [
    "DxfArc",
    "DxfCircle",
    "DxfLine",
    "DxfPolyline",
    "DxfWriter",
    "bulge_to_arc",
    "fmt_number",
    "parse",
    "parse_file",
]
