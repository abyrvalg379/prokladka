# PROKLADKA для Houdini — Установка

Установка через **Houdini Packages** (как SideFX Labs). Полка грузится из
toolbar XML при каждом старте Houdini — переживает обновления и рестарты.

## Требования

- Houdini **20.5+** (Python 3.11; для других версий переименовать
  `python3.11libs` под версию Python Houdini)
- Windows (пути инсталлятора под Windows; на Linux — то же самое руками)

## Установка

### Способ 1 — headless (рекомендуется, ноль ручных действий)

**Закрой Houdini**, затем:

```
"C:\Program Files\Side Effects Software\Houdini 20.5.278\bin\hython.exe" ^
  D:\AI\ZCode\Project\prokladka\out\houdini\install_prokladka_hou.py
```

Установит всё, включая видимость полки. Открой Houdini — вкладка PROKLADKA
уже на полке.

### Способ 2 — из запущенного Houdini

Python Source Editor (`Windows → Python Source Editor`):

```python
exec(open(r'D:\AI\ZCode\Project\prokladka\out\houdini\install_prokladka_hou.py').read())
```

После этого перезапусти Houdini. Если вкладки не видно — `+` на панели
полок → галка **PROKLADKA** (один раз, запоминается).

## Что делает инсталлятор

| Шаг | Куда | Что |
|-----|------|-----|
| Package copy | `<pref>/prokladka/houdini/` | python3.11libs + toolbar XML |
| Package json | `<pref>/packages/prokladka.json` | регистрация пакета |
| Shelf visibility | `<pref>/toolbar/default.shelf` | полка в видимый набор (только при закрытом GUI) |
| Legacy cleanup | `<pref>/scripts/prokladka/` | удаление старой схемы (если была) |

`<pref>` — папка префов Houdini (`$HOUDINI_USER_PREF_DIR`; на основном ПК это
`Documents\houdini20.5`, не `~\houdini20.5`).

## Использование

1. Полка **PROKLADKA** → кнопка **PROKLADKA** → Qt-панель
2. **Export** — формат (FBX/VDB/Alembic/USD), Animation Frames, активный SOP
3. **Import** — из recent (общий `bridge_last.json`) или Browse, auto-detect формата
4. **Naming** — суффиксы `_geo/_vdb/_abc/_usd`, auto-scale fix по bbox

## Обновление

Перезапустить инсталлятор (любой способ) — идемпотентно, перезапишет файлы.

## Troubleshooting

**Вкладки нет после перезапуска** → `+` на панели полок → галка PROKLADKA.
(Появляется когда инсталлятор запускался при открытом Houdini и не смог
править default.shelf.)

**`import prokladka` не работает в hython** → проверь `packages/prokladka.json`
и что `<pref>/prokladka/houdini/python3.11libs/prokladka/` существует.

**Панель не открылась** → `Windows → Houdini Console` — там весь traceback.
