# BUGS

Номера строк и цитаты взяты из вывода поиска по файлам (Grep). Код проекта не менялся.

| id | файл:строка | описание | кто нашёл | статус |
|---|---|---|---|---|
| BUG-001 | Win64/module/ShowGui.py:67 | Опасный `eval()` над строкой `connection` из ini: `...add_action(..., True, eval(connection), None)` | список — Opus 5.5; строка — grep (Sonnet 5.5); сверено людьми вручную | открыт |
| BUG-002 | Win64/sketcher/sketcher.py:105 | Опечатка в ключе: `self.new_do_draw_dict["rectangel"].dynamics_drwa_rectangle()`; в словаре (строка 32) ключ `"rectangle"` → KeyError | список — Opus 5.5; строка — grep (Sonnet 5.5); сверено людьми вручную | открыт |
| BUG-003 | Win64/module/OCAFModule.py:245 | В `subject()` используется несуществующая переменная `name`: `self.parent.Displayshape_core_dict[name]...` (в методе `name` не определено) | список — Opus 5.5; строка — grep (Sonnet 5.5) | открыт |
| BUG-004 | Win64/module/OCAFModule.py:47 и :165 | Фильтр диалога содержит только `IGES files(*.iges)`, `.igs` не показывается, хотя обработка `.igs` есть (строки 125, 212) | список — Opus 5.5; строка — grep (Sonnet 5.5) | открыт |
| BUG-005 | Win64/Ribbon/RibbonMain.ini:3 и :5 | Кнопки 保存 (строка 3) и 导出 (строка 5) имеют `connection=None` | список — Opus 5.5; строка — grep (Sonnet 5.5) | открыт |
| BUG-006 | Win64/module/OCAFModule.py:197 | В `Import_part()` (строки 160–238) встроенная функция `id` используется как ключ: `shape_maneger_core_dict[id] = return_shape[0]`. В этом методе `id` не присваивается (`id = 0` на строке 44 — в другом методе, `Open_part()`), поэтому ключом становится сама функция `id`: ошибки нет, но каждое следующее тело STEP молча перезаписывает предыдущее в `shape_maneger_core_dict` | список — Opus 5.5; строка — grep (Sonnet 5.5); подтверждено Opus (прочитан метод) | открыт |
| BUG-007 | Win64/module/OCAFModule.py:238 | В `Import_part()` `finally: Loadprocess.Close()` без `try/except` (в отличие от `Open_part()`, строки 154–158). `Loadprocess` создаётся только внутри `if os.path.exists(filepath):` (строка 170): если пользователь отменил выбор файла или исключение случилось раньше, `finally` бросает `UnboundLocalError` | список — Opus 5.5; строка — grep (Sonnet 5.5); подтверждено Opus (прочитан метод) | открыт |
| BUG-008 | Win64/sketcher/sketcher.py:90 | Проверка не того ключа: `elif self.sketch_type==1 and self.new_do_draw_dict["rectangle"]==None:` — для профиля создаётся `"profile"`, проверять нужно его | подсказка — Opus 5.5; строка и описание — grep (Sonnet 5.5) | открыт |
| BUG-009 | Win64/sketcher/sketcher.py:362 и :366 | Список вместо словаря: `self.windown_sketcher_dict=[]` (строка 362), далее `if windown_name in self.windown_sketcher_dict.keys():` (строка 366) → AttributeError | подсказка — Opus 5.5; строка и описание — grep (Sonnet 5.5) | открыт |

## Примечания

- BUG-006 и BUG-007 разделены: в исходном списке это был один пункт («`id` как ключ и `finally` может упасть»), но это два разных места кода.
- BUG-008 и BUG-009 добавлены по указанию Сергея на «проверку не того ключа» и «список вместо словаря» в `Win64/sketcher/`.
- BUG-003 дополнительно подтверждает ruff: `F821 Undefined name 'name'` в `OCAFModule.py:245`.
- Вручную людьми сверены только BUG-001 и BUG-002.
