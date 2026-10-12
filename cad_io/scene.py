"""Формы для экспорта из сцены окна (AIS_InteractiveContext).

Без Qt. Берём показанные AIS_Shape, у которых есть хотя бы одна грань:
рёбра эскиза, оси, базовые плоскости, куб вида и точки пропускаются.
"""

from OCC.Core.AIS import (
    AIS_ListIteratorOfListOfInteractive,
    AIS_ListOfInteractive,
    Handle_AIS_Shape_DownCast,
)
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopoDS import TopoDS_Compound

from cad_io.strings import NOTHING_TO_EXPORT


def _has_face(shape):
    return TopExp_Explorer(shape, TopAbs_FACE).More()


def shapes_from_ais_list(ais_list):
    """Список TopoDS_Shape из AIS_ListOfInteractive: только непустые AIS_Shape с гранями."""
    shapes = []
    # У AIS_ListOfInteractive в 7.4 нет __iter__: обходим итератором.
    it = AIS_ListIteratorOfListOfInteractive(ais_list)
    while it.More():
        ais_shape = Handle_AIS_Shape_DownCast(it.Value())
        if ais_shape is not None:
            # Для пустой формы обёртка 7.4 возвращает из Shape() None, а не пустую форму.
            shape = ais_shape.Shape()
            if shape is not None and not shape.IsNull() and _has_face(shape):
                # Shape() не учитывает перенос объекта (Context.SetLocation, сопряжения
                # в сборке): применяем преобразование, иначе деталь уйдёт на старое место.
                if ais_shape.HasTransformation():
                    shape = shape.Moved(TopLoc_Location(ais_shape.Transformation()))
                shapes.append(shape)
        it.Next()
    return shapes


def displayed_shapes(context):
    """Формы для экспорта из всех объектов, показанных в AIS_InteractiveContext."""
    ais_list = AIS_ListOfInteractive()
    context.DisplayedObjects(ais_list)
    return shapes_from_ais_list(ais_list)


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
