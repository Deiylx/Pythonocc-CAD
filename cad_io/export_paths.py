import os
from pathlib import Path

from cad_io.registry import check_kind
from cad_io.strings import (
    ERR_BAD_DEFAULT_EXT,
    ERR_BAD_EXT,
    ERR_EMPTY_PATH,
    ERR_FILE_EXISTS,
    ERR_IS_DIRECTORY,
    ERR_MISSING_DIR,
    ERR_MISSING_EXT,
    ERR_WRONG_KIND,
    KIND_LABELS,
    NO_WRITER,
    UNKNOWN_FORMAT,
)


def _normalize_extension(extension):
    extension = extension.lower()
    if not extension.startswith("."):
        extension = "." + extension
    return extension


def prepare_export_path(
    path,
    allowed_exts=(".step", ".stp"),
    overwrite=False,
    default_ext=None,
):
    """Проверяет и нормализует путь для экспорта файла.

    Параметры:
        path: путь к файлу (str, Path или объект с ``__fspath__``).
        allowed_exts: допустимые расширения (кортеж/список) либо одна
            строка-расширение; регистр не важен.
        overwrite: если False, существующий файл запрещён.
        default_ext: расширение, если у ``path`` суффикса нет.

    Возвращает:
        pathlib.Path — готовый путь к файлу экспорта.

    Исключения:
        ValueError: пустой ``path``/``None``; нет расширения и нет
            осмысленного ``default_ext``; ``default_ext`` только «.»;
            расширение не из ``allowed_exts``.
        FileNotFoundError: родительский каталог не существует.
        IsADirectoryError: ``path`` указывает на существующую папку.
        FileExistsError: файл уже есть и ``overwrite`` is False.
        TypeError: ``path`` нельзя передать в ``os.fspath`` (не путь).
    """
    if isinstance(allowed_exts, str):
        allowed_exts = (allowed_exts,)

    if path is None:
        raise ValueError(ERR_EMPTY_PATH)

    raw_path = os.fspath(path)
    if isinstance(raw_path, bytes):
        raw_path = os.fsdecode(raw_path)

    if not raw_path or not raw_path.strip():
        raise ValueError(ERR_EMPTY_PATH)

    export_path = Path(raw_path)
    extension = export_path.suffix

    if not extension:
        if default_ext is None or not str(default_ext).strip():
            raise ValueError(ERR_MISSING_EXT)

        extension = _normalize_extension(str(default_ext))

        if extension == ".":
            raise ValueError(ERR_BAD_DEFAULT_EXT)

        export_path = export_path.with_suffix(extension)
        extension = export_path.suffix

    normalized_allowed = tuple(
        _normalize_extension(ext) for ext in allowed_exts
    )

    if extension.lower() not in normalized_allowed:
        raise ValueError(
            ERR_BAD_EXT.format(
                ext=extension,
                allowed=", ".join(normalized_allowed),
            )
        )

    if not export_path.parent.is_dir():
        raise FileNotFoundError(
            ERR_MISSING_DIR.format(path=export_path.parent)
        )

    if export_path.is_dir():
        raise IsADirectoryError(
            ERR_IS_DIRECTORY.format(path=export_path)
        )

    if export_path.exists() and not overwrite:
        raise FileExistsError(
            ERR_FILE_EXISTS.format(path=export_path)
        )

    return export_path


def _wrong_kind_error(spec, kind):
    return ValueError(
        ERR_WRONG_KIND.format(
            name=spec.name,
            spec_kind=KIND_LABELS.get(spec.kind, spec.kind),
            kind=KIND_LABELS.get(kind, kind),
        )
    )


def choose_export_target(registry, raw_path, selected_filter=None, kind=None):
    """Выбрать формат и путь экспорта по ответу диалога «Сохранить как».

    Параметры:
        registry: реестр форматов (cad_io.registry.Registry).
        raw_path: путь, который ввёл пользователь.
        selected_filter: выбранная запись фильтра, например
            "STEP (*.step *.stp)"; не распознана — формат по расширению.
        kind: тип экспортируемой модели ("3d" или "2d"); формат другого
            типа — и по фильтру, и по введённому расширению — отказ.
            None — тип не проверяется.

    Возвращает:
        (FormatSpec, pathlib.Path).

    Перезапись: если пользователь сам ввёл расширение, диалог Qt уже
    спросил подтверждение — разрешаем; если расширение добавили мы —
    существующий файл не затираем (FileExistsError).

    Исключения: ValueError (недопустимый kind — как в Registry.qt_filter;
    пустой путь, нет расширения, неизвестный формат, формат другого типа,
    формат без записи, расширение не того формата) и исключения
    prepare_export_path.
    """
    check_kind(kind)
    if raw_path is None:
        raise ValueError(ERR_EMPTY_PATH)
    raw_path = os.fspath(raw_path)
    if isinstance(raw_path, bytes):
        raw_path = os.fsdecode(raw_path)
    if not raw_path.strip():
        raise ValueError(ERR_EMPTY_PATH)
    typed_ext = Path(raw_path).suffix

    spec = registry.find_by_filter(selected_filter)
    if spec is None:
        if not typed_ext:
            raise ValueError(ERR_MISSING_EXT)
        spec = registry.find_by_extension(typed_ext)
        if spec is None:
            raise ValueError(UNKNOWN_FORMAT.format(ext=typed_ext))
    if kind is not None:
        if spec.kind != kind:
            raise _wrong_kind_error(spec, kind)
        # Фильтр подходит, но введено расширение формата другого типа (part.dxf при фильтре STEP).
        typed_spec = registry.find_by_extension(typed_ext)
        if typed_spec is not None and typed_spec.kind != kind:
            raise _wrong_kind_error(typed_spec, kind)
    if not spec.can_write:
        raise ValueError(NO_WRITER.format(name=spec.name))

    path = prepare_export_path(
        raw_path,
        allowed_exts=spec.extensions,
        overwrite=bool(typed_ext),
        default_ext=spec.extensions[0],
    )
    return spec, path
