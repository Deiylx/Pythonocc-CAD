"""cad_io — импорт/экспорт форматов для BrepCAD.

Пакет назван cad_io, а не io: имя io занято стандартным модулем Python.
Окна Qt здесь не импортируются — они только в cad_io.ui_bridge.
"""

from cad_io.registry import FormatSpec, Registry, REGISTRY

__all__ = ["FormatSpec", "Registry", "REGISTRY"]
