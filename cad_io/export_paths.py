import os
from pathlib import Path

from cad_io.strings import (
    ERR_BAD_DEFAULT_EXT,
    ERR_BAD_EXT,
    ERR_EMPTY_PATH,
    ERR_FILE_EXISTS,
    ERR_IS_DIRECTORY,
    ERR_MISSING_DIR,
    ERR_MISSING_EXT,
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
