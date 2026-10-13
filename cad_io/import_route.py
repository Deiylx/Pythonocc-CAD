"""Маршрут кнопки «导入»: старый код OCAF.Import_part или конвертер из реестра.

Без Qt и OCC. STEP, IGES и STL читает старый код (Win64/module/OCAFModule.py, Import_part):
у STEP он сохраняет цвета, имена и дерево сборки. Через реестр идут только форматы,
расширений которых старый код не знает; их регистрация подхватывается сама.
"""

import os

from cad_io.registry import FormatSpec, Registry
from cad_io.strings import UNKNOWN_FORMAT

# Ветки Import_part: STEP (через Assemble, с цветами и деревом), IGES, STL.
LEGACY_IMPORT_FORMATS = (
    ("STEP", (".step", ".stp")),
    ("IGES", (".iges", ".igs")),
    ("STL", (".stl",)),
)

ROUTE_LEGACY = "legacy"
ROUTE_REGISTRY = "registry"


def _legacy_reader(path):
    """Метка старого пути в FormatSpec.reader: такой файл читает OCAF.Import_part, не cad_io."""
    raise RuntimeError("Файл читает OCAF.Import_part: {}".format(path))


def build_import_registry(registry):
    """Реестр для диалога «导入»: старые форматы и 3D-форматы реестра, которые можно читать.

    Формат реестра пропускается целиком, если хотя бы одно его расширение знает старый код.
    Исходный реестр не меняется.
    """
    combined = Registry()
    for name, extensions in LEGACY_IMPORT_FORMATS:
        combined.register(FormatSpec(name, extensions, reader=_legacy_reader, kind="3d"))
    for spec in registry.readable():
        if spec.kind != "3d":
            continue
        if any(combined.find_by_extension(ext) is not None for ext in spec.extensions):
            continue
        combined.register(spec)
    return combined


def choose_import_route(import_registry, path):
    """Куда отправить файл: (ROUTE_LEGACY, None) или (ROUTE_REGISTRY, spec).

    Неизвестное расширение — ValueError(UNKNOWN_FORMAT).
    """
    spec = import_registry.find_by_path(path)
    if spec is None:
        ext = os.path.splitext(path)[1] or os.path.basename(path)
        raise ValueError(UNKNOWN_FORMAT.format(ext=ext))
    if spec.reader is _legacy_reader:
        return ROUTE_LEGACY, None
    return ROUTE_REGISTRY, spec


def base_name(path):
    """Имя файла без папки и расширения: имя новой вкладки и ключ показанной формы."""
    return os.path.splitext(os.path.basename(path))[0] or os.path.basename(path)


def unique_name(base, existing):
    """base, если его нет в existing; иначе «base (2)», «base (3)» и т.д."""
    if base not in existing:
        return base
    number = 2
    while "{} ({})".format(base, number) in existing:
        number += 1
    return "{} ({})".format(base, number)
