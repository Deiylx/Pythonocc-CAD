# -*- coding: utf-8 -*-
"""Чтение и запись DXF R12 (2D, проекция XY, без HLR).

Использует только примитивы OCC, надёжно доступные в pythonocc 7.4.0.
Расширение, папку назначения и перезапись проверяет вызывающий код
(cad_io.export_paths.prepare_export_path).

Сигнатуры совпадают с cad_io.converters.step:
    write_dxf(shape, path) -> None
    read_dxf(path) -> TopoDS_Compound
"""

import math
import os

from OCC.Core.TopExp import topexp
from OCC.Core.TopTools import TopTools_IndexedMapOfShape
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.GeomAbs import GeomAbs_Line, GeomAbs_Circle
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Compound, topods_Edge

from cad_io.dxf import DxfWriter, bulge_to_arc, parse_file
from cad_io.dxf.entities import (
    DxfArc,
    DxfCircle,
    DxfLine,
    DxfPolyline,
)
from cad_io.strings import (
    ERR_DXF_EMPTY_SHAPE,
    ERR_DXF_FILE_NOT_FOUND,
    ERR_DXF_NO_SHAPES,
    ERR_DXF_READ_FAILED,
    ERR_DXF_WRITE_FAILED,
)


# Точность дискретизации «прочих» кривых (BSpline и т.п.).
DEFAULT_SAMPLES = 64

ZERO_TOL = 1e-12
TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Экспорт: TopoDS_Shape -> DXF
# ---------------------------------------------------------------------------

def _iter_edges(shape):
    """Yield unique topology edges in Open CASCADE map order."""
    edge_map = TopTools_IndexedMapOfShape()
    topexp.MapShapes(shape, TopAbs_EDGE, edge_map)
    for index in range(1, edge_map.Size() + 1):
        yield topods_Edge(edge_map.FindKey(index))


def _line_points_2d(curve):
    """Проекция отрезка на XY. None, если проекция — точка."""
    p1 = curve.Value(curve.FirstParameter())
    p2 = curve.Value(curve.LastParameter())
    if abs(p1.X() - p2.X()) < ZERO_TOL and abs(p1.Y() - p2.Y()) < ZERO_TOL:
        return None
    return (p1.X(), p1.Y()), (p2.X(), p2.Y())


def _arc_params(curve):
    """Параметры окружности/дуги для DXF или None, если она не в плоскости XY.

    Устойчиво к ориентации оси: работаем с реальными точками, не с
    параметрами. Возвращает (cx, cy, r, a1_deg, a2_deg, is_full).
    """
    circ = curve.Circle()
    axis = circ.Axis().Direction()

    if abs(axis.X()) > 1e-9 or abs(axis.Y()) > 1e-9:
        return None
    if abs(abs(axis.Z()) - 1.0) > 1e-9:
        return None

    center = circ.Location()
    radius = circ.Radius()
    if radius <= 0.0:
        return None

    u1 = curve.FirstParameter()
    u2 = curve.LastParameter()
    span = abs(u2 - u1)
    if abs(span - TWO_PI) < 1e-7:
        return center.X(), center.Y(), radius, 0.0, 0.0, True

    p1 = curve.Value(u1)
    p2 = curve.Value(u2)
    a1 = math.degrees(math.atan2(p1.Y() - center.Y(), p1.X() - center.X())) % 360.0
    a2 = math.degrees(math.atan2(p2.Y() - center.Y(), p2.X() - center.X())) % 360.0

    if axis.Z() < 0.0:
        a1, a2 = a2, a1

    return center.X(), center.Y(), radius, a1, a2, False


def _sample_curve(curve, n=DEFAULT_SAMPLES):
    """Равномерно по параметру: n точек. Для BSpline и прочих кривых."""
    u1 = curve.FirstParameter()
    u2 = curve.LastParameter()
    if u2 <= u1 or n < 2:
        return []
    step = (u2 - u1) / float(n - 1)
    pts = []
    for i in range(n):
        p = curve.Value(u1 + step * i)
        pts.append((p.X(), p.Y()))
    return pts


def write_dxf(shape, path):
    """Записать TopoDS_Shape в DXF R12 (проекция XY, слой 0).

    ValueError — форма пустая или в ней нет рёбер для экспорта.
    OSError — не удалось записать файл.
    """
    if shape is None or shape.IsNull():
        raise ValueError(ERR_DXF_EMPTY_SHAPE)

    writer = DxfWriter()
    count = 0

    for edge in _iter_edges(shape):
        curve = BRepAdaptor_Curve(edge)
        ctype = curve.GetType()

        if ctype == GeomAbs_Line:
            pts = _line_points_2d(curve)
            if pts is None:
                continue
            (x1, y1), (x2, y2) = pts
            writer.add_line(x1, y1, x2, y2)
            count += 1

        elif ctype == GeomAbs_Circle:
            params = _arc_params(curve)
            if params is None:
                pts = _sample_curve(curve)
                if len(pts) >= 2:
                    writer.add_polyline(pts, closed=False)
                    count += 1
                continue
            cx, cy, r, a1, a2, full = params
            if full:
                writer.add_circle(cx, cy, r)
            else:
                writer.add_arc(cx, cy, r, a1, a2)
            count += 1

        else:
            pts = _sample_curve(curve)
            if len(pts) >= 2:
                writer.add_polyline(pts, closed=False)
                count += 1

    if count == 0:
        raise ValueError(ERR_DXF_EMPTY_SHAPE)

    try:
        writer.save(path)
    except (IOError, OSError) as err:
        raise OSError(ERR_DXF_WRITE_FAILED.format(path=path)) from err

# ---------------------------------------------------------------------------
# Импорт: DXF -> TopoDS_Compound
# ---------------------------------------------------------------------------

def _make_line(p1, p2):
    """Создать ребро-отрезок; вырожденные отрезки пропустить."""
    try:
        builder = BRepBuilderAPI_MakeEdge(
            gp_Pnt(p1[0], p1[1], 0.0),
            gp_Pnt(p2[0], p2[1], 0.0),
        )
    except Exception:
        return None
    if not builder.IsDone():
        return None
    return builder.Edge()


def _make_circle(center, radius):
    ax = gp_Ax2(gp_Pnt(center[0], center[1], 0.0), gp_Dir(0.0, 0.0, 1.0))
    circ = gp_Circ(ax, radius)
    builder = BRepBuilderAPI_MakeEdge(circ)
    if not builder.IsDone():
        return None
    return builder.Edge()


def _make_arc(center, radius, start_deg, end_deg, ccw=True):
    """Создать дугу из DXF-углов; OCC получает возрастающий диапазон параметров."""
    ax = gp_Ax2(gp_Pnt(center[0], center[1], 0.0), gp_Dir(0.0, 0.0, 1.0))
    circ = gp_Circ(ax, radius)
    # Normalize before converting: adding 2*pi may not change huge floats.
    # Equal angles stay equal; the existing loops keep full-circle behavior.
    start_deg = start_deg % 360.0
    end_deg = end_deg % 360.0
    u1 = math.radians(start_deg)
    u2 = math.radians(end_deg)

    reverse_edge = False
    if ccw:
        while u2 <= u1:
            u2 += TWO_PI
        first, last = u1, u2
    else:
        # Сначала строим дугу CCW от исходного конца к исходному началу,
        # затем разворачиваем ребро, чтобы сохранить направление исходной дуги.
        while u1 <= u2:
            u1 += TWO_PI
        first, last = u2, u1
        reverse_edge = True

    if abs(last - first) < ZERO_TOL:
        return _make_circle(center, radius)

    try:
        builder = BRepBuilderAPI_MakeEdge(circ, first, last)
    except Exception:
        return None
    if not builder.IsDone():
        return None
    edge = builder.Edge()
    if reverse_edge:
        edge.Reverse()
    return edge


def _polyline_edges(points, bulges, closed):
    """Сегменты полилинии, включая дуги по bulge."""
    edges = []
    n = len(points)
    if n < 2:
        return edges

    seq = list(zip(points, bulges))
    if closed:
        seq.append(seq[0])

    for i in range(len(seq) - 1):
        p1 = seq[i][0]
        b1 = seq[i][1]
        p2 = seq[i + 1][0]

        e = None
        if b1 is not None and abs(b1) > ZERO_TOL:
            arc = bulge_to_arc(p1, p2, b1)
            if arc is not None:
                cx, cy, r, a1, a2, ccw = arc
                e = _make_arc((cx, cy), r, a1, a2, ccw=ccw)
        if e is None:
            e = _make_line(p1, p2)
        if e is not None:
            edges.append(e)
    return edges


def read_dxf(path):
    """Прочитать DXF и вернуть TopoDS_Compound с рёбрами.

    FileNotFoundError — файла нет.
    ValueError — файл пустой или в нём нет поддерживаемых примитивов.
    """
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(ERR_DXF_FILE_NOT_FOUND.format(path=path))

    try:
        entities = parse_file(path)
    except ValueError as err:
        raise ValueError(
            ERR_DXF_READ_FAILED.format(path=path, error=err)
        ) from err

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    count = 0
    for ent in entities:
        if isinstance(ent, DxfLine):
            e = _make_line(ent.start, ent.end)
            if e is not None:
                builder.Add(compound, e)
                count += 1

        elif isinstance(ent, DxfCircle):
            e = _make_circle(ent.center, ent.radius)
            if e is not None:
                builder.Add(compound, e)
                count += 1

        elif isinstance(ent, DxfArc):
            e = _make_arc(
                ent.center, ent.radius, ent.start_angle, ent.end_angle,
                ccw=True,
            )
            if e is not None:
                builder.Add(compound, e)
                count += 1

        elif isinstance(ent, DxfPolyline):
            for e in _polyline_edges(ent.points, ent.bulges, ent.closed):
                builder.Add(compound, e)
                count += 1

    if count == 0:
        raise ValueError(ERR_DXF_NO_SHAPES.format(path=path))

    return compound
