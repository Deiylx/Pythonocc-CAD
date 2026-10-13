# -*- coding: utf-8 -*-
"""Чтение DXF R12.

Поддерживаются LINE, CIRCLE, ARC, LWPOLYLINE и POLYLINE/VERTEX.
Неподдерживаемые типы сущностей пропускаются. Совместимо с Python 3.7.
"""

import io
import math

from cad_io.dxf.entities import (
    DxfArc,
    DxfCircle,
    DxfLine,
    DxfPolyline,
)


_MISSING = object()


def _tokenize(text):
    """Разбить текст DXF на пары (code: int, value: str)."""
    if text.startswith("\ufeff"):
        text = text[1:]
    # Не использовать splitlines(): он также делит по form-feed и другим
    # управляющим символам, которые могут встречаться внутри текстовых полей.
    lines = [line.rstrip("\r") for line in text.split("\n")]
    i = 0
    while i < len(lines):
        code_line = lines[i].strip()
        i += 1
        if not code_line:
            continue
        if i >= len(lines):
            break
        value = lines[i]
        i += 1
        try:
            code = int(code_line)
        except ValueError:
            # Поведение для повреждённой строки кода сохраняем прежним:
            # нечисловая строка кода пропускается.
            continue
        yield code, value


def _first(data, code, default=None):
    for current_code, value in data:
        if current_code == code:
            return value
    return default


def _parse_float(value, description):
    """Прочитать конечное число или явно сообщить об ошибке данных."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise ValueError(
            "DXF: некорректное числовое значение для {}: {!r}".format(
                description, value
            )
        ) from err

    if not math.isfinite(number):
        raise ValueError(
            "DXF: значение для {} должно быть конечным числом: {!r}".format(
                description, value
            )
        )
    return number


def _field_float(data, code, entity, field, default=_MISSING):
    """Прочитать числовое поле сущности; default применяется только к пропуску."""
    value = _first(data, code, _MISSING)
    description = "{} {}, group code {}".format(entity, field, code)

    if value is _MISSING:
        if default is not _MISSING:
            return default
        raise ValueError("DXF: отсутствует обязательное поле {}".format(description))

    return _parse_float(value, description)


def _closed_flag(data, entity):
    flags = _field_float(data, 70, entity, "flags", default=0.0)
    if not flags.is_integer():
        raise ValueError(
            "DXF: поле {} flags (group code 70) должно быть целым числом".format(
                entity
            )
        )
    return bool(int(flags) & 1)


def _parse_lwpolyline_verts(data):
    """Собрать точки и bulge из пар кодов LWPOLYLINE."""
    points = []
    bulges = []
    pending_x = None

    for code, value in data:
        if code == 10:
            if pending_x is not None:
                raise ValueError(
                    "DXF: LWPOLYLINE: координата X без следующей координаты Y"
                )
            pending_x = _parse_float(value, "LWPOLYLINE coordinate X (code 10)")
        elif code == 20:
            if pending_x is None:
                raise ValueError(
                    "DXF: LWPOLYLINE: координата Y без предшествующей координаты X"
                )
            y = _parse_float(value, "LWPOLYLINE coordinate Y (code 20)")
            points.append((pending_x, y))
            bulges.append(0.0)
            pending_x = None
        elif code == 42:
            # Отсутствие code 42 допустимо и означает прямой сегмент (bulge=0).
            # Но если поле присутствует, его значение обязано быть числом.
            bulge = _parse_float(value, "LWPOLYLINE bulge (code 42)")
            if not bulges:
                raise ValueError(
                    "DXF: LWPOLYLINE: bulge задан до первой вершины"
                )
            bulges[-1] = bulge

    if pending_x is not None:
        raise ValueError(
            "DXF: LWPOLYLINE: отсутствует координата Y для последней вершины"
        )

    return points, bulges


def _build_entity(etype, data):
    """Создать поддерживаемую DXF-сущность или вернуть None для неподдерживаемой."""
    layer = _first(data, 8, "0") or "0"

    if etype == "LINE":
        x1 = _field_float(data, 10, etype, "start X")
        y1 = _field_float(data, 20, etype, "start Y")
        x2 = _field_float(data, 11, etype, "end X")
        y2 = _field_float(data, 21, etype, "end Y")
        return DxfLine((x1, y1), (x2, y2), layer=layer)

    if etype == "CIRCLE":
        cx = _field_float(data, 10, etype, "center X")
        cy = _field_float(data, 20, etype, "center Y")
        radius = _field_float(data, 40, etype, "radius")
        if radius <= 0.0:
            raise ValueError("DXF: CIRCLE radius (group code 40) должен быть больше нуля")
        return DxfCircle((cx, cy), radius, layer=layer)

    if etype == "ARC":
        cx = _field_float(data, 10, etype, "center X")
        cy = _field_float(data, 20, etype, "center Y")
        radius = _field_float(data, 40, etype, "radius")
        start_angle = _field_float(data, 50, etype, "start angle")
        end_angle = _field_float(data, 51, etype, "end angle")
        if radius <= 0.0:
            raise ValueError("DXF: ARC radius (group code 40) должен быть больше нуля")
        return DxfArc(
            (cx, cy), radius, start_angle, end_angle, layer=layer
        )

    if etype == "LWPOLYLINE":
        points, bulges = _parse_lwpolyline_verts(data)
        if not points:
            return None
        closed = _closed_flag(data, etype)
        return DxfPolyline(
            points, closed=closed, layer=layer, bulges=bulges
        )

    return None


def _collect_polyline_r12(pairs, start_idx):
    """Собрать POLYLINE R12 (POLYLINE + VERTEX* + SEQEND)."""
    n = len(pairs)
    header = []
    i = start_idx + 1
    while i < n and pairs[i][0] != 0:
        header.append(pairs[i])
        i += 1

    layer = _first(header, 8, "0") or "0"
    closed = _closed_flag(header, "POLYLINE")

    points = []
    bulges = []
    while i < n:
        code, value = pairs[i]
        if code == 0 and value.strip() == "VERTEX":
            vertex_data = []
            i += 1
            while i < n and pairs[i][0] != 0:
                vertex_data.append(pairs[i])
                i += 1

            x = _field_float(vertex_data, 10, "VERTEX", "X")
            y = _field_float(vertex_data, 20, "VERTEX", "Y")
            bulge = _field_float(
                vertex_data, 42, "VERTEX", "bulge", default=0.0
            )
            points.append((x, y))
            bulges.append(bulge)
            continue

        if code == 0 and value.strip() == "SEQEND":
            i += 1
            while i < n and pairs[i][0] != 0:
                i += 1
            break
        break

    if not points:
        return None, i
    return DxfPolyline(points, closed=closed, layer=layer, bulges=bulges), i


def parse(text):
    """Разобрать DXF-текст и вернуть сущности в порядке появления."""
    pairs = list(_tokenize(text))
    entities = []
    in_entities = False
    i = 0
    n = len(pairs)

    while i < n:
        code, value = pairs[i]
        if code != 0:
            i += 1
            continue

        etype = value.strip()

        if etype == "SECTION":
            if i + 1 < n and pairs[i + 1][0] == 2:
                in_entities = pairs[i + 1][1].strip() == "ENTITIES"
                i += 2
                continue
            i += 1
            continue

        if etype == "ENDSEC":
            in_entities = False
            i += 1
            continue

        if etype == "EOF":
            break

        if not in_entities:
            i += 1
            continue

        data = []
        j = i + 1
        while j < n and pairs[j][0] != 0:
            data.append(pairs[j])
            j += 1

        if etype == "POLYLINE":
            polyline, j = _collect_polyline_r12(pairs, i)
            if polyline is not None:
                entities.append(polyline)
            i = j
            continue

        entity = _build_entity(etype, data)
        if entity is not None:
            entities.append(entity)
        i = j

    return entities


def parse_file(path):
    """Прочитать DXF-файл как UTF-8, автоматически сняв BOM при наличии."""
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as source:
        return parse(source.read())
