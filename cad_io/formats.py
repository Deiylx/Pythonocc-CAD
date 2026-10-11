"""Регистрация встроенных форматов в реестре.

registry.py не импортирует OCC и Qt, поэтому конвертеры подключаются здесь.
Импорт cad_io ничего не регистрирует: register_builtin() вызывает код приложения.
"""

from cad_io.converters.step import read_step, write_step
from cad_io.registry import REGISTRY, FormatSpec


def step_spec():
    return FormatSpec("STEP", (".step", ".stp"), reader=read_step, writer=write_step, kind="3d")


def builtin_specs():
    return [step_spec()]


def register_builtin(registry=REGISTRY):
    """Зарегистрировать встроенные форматы; уже зарегистрированные пропускаются.

    Повторный вызов не падает. Если расширение занято другим форматом,
    registry.register бросает ValueError. Возвращает реестр.
    """
    for spec in builtin_specs():
        known = registry.find_by_extension(spec.extensions[0])
        if known is not None and known.name == spec.name:
            continue
        registry.register(spec)
    return registry
