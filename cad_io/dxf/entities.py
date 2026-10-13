# -*- coding: utf-8 -*-
"""Примитивы DXF R12 и вспомогательные функции.

Только данные и чистая математика. Ни OCC, ни Qt, ни файлового ввода-вывода.
Совместимо с Python 3.7.
"""

import math


TWO_PI = 2.0 * math.pi


class DxfLine(object):
    """Отрезок: start и end — кортежи (x, y)."""

    __slots__ = ("start", "end", "layer")

    def __init__(self, start, end, layer="0"):
        self.start = start
        self.end = end
        self.layer = layer

    def __repr__(self):
        return "DxfLine({!r}, {!r}, layer={!r})".format(
            self.start, self.end, self.layer
        )


class DxfCircle(object):
    """Окружность: center (x, y) и radius > 0."""

    __slots__ = ("center", "radius", "layer")

    def __init__(self, center, radius, layer="0"):
        self.center = center
        self.radius = radius
        self.layer = layer

    def __repr__(self):
        return "DxfCircle({!r}, r={}, layer={!r})".format(
            self.center, self.radius, self.layer
        )


class DxfArc(object):
    """Дуга: углы в градусах, CCW, [0, 360)."""

    __slots__ = ("center", "radius", "start_angle", "end_angle", "layer")

    def __init__(self, center, radius, start_angle, end_angle, layer="0"):
        self.center = center
        self.radius = radius
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.layer = layer

    def __repr__(self):
        return "DxfArc({!r}, r={}, {}..{}, layer={!r})".format(
            self.center,
            self.radius,
            self.start_angle,
            self.end_angle,
            self.layer,
        )


class DxfPolyline(object):
    """Полилиния: points — [(x, y), ...], bulges — по числу точек (код 42)."""

    __slots__ = ("points", "closed", "layer", "bulges")

    def __init__(self, points, closed=False, layer="0", bulges=None):
        self.points = list(points)
        self.closed = bool(closed)
        self.layer = layer
        if bulges is None:
            self.bulges = [0.0] * len(self.points)
        else:
            values = list(bulges)
            while len(values) < len(self.points):
                values.append(0.0)
            self.bulges = values[:len(self.points)]

    def __repr__(self):
        return "DxfPolyline(n={}, closed={}, layer={!r})".format(
            len(self.points), self.closed, self.layer
        )


# ---------------------------------------------------------------------------
# Числа
# ---------------------------------------------------------------------------

def fmt_number(value):
    """Оформить число для DXF.

    - целое -> "5"
    - float -> без хвостовых нулей и экспоненты ("5.5", "0.0")
    - -0.0 -> "0.0"
    - NaN/inf -> ValueError: в DXF такие значения писать нельзя.
    """
    if isinstance(value, float):
        if value != value:
            raise ValueError("NaN нельзя записать в DXF")
        if value == float("inf") or value == float("-inf"):
            raise ValueError("Бесконечность нельзя записать в DXF")
        if value == 0.0:
            value = 0.0
        text = "{:.9f}".format(value).rstrip("0").rstrip(".")
        if text in ("", "-"):
            text = "0.0"
        elif "." not in text:
            text += ".0"
        return text
    return str(value)


# ---------------------------------------------------------------------------
# Bulge -> дуга (для импорта LWPOLYLINE / POLYLINE)
# ---------------------------------------------------------------------------

def bulge_to_arc(p1, p2, bulge):
    """Перевести bulge (код 42) в параметры дуги.

    bulge = tan(theta / 4), где theta — подписанный угол дуги.
    Положительное значение задаёт направление против часовой стрелки,
    отрицательное — по часовой стрелке. Модуль угла может быть больше 180°.

    Возвращает (cx, cy, radius, a1_deg, a2_deg, ccw) или None,
    если bulge вырожден, точки совпадают или значение не конечно.
    """
    if bulge is None or not math.isfinite(bulge):
        return None
    if abs(bulge) < 1e-12:
        return None

    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    chord = math.hypot(dx, dy)
    if chord < 1e-12:
        return None

    theta = 4.0 * math.atan(bulge)
    half = abs(theta) / 2.0
    if half < 1e-12 or half >= math.pi:
        return None

    sin_half = math.sin(half)
    if abs(sin_half) < 1e-12:
        return None

    radius = chord / (2.0 * sin_half)
    if not math.isfinite(radius) or radius <= 0.0:
        return None

    # Подписанное смещение центра от середины хорды.
    # Знак (1 / bulge - bulge) важен: для |bulge| > 1 центр находится
    # по другую сторону хорды, иначе большая дуга ошибочно станет малой.
    center_offset = (chord / 4.0) * (1.0 / bulge - bulge)

    mx = (x1 + x2) / 2.0
    my = (y1 + y2) / 2.0
    nx = -dy / chord
    ny = dx / chord
    cx = mx + nx * center_offset
    cy = my + ny * center_offset

    if not math.isfinite(cx) or not math.isfinite(cy):
        return None

    a1 = math.degrees(math.atan2(y1 - cy, x1 - cx)) % 360.0
    a2 = math.degrees(math.atan2(y2 - cy, x2 - cx)) % 360.0
    ccw = theta > 0.0
    return cx, cy, radius, a1, a2, ccw
