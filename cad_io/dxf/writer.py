# -*- coding: utf-8 -*-
"""Запись DXF R12 (AC1009) ASCII.

Совместимо с Python 3.7. Ни OCC, ни Qt.
"""

import io

from cad_io.dxf.entities import fmt_number


class DxfWriter(object):
    """Собирает DXF R12. Слои — только "0" (по умолчанию)."""

    def __init__(self):
        self._records = []

    # --- примитивы --------------------------------------------------------

    def add_line(self, x1, y1, x2, y2, layer="0"):
        self._records.append([
            (0, "LINE"), (8, layer),
            (10, x1), (20, y1), (30, 0.0),
            (11, x2), (21, y2), (31, 0.0),
        ])

    def add_circle(self, cx, cy, r, layer="0"):
        self._records.append([
            (0, "CIRCLE"), (8, layer),
            (10, cx), (20, cy), (30, 0.0),
            (40, r),
        ])

    def add_arc(self, cx, cy, r, start_deg, end_deg, layer="0"):
        self._records.append([
            (0, "ARC"), (8, layer),
            (10, cx), (20, cy), (30, 0.0),
            (40, r),
            (50, start_deg), (51, end_deg),
        ])

    def add_polyline(self, points, closed=False, layer="0"):
        """Полилиния R12: POLYLINE + VERTEX* + SEQEND."""
        if not points:
            return
        self._records.append([
            (0, "POLYLINE"), (8, layer),
            (66, 1), (70, 1 if closed else 0),
            (10, 0.0), (20, 0.0), (30, 0.0),
        ])
        for x, y in points:
            self._records.append([
                (0, "VERTEX"), (8, layer),
                (10, x), (20, y), (30, 0.0),
            ])
        self._records.append([(0, "SEQEND"), (8, layer)])

    # --- вывод ------------------------------------------------------------

    def dumps(self):
        """Вернуть DXF как строку."""
        parts = []
        parts.append("0\nSECTION\n2\nHEADER\n")
        parts.append("9\n$ACADVER\n1\nAC1009\n")
        # $INSUNITS в R12 не существует; единицы — договорённость проекта.
        parts.append("0\nENDSEC\n")
        parts.append("0\nSECTION\n2\nENTITIES\n")
        for record in self._records:
            for code, value in record:
                parts.append("{}\n{}\n".format(code, fmt_number(value)))
        parts.append("0\nENDSEC\n0\nEOF\n")
        return "".join(parts)

    def save(self, path):
        """Записать в файл. Только путь; проверки — на вызывающем коде."""
        text = self.dumps()
        # newline="\n" — DXF чувствителен к окончаниям строк.
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
