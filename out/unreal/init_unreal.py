# -*- coding: utf-8 -*-
"""
init_unreal.py — скрипт автозапуска PROKLADKA для Unreal Engine.

Положить в: <UE_Project>/Content/Python/init_unreal.py

UE автоматически выполняет init_unreal.py в Content/Python/ при старте.
Здесь: добавляем prokladka/ в sys.path, регистрируем toolbar кнопку +
подменю Window → PROKLADKA. Панель создаётся при первом open_panel().
"""
import os
import sys

try:
    import unreal
except ImportError:
    # Не в UE — просто выходим
    sys.exit(0)

# Папка рядом с этим файлом (= Content/Python/)
_PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
_PROKLADKA_DIR = os.path.join(_PYTHON_DIR, "prokladka")

if _PROKLADKA_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

try:
    import prokladka
    # Toolbar кнопка в Level Editor
    prokladka.register_toolbar()
    # Подменю Window → PROKLADKA
    prokladka.register_menu()
    unreal.log("[PROKLADKA] Auto-init OK (toolbar + Window submenu)")
except Exception as e:
    unreal.log_warning("[PROKLADKA] init_unreal.py failed: {}".format(e))
    # Не падать весь UE из-за одной ошибки инициализации
