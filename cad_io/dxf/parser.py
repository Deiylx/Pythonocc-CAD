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

from cad_io.strings import (
    DXF_FIELD,
    DXF_FIELD_NAMES,
    ERR_DXF_BAD_NUMBER,
    ERR_DXF_LWPOLYLINE_BULGE_FIRST,
    ERR_DXF_LWPOLYLINE_NO_LAST_Y,
    ERR_DXF_LWPOLYLINE_X_WITHOUT_Y,
    ERR_DXF_LWPOLYLINE_Y_WITHOUT_X,
    ERR_DXF_MISSING_FIELD,
    ERR_DXF_NOT_FINITE,
    ERR_DXF_NOT_INTEGER,
    ERR_DXF_NOT_POSITIVE,
    ERR_DXF_UNSUPPORTED_OCS,
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
            ERR_DXF_BAD_NUMBER.format(field=description, value=value)
        ) from err

    if not math.isfinite(number):
        raise ValueError(
            ERR_DXF_NOT_FINITE.format(field=description, value=value)
        )
    return number


def _field_float(data, code, entity, field, default=_MISSING):
    """Прочитать числовое поле сущности; default применяется только к пропуску."""
    value = _first(data, code, _MISSING)
    description = DXF_FIELD.format(
        entity=entity,
        name=DXF_FIELD_NAMES[field],
        code=code,
    )

    if value is _MISSING:
        if default is not _MISSING:
            return default
        raise ValueError(ERR_DXF_MISSING_FIELD.format(field=description))

    return _parse_float(value, description)


def _closed_flag(data, entity):
    flags = _field_float(data, 70, entity, "flags", default=0.0)
    if not flags.is_integer():
        raise ValueError(
            ERR_DXF_NOT_INTEGER.format(
                field=DXF_FIELD.format(
                    entity=entity,
                    name=DXF_FIELD_NAMES["flags"],
                    code=70,
                )
            )
        )
    return bool(int(flags) & 1)


def _validate_xy_ocs(data, entity):
    """Отклонить сущности, нормаль OCS которых не направлена вдоль оси +Z."""
    nx = _field_float(data, 210, entity, "normal_x", default=0.0)
    ny = _field_float(data, 220, entity, "normal_y", default=0.0)
    nz = _field_float(data, 230, entity, "normal_z", default=1.0)
    normal = (nx, ny, nz)
    if abs(nx) > 1e-9 or abs(ny) > 1e-9 or abs(nz - 1.0) > 1e-9:
        raise ValueError(
            ERR_DXF_UNSUPPORTED_OCS.format(entity=entity, normal=normal)
        )


def _parse_lwpolyline_verts(data):
    """Собрать точки и bulge из пар кодов LWPOLYLINE."""
    points = []
    bulges = []
    pending_x = None

    for code, value in data:
        if code == 10:
            if pending_x is not None:
                raise ValueError(ERR_DXF_LWPOLYLINE_X_WITHOUT_Y)
            pending_x = _parse_float(
                value,
                DXF_FIELD.format(
                    entity="LWPOLYLINE",
                    name=DXF_FIELD_NAMES["x"],
                    code=10,
                ),
            )
        elif code == 20:
            if pending_x is None:
                raise ValueError(ERR_DXF_LWPOLYLINE_Y_WITHOUT_X)
            y = _parse_float(
                value,
                DXF_FIELD.format(
                    entity="LWPOLYLINE",
                    name=DXF_FIELD_NAMES["y"],
                    code=20,
                ),
            )
            points.append((pending_x, y))
            bulges.append(0.0)
            pending_x = None
        elif code == 42:
            # Отсутствие code 42 допустимо и означает прямой сегмент (bulge=0).
            # Но если поле присутствует, его значение обязано быть числом.
            bulge = _parse_float(
                value,
                DXF_FIELD.format(
                    entity="LWPOLYLINE",
                    name=DXF_FIELD_NAMES["bulge"],
                    code=42,
                ),
            )
            if not bulges:
                raise ValueError(ERR_DXF_LWPOLYLINE_BULGE_FIRST)
            bulges[-1] = bulge

    if pending_x is not None:
        raise ValueError(ERR_DXF_LWPOLYLINE_NO_LAST_Y)

    return points, bulges


def _build_entity(etype, data):
    """Создать поддерживаемую DXF-сущность или вернуть None для неподдерживаемой."""
    layer = _first(data, 8, "0") or "0"

    if etype == "LINE":
        x1 = _field_float(data, 10, etype, "start_x")
        y1 = _field_float(data, 20, etype, "start_y")
        x2 = _field_float(data, 11, etype, "end_x")
        y2 = _field_float(data, 21, etype, "end_y")
        return DxfLine((x1, y1), (x2, y2), layer=layer)

    if etype == "CIRCLE":
        _validate_xy_ocs(data, etype)
        cx = _field_float(data, 10, etype, "center_x")
        cy = _field_float(data, 20, etype, "center_y")
        radius = _field_float(data, 40, etype, "radius")
        if radius <= 0.0:
            raise ValueError(
                ERR_DXF_NOT_POSITIVE.format(
                    field=DXF_FIELD.format(
                        entity=etype,
                        name=DXF_FIELD_NAMES["radius"],
                        code=40,
                    )
                )
            )
        return DxfCircle((cx, cy), radius, layer=layer)

    if etype == "ARC":
        _validate_xy_ocs(data, etype)
        cx = _field_float(data, 10, etype, "center_x")
        cy = _field_float(data, 20, etype, "center_y")
        radius = _field_float(data, 40, etype, "radius")
        start_angle = _field_float(data, 50, etype, "start_angle")
        end_angle = _field_float(data, 51, etype, "end_angle")
        if radius <= 0.0:
            raise ValueError(
                ERR_DXF_NOT_POSITIVE.format(
                    field=DXF_FIELD.format(
                        entity=etype,
                        name=DXF_FIELD_NAMES["radius"],
                        code=40,
                    )
                )
            )
        return DxfArc(
            (cx, cy), radius, start_angle, end_angle, layer=layer
        )

    if etype == "LWPOLYLINE":
        _validate_xy_ocs(data, etype)
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

    _validate_xy_ocs(header, "POLYLINE")
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

            x = _field_float(vertex_data, 10, "VERTEX", "x")
            y = _field_float(vertex_data, 20, "VERTEX", "y")
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
