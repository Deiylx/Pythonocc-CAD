import os
from pathlib import Path


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
    if path is None:
        raise ValueError("Путь для экспорта не может быть пустым.")

    raw_path = os.fspath(path)
    if isinstance(raw_path, bytes):
        raw_path = os.fsdecode(raw_path)

    if not raw_path or not raw_path.strip():
        raise ValueError("Путь для экспорта не может быть пустым.")

    export_path = Path(raw_path)
    extension = export_path.suffix

    if not extension:
        if default_ext is None or not str(default_ext).strip():
            raise ValueError("Не указано расширение файла для экспорта.")

        extension = _normalize_extension(str(default_ext))

        if extension == ".":
            raise ValueError("Некорректное расширение файла по умолчанию.")

        export_path = export_path.with_suffix(extension)
        extension = export_path.suffix

    normalized_allowed = tuple(
        _normalize_extension(ext) for ext in allowed_exts
    )

    if extension.lower() not in normalized_allowed:
        raise ValueError(
            "Недопустимое расширение файла '{}'. "
            "Допустимые расширения: {}.".format(
                extension,
                ", ".join(normalized_allowed),
            )
        )

    if not export_path.parent.is_dir():
        raise FileNotFoundError(
            "Каталог назначения не существует: '{}'.".format(
                export_path.parent
            )
        )

    if export_path.exists() and not overwrite:
        raise FileExistsError(
            "Файл уже существует: '{}'.".format(export_path)
        )

    return export_path