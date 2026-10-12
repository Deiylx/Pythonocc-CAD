"""Реестр форматов: расширение файла -> функции чтения и записи.

Совместимо с Python 3.7. OCC и Qt здесь не импортируются.
"""

import os

from cad_io.strings import ALL_SUPPORTED


def check_kind(kind):
    """Проверить аргумент kind фильтра или экспорта: "2d", "3d" или None (тип не важен).

    Недопустимое значение — ошибка вызывающего кода (ValueError), а не выбор пользователя.
    """
    if kind is not None and kind not in ("2d", "3d"):
        raise ValueError("kind должен быть '2d', '3d' или None: {!r}".format(kind))


class FormatSpec(object):
    """Описание одного формата.

    name       — короткое имя для фильтра диалога, например "STEP".
    extensions — расширения с точкой, например (".step", ".stp").
    reader     — функция path -> объект (или None, если чтения нет).
    writer     — функция (объект, path) -> None (или None, если записи нет).
    kind       — "3d" или "2d".
    """

    def __init__(self, name, extensions, reader=None, writer=None, kind="3d"):
        if not name:
            raise ValueError("Пустое имя формата")
        if not extensions:
            raise ValueError("У формата {} нет расширений".format(name))
        normalized = []
        for ext in extensions:
            if not ext.startswith(".") or len(ext) < 2:
                raise ValueError("Расширение должно начинаться с точки: {!r}".format(ext))
            normalized.append(ext.lower())
        if kind not in ("2d", "3d"):
            raise ValueError("kind должен быть '2d' или '3d': {!r}".format(kind))
        self.name = name
        self.extensions = tuple(normalized)
        self.reader = reader
        self.writer = writer
        self.kind = kind

    @property
    def can_read(self):
        return self.reader is not None

    @property
    def can_write(self):
        return self.writer is not None

    def __repr__(self):
        return "FormatSpec({!r}, {!r})".format(self.name, self.extensions)


class Registry(object):
    """Таблица зарегистрированных форматов."""

    def __init__(self):
        self._specs = []
        self._by_ext = {}

    def register(self, spec):
        for ext in spec.extensions:
            if ext in self._by_ext:
                raise ValueError(
                    "Расширение {} уже занято форматом {}".format(ext, self._by_ext[ext].name)
                )
        self._specs.append(spec)
        for ext in spec.extensions:
            self._by_ext[ext] = spec
        return spec

    def formats(self):
        return list(self._specs)

    def find_by_extension(self, ext):
        if not ext:
            return None
        ext = ext.lower()
        if not ext.startswith("."):
            ext = "." + ext
        return self._by_ext.get(ext)

    def find_by_path(self, path):
        return self.find_by_extension(os.path.splitext(path)[1])

    def readable(self):
        return [s for s in self._specs if s.can_read]

    def writable(self):
        return [s for s in self._specs if s.can_write]

    @staticmethod
    def _patterns(spec):
        return " ".join("*" + ext for ext in spec.extensions)

    def filter_entry(self, spec):
        """Запись фильтра QFileDialog для одного формата: "STEP (*.step *.stp)"."""
        return "{} ({})".format(spec.name, self._patterns(spec))

    def find_by_filter(self, entry):
        """Формат по записи фильтра, которую вернул QFileDialog; не нашли — None.

        Запись «Все поддерживаемые (...)» формата не задаёт — тоже None.
        """
        if not entry:
            return None
        entry = entry.strip()
        for spec in self._specs:
            if self.filter_entry(spec) == entry:
                return spec
        return None

    def qt_filter(self, mode="read", all_label=ALL_SUPPORTED, kind=None):
        """Строка фильтра для QFileDialog.

        Пример: "Все поддерживаемые (*.step *.stp);;STEP (*.step *.stp)".
        Перечисляет ВСЕ расширения формата (например, и .iges, и .igs).
        kind ("3d" или "2d") оставляет только форматы этого типа; None — все.
        """
        if mode == "read":
            specs = self.readable()
        elif mode == "write":
            specs = self.writable()
        else:
            raise ValueError("mode должен быть 'read' или 'write': {!r}".format(mode))
        check_kind(kind)
        if kind is not None:
            specs = [s for s in specs if s.kind == kind]
        parts = []
        all_patterns = []
        for spec in specs:
            all_patterns.append(self._patterns(spec))
            parts.append(self.filter_entry(spec))
        if len(specs) > 1:
            parts.insert(0, "{} ({})".format(all_label, " ".join(all_patterns)))
        return ";;".join(parts)


# Общий реестр приложения. Конвертеры регистрируются в нём в следующих итерациях.
REGISTRY = Registry()
