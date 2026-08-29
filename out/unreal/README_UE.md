# PROKLADKA для Unreal Engine — Установка

## Требования

- Unreal Engine **5.7+**
- Включённый **Python Editor Script Plugin**:
  `Edit → Plugins → Scripting → Python Editor Script Plugin` (✓)
- Перезапустить UE после включения плагина

## Установка

### 1. Скопировать файлы

```
<UE_Project>/Content/Python/
├── init_unreal.py
└── prokladka/
    ├── __init__.py
    ├── prokladka_ue.py
    ├── prokladka_ui.py
    ├── prokladka_settings.py
    └── menu_action.py
```

### 2. Перезапустить UE

При старте UE выполнит `init_unreal.py` и зарегистрирует UI.

## Что появляется в редакторе

| Элемент | Где | Что делает |
|---------|-----|-----------|
| **Toolbar кнопка** `PROKLADKA` | Level Editor toolbar | Открывает dockable панель |
| **Подменю** `Window → PROKLADKA` | Main menu | Open Panel / Import Bridge FBX / Settings Folder |
| **Панель** `BP_ProkladkaPanel` | dockable tab | Полный UI импорта (см. ниже) |

Панель создаётся автоматически при первом `Open Panel` — ассет
`/Game/Prokladka/BP_ProkladkaPanel` в Content Browser.

## Панель

```
PROKLADKA                    READY
-- RECENT FBX --
[<]  bridge.fbx        [>]   ← цикл по недавним экспортам
-- IMPORT --
Mesh type:  [Auto (detect)]  ← клик: Auto → Static → Skeletal
[ IMPORT FBX ]
[ Browse... ]
-- NAMING --
UE convention auto-applied on import:
SM_/SK_/T_/MI_ + PascalCase
-- SETTINGS --
Import path:  [/Game/Imports/Prokladka]
Master mat:   [/Game/MasterPBR_M]
Scale:        [100.0]
[x] Auto-import textures
[ SAVE SETTINGS ]
```

Статус-строка в шапке: READY → IMPORTING → IMPORTED n assets / ERROR.

## Использование

1. В Blender или Maya PROKLADKA: **Export Bridge** → FBX в `C:\temp\<asset>_bridge.fbx`
2. В UE: toolbar кнопка `PROKLADKA` (или Window → PROKLADKA → Open Panel)
3. В панели: выбрать recent (`<` / `>`) или `Browse...`
4. `IMPORT FBX` — ассеты в `/Game/Imports/Prokladka/<asset>/`

## Настройки

`C:\temp\prokladka_ue_settings.json` (создаётся автоматически):

```json
{
  "import_base": "/Game/Imports/Prokladka",
  "master_material": "/Game/MasterPBR_M",
  "import_scale": 100.0,
  "auto_import_textures": true,
  "last_fbx_path": "",
  "last_mesh_type": "auto"
}
```

Править можно в панели (SAVE SETTINGS) или вручную.

## Naming convention

PROKLADKA автоматически применяет UE PascalCase + префиксы:

| Тип | Префикс | Пример |
|------|---------|--------|
| Static Mesh | `SM_` | `SM_WingMain` |
| Skeletal Mesh | `SK_` | `SK_WingMain` |
| Skeleton | `Skeleton_` | `Skeleton_WingMain` |
| Texture | `T_` | `T_WingMain_Albedo` |
| Material Instance | `MI_` | `MI_WingMain` |

## Auto-detect Static vs Skeletal

Алгоритм:
1. Если рядом с FBX есть `<asset>_rig_recipe.json` → Skeletal (rig-экспорт)
2. Иначе → Static (по умолчанию, окружение/props)
3. Если Static импорт пуст → fallback на Skeletal

Кнопка Mesh type в панели всегда позволяет переопределить.

## Materials

PROKLADKA ищет текстуры рядом с FBX (с тем же asset-префиксом). Если находит
PBR карты (Albedo, Normal, ORM, Roughness, Metallic) — создаёт Material Instance
от master material.

**Требуется master material** по пути `/Game/MasterPBR_M` с параметрами:
- `Albedo` (Texture)
- `Normal` (Texture)
- `ORM` (Texture) — AO/Roughness/Metallic packed
- или отдельные `Roughness`, `Metallic`, `AO`
- опционально `Specular`, `Emissive`

Если master material не найден — текстуры импортируются, MI пропускается
(предупреждение в Output Log). Путь к master material меняется в панели.

## Troubleshooting

### Меню/toolbar не появились
- Проверить Python plugin включён
- Перезапустить UE
- Output Log → dropdown `Python` → искать `[PROKLADKA]` сообщения
- Вручную: `import prokladka; prokladka.register_toolbar(); prokladka.register_menu()`

### Панель пустая / не открылась
- Смотреть лог: если `UMG tree build failed` — классы UMG недоступны из Python
  (проверить версию UE ≥ 5.7)
- Пересоздать ассет: удалить `/Game/Prokladka/BP_ProkladkaPanel` → снова Open Panel
- Fallback: Window → PROKLADKA → Import Bridge FBX (popup-flow, всегда работает)

### `py "..."` не работает
- Output Log dropdown → выбрать **Python**
- Команда: `py "C:/path/to/prokladka/menu_action.py"`

### Master material не найден
- Создать `/Game/MasterPBR_M` Material с параметрами (см. выше)
- Или указать свой путь в панели → SAVE SETTINGS

### Skeletal импорт падает
- Mesh type кнопка → "Force Static"
- Или убедиться что FBX действительно содержит skeleton
