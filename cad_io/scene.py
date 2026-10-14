"""Формы для экспорта из сцены окна (AIS_InteractiveContext).

Без Qt. Отбираем показанные AIS_Shape для 3D- или 2D-экспорта;
оси, базовые плоскости, куб вида и точки пропускаются.
"""

from OCC.Core.AIS import (
    AIS_ListIteratorOfListOfInteractive,
    AIS_ListOfInteractive,
    Handle_AIS_Shape_DownCast,
)
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopoDS import TopoDS_Compound

from cad_io.strings import NOTHING_TO_EXPORT


def _has_face(shape):
    return TopExp_Explorer(shape, TopAbs_FACE).More()


def _has_edge(shape):
    return TopExp_Explorer(shape, TopAbs_EDGE).More()


def _collect_shapes(ais_list, kind):
    """Внутренний отбор форм с сохранением порядка объектов AIS."""
    shapes = []
    # В OCC 7.4.0 AIS_ListOfInteractive не поддерживает обычную итерацию __iter__.
    it = AIS_ListIteratorOfListOfInteractive(ais_list)

    while it.More():
        ais_shape = Handle_AIS_Shape_DownCast(it.Value())

        if ais_shape is not None:
            # Для пустого AIS_Shape обёртка pythonocc-core 7.4.0 может вернуть None из Shape().
            shape = ais_shape.Shape()

            if shape is not None and not shape.IsNull():
                has_face = _has_face(shape)

                if kind == "3d":
                    keep = has_face
                else:
                    keep = not has_face and _has_edge(shape)

                if keep:
                    if ais_shape.HasTransformation():
                        # Shape() может не учитывать перенос AIS-объекта; применяем его
                        # трансформацию, чтобы экспортировать геометрию в отображаемом месте.
                        shape = shape.Moved(
                            TopLoc_Location(ais_shape.Transformation())
                        )
                    shapes.append(shape)

        it.Next()

    return shapes


def shapes_from_ais_list(ais_list, kind="3d"):
    """Выбрать формы с гранями (3D) либо рёбрами без граней (2D)."""
    if kind not in ("3d", "2d"):
        raise ValueError("kind должен быть '3d' или '2d'")

    return _collect_shapes(ais_list, kind)


def export_kind_and_shapes(ais_list):
    """Определить тип экспорта и вернуть подходящие формы."""
    shapes_3d = shapes_from_ais_list(ais_list, kind="3d")

    if shapes_3d:
        return "3d", shapes_3d

    shapes_2d = shapes_from_ais_list(ais_list, kind="2d")

    if shapes_2d:
        return "2d", shapes_2d

    return None, []


def displayed_export_shapes(context):
    """Определить тип экспорта по отображаемым объектам окна."""
    ais_list = AIS_ListOfInteractive()
    context.DisplayedObjects(ais_list)

    return export_kind_and_shapes(ais_list)


def combine_shapes(shapes):
    """Одна форма — она сама; несколько — TopoDS_Compound.

    Пустой список — ValueError(NOTHING_TO_EXPORT).
    """
    shapes = list(shapes)
    if not shapes:
        raise ValueError(NOTHING_TO_EXPORT)
    if len(shapes) == 1:
        return shapes[0]
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound
