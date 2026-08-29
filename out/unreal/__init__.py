# -*- coding: utf-8 -*-
"""
PROKLADKA для Unreal Engine 5.7+.

Мост-приёмник: импорт FBX из Blender/Maya PROKLADKA в UE Content Browser.
UI: toolbar кнопка + Window → PROKLADKA подменю + dockable EUW-панель.
"""
from .prokladka_ue import (
    # Главные API
    register_menu,
    register_toolbar,
    unregister_menu,
    run_import_dialog,
    process_bridge_import,
    import_fbx,
    import_textures,
    create_material_instance,
    apply_ue_naming,
    read_recent_fbx,
    # Константы
    IMPORT_BASE,
    PREFIX,
    PBR_SLOTS,
)
from .prokladka_ui import (
    open_panel,
    close_panel,
)
from . import prokladka_settings as settings

__version__ = "2.0.0"
