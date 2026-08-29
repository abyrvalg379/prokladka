# -*- coding: utf-8 -*-
"""
menu_action.py — точка входа для команды меню PROKLADKA в UE.

Вызывается через `py "menu_action.py"` из ToolMenus registration.

Установка:
  Эта папка (с __init__.py, prokladka_ue.py, menu_action.py) должна лежать
  в <UE_Project>/Content/Python/prokladka/. Имя пакета = "prokladka".

  Структура:
    Content/Python/
    ├── init_unreal.py
    └── prokladka/
        ├── __init__.py
        ├── prokladka_ue.py
        └── menu_action.py

  init_unreal.py:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prokladka'))
    import prokladka
    prokladka.register_menu()

  Тогда `py ".../prokladka/menu_action.py"` запустит этот файл,
  который через relative import вызовет run_import_dialog().
"""
import os
import sys
import unreal

# Папка этого файла = корень пакета prokladka (UE-side package)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# Подняться на уровень выше чтобы Python увидел пакет "prokladka"
_PARENT_DIR = os.path.dirname(_THIS_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

try:
    # В UE этот пакет лежит в Content/Python/prokladka/ → import prokladka
    import prokladka
    unreal.log("[PROKLADKA] menu_action: launching import dialog")
    prokladka.run_import_dialog()
except ImportError:
    # Fallback для dev-режима: этот файл сам в пакете, использовать __init__
    try:
        # Добавить текущую папку для прямого импорта prokladka_ue
        if _THIS_DIR not in sys.path:
            sys.path.insert(0, _THIS_DIR)
        import prokladka_ue
        prokladka_ue.run_import_dialog()
    except Exception as e2:
        unreal.log_error("[PROKLADKA] Failed to launch: {}".format(e2))
except Exception as e:
    unreal.log_error("[PROKLADKA] menu_action failed: {}".format(e))
