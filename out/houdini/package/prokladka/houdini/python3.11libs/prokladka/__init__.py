# -*- coding: utf-8 -*-
"""
PROKLADKA для Houdini 20.5+.

Двусторонний мост: 4 формата обмена (FBX, VDB, Alembic, USD).
"""
from .prokladka_hou import (
    # Главные API
    launch,
    export_current,
    export_fbx,
    export_vdb,
    export_alembic,
    export_usd,
    import_file,
    apply_hou_naming,
    get_active_sop,
    get_active_lop,
    read_recent_files,
    clear_recent_json,
    update_recent_json,
    # Константы
    TEMP_DIRECTORY,
    RECENT_JSON,
    EXPORT_FORMATS,
    HOUDINI_NAMING_PRESETS,
)

__version__ = "1.0.0"
