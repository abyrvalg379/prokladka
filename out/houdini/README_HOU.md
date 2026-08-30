# PROKLADKA для Houdini — Установка

Установка через **Houdini Packages** (как SideFX Labs). Полка грузится из
toolbar XML при каждом старте Houdini — переживает обновления и рестарты.

## Требования

- Houdini **20.5+** (Python 3.11; для других версий переименовать
  `python3.11libs` под версию Python Houdini)

## Установка

### Способ 1 — двойной клик (рекомендуется)

**Закрой Houdini**, затем открой (двойной клик):

```
out/houdini/install_PROKLADKA.bat
```

Установит всё: файлы пакета, `packages/prokladka.json`, видимость полки.
Запускай Houdini — вкладка PROKLADKA на полке.

Состав: `install_PROKLADKA.bat` (bootstrap) + `install_prokladka_hou.ps1`
(логика). Работает на любой машине, ничего не нужно править.

### Способ 2 — вручную, 2 шага

**1.** Скопировать папку `out/houdini/package/prokladka/houdini/` (целиком)
в папку префов Houdini:

```
<папка скачанного репо>/out/houdini/package/prokladka/houdini
  →  <pref>/prokladka/houdini
```

**2.** Создать файл `<pref>/packages/prokladka.json`:

```json
{
    "env": [
        {"PROKLADKA": "C:/Users/<user>/Documents/houdini20.5/prokladka/houdini"}
    ],
    "path": ["$PROKLADKA"]
}
```

(путь в `env` — куда скопировали на шаге 1, слэши вперёд)

`<pref>` — папка префов Houdini: по умолчанию
`C:\Users\<user>\Documents\houdini20.5` (Houdini 20.5 на Windows), либо
`$HOUDINI_USER_PREF_DIR`, если задана.

**3.** Запустить Houdini. Если вкладки PROKLADKA на полке нет — `+` в строке
вкладок полок → галка **PROKLADKA** (один раз, запоминается).

### Способ 3 — инсталлятором hython (headless)

**Закрой Houdini**, затем в cmd:

```
"C:\Program Files\Side Effects Software\Houdini 20.5.278\bin\hython.exe" ^
  <папка скачанного репо>\out\houdini\install_prokladka_hou.py
```

### Способ 4 — из запущенного Houdini

Python Source Editor (`Windows → Python Source Editor`):

```python
exec(open(r'<путь к распакованному репо>/out/houdini/install_prokladka_hou.py').read())
```

Вывод — в `Windows → Houdini Console`. После — перезапуск Houdini
(видимость: `+` → галка).

## Что делает инсталлятор (и что воспроизводит Способ 1)

| Шаг | Куда | Что |
|-----|------|-----|
| Package copy | `<pref>/prokladka/houdini/` | python3.11libs + toolbar XML |
| Package json | `<pref>/packages/prokladka.json` | регистрация пакета |
| Shelf visibility | `<pref>/toolbar/default.shelf` | полка в видимый набор (только при закрытом GUI) |
| Legacy cleanup | `<pref>/scripts/prokladka/` | удаление старой схемы (если была) |

## Использование

1. Полка **PROKLADKA** → кнопка **PROKLADKA** → Qt-панель
2. **Export** — формат (FBX/VDB/Alembic/USD), Animation Frames, активный SOP
3. **Import** — из recent (общий `bridge_last.json`) или Browse, auto-detect формата
4. **Naming** — суффиксы `_geo/_vdb/_abc/_usd`, auto-scale fix по bbox

## Обновление

Повторить установку (любой способ) — идемпотентно, перезапишет файлы.

## Troubleshooting

**Вкладки нет после перезапуска** → `+` на панели полок → галка PROKLADKA.

**`import prokladka` не работает** → проверь `packages/prokladka.json`
и что `<pref>/prokladka/houdini/python3.11libs/prokladka/` существует.

**Панель не открылась** → `Windows → Houdini Console` — там весь traceback.
