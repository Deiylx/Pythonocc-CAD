"""Чтение и запись STEP (AP214, миллиметры).

Использует STEPControl_Writer и STEPControl_Reader из pythonocc 7.4.0 (OCC.Core).
Проверяет только то, что относится к OCC: пустую форму и статусы записи и чтения.
Расширение, папку назначения и перезапись проверяет вызывающий код
(cad_io.export_paths.prepare_export_path).
"""

import os

from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Interface import Interface_Static_SetCVal
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer

from cad_io.strings import (
    ERR_STEP_EMPTY_SHAPE,
    ERR_STEP_FILE_NOT_FOUND,
    ERR_STEP_NO_SHAPES,
    ERR_STEP_READ_FAILED,
    ERR_STEP_WRITE_FAILED,
)

STEP_SCHEMA = "AP214IS"
STEP_UNIT = "MM"


def write_step(shape, path):
    """Записать форму (TopoDS_Shape) в файл STEP.

    ValueError — форма пустая; OSError — OCC не смог перевести форму или записать файл.
    """
    if shape is None or shape.IsNull():
        raise ValueError(ERR_STEP_EMPTY_SHAPE)
    path = os.fspath(path)

    # Параметры write.step.* появляются только после создания первого STEPControl_Writer
    # (или Reader): до этого SetCVal возвращает False. Поэтому writer создаём раньше.
    writer = STEPControl_Writer()

    # Interface_Static — глобальное состояние OCCT: выставляем при каждой записи.
    if not Interface_Static_SetCVal("write.step.schema", STEP_SCHEMA):
        raise OSError(ERR_STEP_WRITE_FAILED.format(path=path))
    if not Interface_Static_SetCVal("write.step.unit", STEP_UNIT):
        raise OSError(ERR_STEP_WRITE_FAILED.format(path=path))

    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise OSError(ERR_STEP_WRITE_FAILED.format(path=path))
    if writer.Write(path) != IFSelect_RetDone:
        raise OSError(ERR_STEP_WRITE_FAILED.format(path=path))


def read_step(path):
    """Прочитать файл STEP и вернуть одну форму (TopoDS_Shape).

    FileNotFoundError — файла нет; ValueError — файл не разобран или в нём нет геометрии.
    """
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(ERR_STEP_FILE_NOT_FOUND.format(path=path))

    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise ValueError(ERR_STEP_READ_FAILED.format(path=path))
    if reader.TransferRoots() == 0:
        raise ValueError(ERR_STEP_NO_SHAPES.format(path=path))
    # Без перенесённых форм обёртка 7.4 возвращает из OneShape() None, а не пустую форму.
    shape = reader.OneShape()
    if shape is None or shape.IsNull():
        raise ValueError(ERR_STEP_NO_SHAPES.format(path=path))
    return shape
