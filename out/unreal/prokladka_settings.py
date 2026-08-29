# -*- coding: utf-8 -*-
"""
prokladka_settings.py — настройки PROKLADKA для Unreal Engine.

Хранятся в C:\\temp\\prokladka_ue_settings.json (рядом с bridge_last.json).
"""
from __future__ import annotations

import os
import json

try:
    import unreal
    _HAS_UNREAL = True
except ImportError:
    _HAS_UNREAL = False


# ════════════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════════════════════

TEMP_DIRECTORY = r"C:\temp"
SETTINGS_PATH = os.path.join(TEMP_DIRECTORY, "prokladka_ue_settings.json")

DEFAULT_SETTINGS = {
    "import_base": "/Game/Imports/Prokladka",
    "master_material": "/Game/MasterPBR_M",
    "import_scale": 100.0,
    "auto_import_textures": True,
    "last_fbx_path": "",
    "last_mesh_type": "auto",
}

# Кэш в памяти (чтобы не читать файл каждый раз)
_cache: dict = {}


# ════════════════════════════════════════════════════════════════════════════
# API
# ════════════════════════════════════════════════════════════════════════════

def load_settings() -> dict:
    """Загрузить настройки из JSON. Возвращает merged с DEFAULT_SETTINGS."""
    global _cache
    merged = dict(DEFAULT_SETTINGS)

    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged.update(data)
    except Exception as e:
        if _HAS_UNREAL:
            unreal.log_warning("[PROKLADKA] Settings load error: {}".format(e))

    _cache = merged
    return dict(merged)


def save_settings(settings: dict) -> bool:
    """Сохранить настройки в JSON."""
    global _cache
    try:
        os.makedirs(TEMP_DIRECTORY, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        _cache = dict(settings)
        if _HAS_UNREAL:
            unreal.log("[PROKLADKA] Settings saved")
        return True
    except Exception as e:
        if _HAS_UNREAL:
            unreal.log_warning("[PROKLADKA] Settings save error: {}".format(e))
        return False


def get(key: str, default=None):
    """Получить значение настройки. Читает из кэша, если есть, иначе из файла."""
    if not _cache:
        load_settings()
    if default is None:
        default = DEFAULT_SETTINGS.get(key)
    return _cache.get(key, default)


def set(key: str, value) -> None:
    """Установить значение настройки и сохранить."""
    if not _cache:
        load_settings()
    _cache[key] = value
    save_settings(_cache)


def reset() -> dict:
    """Сбросить настройки к дефолтным."""
    save_settings(dict(DEFAULT_SETTINGS))
    return dict(DEFAULT_SETTINGS)
