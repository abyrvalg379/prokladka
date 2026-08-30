# Changelog

Все заметные изменения PROKLADKA документируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/).

## [2.0.0] — 2026-08-30 (UE-сторона)

### Added
- **EUW-панель** (`prokladka_ui.py`) — dockable Editor Utility Widget:
  Recent FBX (цикл `<`/`>`), Mesh type cycle-кнопка (Auto/Static/Skeletal),
  IMPORT FBX / Browse, настройки (import path, master mat, scale, auto-textures),
  статус-строка. Создаётся автоматически как `/Game/Prokladka/BP_ProkladkaPanel`
- **Toolbar кнопка** PROKLADKA в Level Editor (`register_toolbar()`)
- **Подменю Window → PROKLADKA**: Open Panel / Import Bridge FBX / Settings Folder
- **Settings JSON** (`prokladka_settings.py`) — `C:\temp\prokladka_ue_settings.json`
- Тестовый проект UE 5.7 `prokladka_test` пересоздан (старый удалён)

### Changed
- UE 5.8 → **UE 5.7** (переустановка: `D:\Unreal\UE_5.8\` → `D:\UE\UE_5.7\`)
- Версия UE-пакета: 1.0.0 → 2.0.0

### Removed
- Popup-only UI как единственный способ (остался как fallback в подменю)

## [1.9.1] — 2026-08-30 (Houdini-сторона)

### Added
- **Полка PROKLADKA: 7 кнопок** — панель + one-click Export FBX/VDB/Alembic/USD
  + Import Bridge (последний экспорт) + Apply Naming. Свои SVG-иконки
  (config/Icons, грузятся из пакета). Второй способ использования помимо панели

### Changed
- **Установка переведена на Houdini Packages** (как SideFX Labs):
  `packages/prokladka.json` + `<pref>/prokladka/houdini/` (python3.11libs +
  toolbar XML). Полка грузится из `toolbar/prokladka.shelf` при каждом старте —
  без hou.shelves API и ручных галок
- Инсталлятор rewritten: headless-режим через hython (ноль действий при
  закрытом Houdini, включая видимость полки через default.shelf shelfSetEdit),
  идемпотентный, с legacy-cleanup
- Резолв преф-папки через `$HOUDINI_USER_PREF_DIR` (на основном ПК это
  `Documents\houdini20.5`, не `~\houdini20.5`)
- `bridge_qt.py`: импорт prokladka_hou через relative с fallback (package-режим)

### Fixed
- Кнопка полки больше не ломается после legacy-cleanup (скрипт тула теперь
  `import prokladka; prokladka.launch()`)

## [1.9.0] — 2026-07-21

### Added
- **Rig Transfer System** — перенос рига между Maya и Blender через FBX + JSON recipe
  - `rig_recipe.py` — DCC-agnostic формат данных (dataclasses + JSON)
  - `rig_maya.py` — extract/reconstruct для Maya (cmds API)
  - `rig_blender.py` — extract/reconstruct для Blender (bpy API)
  - 6 типов constraints: parent, point, orient, scale, aim, aim_no_up
  - Custom control shapes переносятся как curve points
- **Naming preset "Rig"** — `_geo`/`_grp`/`_skel`/`_jnt`/`_ctl` суффиксы
- **Universal UV Renamer** — конвенции Maya/Blender/Houdini/Unreal/Custom
- **PBR Texture Assigner** (Maya Qt) — UDIM auto-detect, ACES colorSpace
- **Materials utils** (Maya Qt) — Standard Surface по умолчанию, mClean, Copy Mat
- **Recent FBX** список в Maya Qt с чтением общего `bridge_last.json`
- **Installer для Maya** — drag&drop `install_prokladka.py`

### Changed
- Имя аддона: `Bridge Maya Import/ExportFBX V7` → **PROKLADKA**
- Категория N-панели: `Bridge V7` → `PROKLADKA`
- Plain Scale → **Legacy scale** (понятнее семантика)
- Две равнозначные кнопки Export/Import вместо одной большой + маленькая
- Структура проекта: single-file → package (`prokladka/blender/`, `prokladka/maya/`)
- Нейминг: hardcoded VVERH → система редактируемых пресетов в AddonPreferences

### Removed
- Зависимости от сторонних аддонов: Better FBX, Pies Plus
- cmds-версия Maya бриджа (заменена на Qt)

## [1.7.0] — 2026-07-17 (как Bridge V7)

### Added
- Аддон Bridge Maya Import/ExportFBX V7
- FBX I/O с именем файла из сцены (`<scene>_bridge.fbx`)
- VVERH-нейминг (hardcoded lowercase + _geo/_grp/_skel)
- Plain Scale чекбокс
- Recent FBX JSON (`bridge_last.json`)

### Based on
- Оригинальный bridge V6 by Ismailov Dmitry
