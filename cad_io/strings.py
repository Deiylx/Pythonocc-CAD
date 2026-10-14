"""Все новые надписи интерфейса — на русском, в одном месте."""

ALL_SUPPORTED = "Все поддерживаемые"

IMPORT_TITLE = "Импорт файла"
EXPORT_TITLE = "Экспорт файла"

UNKNOWN_FORMAT = "Формат файла не поддерживается: {ext}"
NO_READER = "Формат {name} нельзя открыть, только сохранить"
NO_WRITER = "Формат {name} нельзя сохранить, только открыть"
NOTHING_TO_EXPORT = "Нет модели для экспорта"

IMPORT_OK = "Файл открыт: {path}"
EXPORT_OK = "Файл сохранён: {path}"
IMPORT_FAILED = "Не удалось открыть файл {path}: {error}"
EXPORT_FAILED = "Не удалось сохранить файл {path}: {error}"
EXPORT_SCENE_FAILED = "Не удалось получить модель текущего окна: {error}"
ERR_IMPORT_FILE_NOT_FOUND = "Файл для импорта не найден: '{path}'."

# Ошибки prepare_export_path
ERR_EMPTY_PATH = "Путь для экспорта не может быть пустым."
ERR_MISSING_EXT = "Не указано расширение файла для экспорта."
ERR_BAD_DEFAULT_EXT = "Некорректное расширение файла по умолчанию."
ERR_BAD_EXT = (
    "Недопустимое расширение файла '{ext}'. "
    "Допустимые расширения: {allowed}."
)
ERR_MISSING_DIR = "Каталог назначения не существует: '{path}'."
ERR_IS_DIRECTORY = (
    "Путь указывает на существующую папку, а не файл: '{path}'."
)
ERR_FILE_EXISTS = "Файл уже существует: '{path}'."

# Ошибка choose_export_target: тип формата (FormatSpec.kind) не совпал с типом модели
KIND_LABELS = {"3d": "3D", "2d": "2D"}
ERR_WRONG_KIND = (
    "Формат {name} ({spec_kind}) не подходит для этой модели: "
    "выберите формат {kind}."
)

# Ошибки конвертера STEP (cad_io/converters/step.py)
ERR_STEP_EMPTY_SHAPE = "Нет модели для записи в STEP: форма пустая."
ERR_STEP_WRITE_FAILED = "Не удалось записать файл STEP: '{path}'."
ERR_STEP_FILE_NOT_FOUND = "Файл STEP не найден: '{path}'."
ERR_STEP_READ_FAILED = "Не удалось прочитать файл STEP: '{path}'."
ERR_STEP_NO_SHAPES = "В файле STEP нет геометрии: '{path}'."

# Ошибки конвертера DXF (cad_io/converters/dxf.py)
ERR_DXF_EMPTY_SHAPE = "Нет модели для записи в DXF: форма пустая."
ERR_DXF_WRITE_FAILED = "Не удалось записать файл DXF: '{path}'."
ERR_DXF_FILE_NOT_FOUND = "Файл DXF не найден: '{path}'."
ERR_DXF_READ_FAILED = "Не удалось прочитать файл DXF: '{path}'. Причина: {error}"
DXF_FIELD = "{entity}, {name} (групповой код {code})"
DXF_FIELD_NAMES = {
    "start_x": "X начала",
    "start_y": "Y начала",
    "end_x": "X конца",
    "end_y": "Y конца",
    "center_x": "X центра",
    "center_y": "Y центра",
    "radius": "радиус",
    "start_angle": "начальный угол",
    "end_angle": "конечный угол",
    "flags": "флаги",
    "normal_x": "нормаль X",
    "normal_y": "нормаль Y",
    "normal_z": "нормаль Z",
    "x": "координата X",
    "y": "координата Y",
    "bulge": "выпуклость",
}
ERR_DXF_BAD_NUMBER = (
    "DXF: некорректное числовое значение для {field}: {value!r}"
)
ERR_DXF_NOT_FINITE = (
    "DXF: значение для {field} должно быть конечным числом: {value!r}"
)
ERR_DXF_MISSING_FIELD = "DXF: отсутствует обязательное поле {field}"
ERR_DXF_NOT_INTEGER = "DXF: поле {field} должно быть целым числом"
ERR_DXF_NOT_POSITIVE = "DXF: поле {field} должно быть больше нуля"
ERR_DXF_LWPOLYLINE_X_WITHOUT_Y = (
    "DXF: LWPOLYLINE: координата X без следующей координаты Y"
)
ERR_DXF_LWPOLYLINE_Y_WITHOUT_X = (
    "DXF: LWPOLYLINE: координата Y без предшествующей координаты X"
)
ERR_DXF_LWPOLYLINE_BULGE_FIRST = (
    "DXF: LWPOLYLINE: выпуклость (групповой код 42) задана до первой вершины"
)
ERR_DXF_LWPOLYLINE_NO_LAST_Y = (
    "DXF: LWPOLYLINE: отсутствует координата Y для последней вершины"
)
ERR_DXF_UNSUPPORTED_OCS = (
    "DXF: сущность {entity}: неподдерживаемая нормаль OCS {normal}; "
    "поддерживается только (0, 0, 1)."
)
ERR_DXF_NO_SHAPES = "В файле DXF нет геометрии: '{path}'."
