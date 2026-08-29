# -*- coding: utf-8 -*-
"""
prokladka_ue.py — PROKLADKA для Unreal Engine 5.7+ (сторона приёмника).

Мост-получатель: принимает FBX из C:\\temp\\<asset>_bridge.fbx, импортирует
как Static/Skeletal Mesh + Material Instance из PBR текстур.

UI: toolbar кнопка Level Editor + подменю Window → PROKLADKA + EUW-панель
(dockable, prokladka_ui.py).

Запуск:
  - Автоматически через init_unreal.py (регистрация UI)
  - Вручную: Tools → Run Python Script → этот файл
  - Из Output Log: `py "C:/path/to/prokladka_ue.py"`
"""
from __future__ import annotations

import os
import re
import json
import unreal


# ════════════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════════════════════

TEMP_DIRECTORY = r"C:\temp"
RECENT_JSON    = os.path.join(TEMP_DIRECTORY, "bridge_last.json")
IMPORT_BASE    = "/Game/Imports/Prokladka"

# Naming convention (UE PascalCase + префиксы)
PREFIX = {
    "static_mesh":   "SM_",
    "skeletal_mesh": "SK_",
    "skeleton":      "Skeleton_",
    "texture":       "T_",
    "material_inst": "MI_",
}

# PBR slot mapping: подстрока в имени файла → Material param name
PBR_SLOTS = {
    "albedo":      "Albedo",
    "basecolor":   "Albedo",
    "basecolour":  "Albedo",
    "diffuse":     "Albedo",
    "color":       "Albedo",
    "colour":      "Albedo",
    "normal":      "Normal",
    "norm":        "Normal",
    "nrm":         "Normal",
    "orm":         "ORM",
    "roughness":   "Roughness",
    "metallic":    "Metallic",
    "metalness":   "Metallic",
    "metal":       "Metallic",
    "ao":          "AO",
    "ambient":     "AO",
    "specular":    "Specular",
    "spec":        "Specular",
    "emissive":    "Emissive",
    "emission":    "Emissive",
}


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _to_pascal_case(name: str) -> str:
    """lower_geo → LowerGeo. Чистит не-буквы."""
    words = re.split(r'[_\-\s\.]+', name)
    return ''.join(w[:1].upper() + w[1:] for w in words if w)


def _normalize_slashes(path: str) -> str:
    """Windows path → UE-style (forward slashes)."""
    return path.replace("\\", "/")


def _asset_name_from_fbx(fbx_path: str) -> str:
    """<asset>_bridge.fbx → <asset>."""
    base = os.path.splitext(os.path.basename(fbx_path))[0]
    if base.endswith("_bridge"):
        base = base[:-len("_bridge")]
    if base.endswith("_rig"):
        base = base[:-len("_rig")]
    return _to_pascal_case(base) or "Untited"


def read_recent_fbx() -> list:
    """Прочитать bridge_last.json → список путей FBX."""
    try:
        if not os.path.exists(RECENT_JSON):
            return []
        with open(RECENT_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [p for p in data if isinstance(p, str) and os.path.exists(p)]
    except Exception as e:
        unreal.log_warning("[PROKLADKA] bridge_last.json read error: {}".format(e))
    return []


def _ensure_folder(folder_path: str) -> bool:
    """Создать папку в Content Browser если не существует."""
    ESS = unreal.EditorAssetSubsystem
    try:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        # does_asset_exist на папке возвращает False если нет ни одного ассета,
        # но сама папка может существовать. Создаём через create_asset → None
        # Правильный путь — create_new_asset или просто импорт.
        return True
    except Exception as e:
        unreal.log_warning("[PROKLADKA] ensure_folder: {}".format(e))
        return False


def _does_asset_exist(asset_path: str) -> bool:
    """Безопасная проверка существования ассета."""
    try:
        ESS = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        return bool(ESS.does_asset_exist(asset_path))
    except Exception:
        try:
            return bool(unreal.EditorAssetLibrary.does_asset_exist(asset_path))
        except Exception:
            return False


def _rename_asset(old_path: str, new_path: str) -> bool:
    """Переименовать ассет. Поддержка EditorAssetSubsystem и fallback на Library."""
    try:
        ESS = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        ESS.rename_asset(old_path, new_path)
        return True
    except Exception:
        try:
            unreal.EditorAssetLibrary.rename_asset(old_path, new_path)
            return True
        except Exception as e:
            unreal.log_warning("[PROKLADKA] rename failed {} → {}: {}".format(
                old_path, new_path, e))
            return False


def _sync_browser_to_folder(folder_path: str) -> None:
    """Показать папку в Content Browser."""
    try:
        ESS = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        ESS.sync_browser_to_objects([folder_path])
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# FBX IMPORT
# ════════════════════════════════════════════════════════════════════════════

def _safe_set(obj, prop, value):
    """set_editor_property с игнорированием несуществующих свойств (UE version compat)."""
    try:
        obj.set_editor_property(prop, value)
    except Exception:
        pass


def _make_import_task(fbx_path: str, dest_folder: str, name: str,
                      as_skeletal: bool, skeleton=None) -> unreal.AssetImportTask:
    """Создать и настроить AssetImportTask."""
    task = unreal.AssetImportTask()
    _safe_set(task, 'filename', _normalize_slashes(fbx_path))
    _safe_set(task, 'destination_path', dest_folder)
    _safe_set(task, 'destination_name', name)
    _safe_set(task, 'replace_existing', True)
    _safe_set(task, 'replace_existing_settings', True)
    _safe_set(task, 'automated', True)               # suppress dialogs
    _safe_set(task, 'automated_import_should_delete_type', False)  # not in all UE versions
    _safe_set(task, 'save', True)

    opts = unreal.FbxImportUI()
    _safe_set(opts, 'import_mesh', True)
    _safe_set(opts, 'import_as_skeletal', as_skeletal)
    _safe_set(opts, 'import_materials', False)
    _safe_set(opts, 'import_textures', False)
    _safe_set(opts, 'import_animations', False)

    if as_skeletal:
        sk = unreal.FbxSkeletalMeshImportData()
        _safe_set(sk, 'import_morph_targets', False)
        _safe_set(sk, 'update_skeleton_reference_pose', False)
        # Blender метры → UE сантиметры (×100)
        _safe_set(sk, 'import_uniform_scale', 100.0)
        _safe_set(opts, 'skeletal_mesh_import_data', sk)
        if skeleton is not None:
            _safe_set(opts, 'skeleton', skeleton)
    else:
        sm = unreal.FbxStaticMeshImportData()
        _safe_set(sm, 'combine_meshes', False)
        _safe_set(sm, 'generate_lightmap_uv', True)   # lightmap UV channel 1
        _safe_set(sm, 'auto_compute_lod_distances', True)
        # Blender метры → UE сантиметры (×100)
        _safe_set(sm, 'import_uniform_scale', 100.0)
        _safe_set(opts, 'static_mesh_import_data', sm)

    task.set_editor_property('options', opts)
    return task


def import_fbx(fbx_path: str, asset_name: str = "",
               mesh_type: str = "auto") -> dict:
    """
    Импортировать FBX. mesh_type: 'auto' | 'static' | 'skeletal'.
    Возвращает dict с результатом.
    """
    asset_name = asset_name or _asset_name_from_fbx(fbx_path)
    dest_folder = "{}/{}".format(IMPORT_BASE, asset_name)

    result = {
        "asset_name": asset_name,
        "fbx_path": fbx_path,
        "dest_folder": dest_folder,
        "imported_assets": [],
        "mesh_type": mesh_type,
        "errors": [],
    }

    # Auto-detect strategy
    actual_type = mesh_type
    if mesh_type == "auto":
        # 1. Проверить recipe.json рядом с FBX (rig-экспорт несёт has_animation/skeleton)
        recipe_path = fbx_path.replace(".fbx", "_recipe.json")
        if os.path.exists(recipe_path):
            try:
                with open(recipe_path, "r", encoding="utf-8") as f:
                    recipe = json.load(f)
                # Если в recipe есть bones → skeletal
                if recipe.get("parents") or recipe.get("constraints"):
                    actual_type = "skeletal"
                    unreal.log("[PROKLADKA] Auto-detect: skeletal (from recipe)")
                else:
                    actual_type = "static"
            except Exception:
                actual_type = "static"
        else:
            actual_type = "static"  # по умолчанию Static (VVERH пайплайн — окружение/props)

    # Импорт
    try:
        as_skeletal = (actual_type == "skeletal")
        task = _make_import_task(fbx_path, dest_folder, asset_name, as_skeletal)
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        asset_tools.import_asset_tasks([task])
        imported = list(task.imported_object_paths or [])
        result["imported_assets"] = imported

        # Auto-detect fallback: если Static ничего не дал, попробовать Skeletal
        if mesh_type == "auto" and not imported and actual_type == "static":
            unreal.log("[PROKLADKA] Static import empty, retrying as skeletal...")
            task2 = _make_import_task(fbx_path, dest_folder, asset_name, True)
            asset_tools.import_asset_tasks([task2])
            imported = list(task2.imported_object_paths or [])
            result["imported_assets"] = imported
            actual_type = "skeletal"
            result["mesh_type"] = "skeletal"

    except Exception as e:
        result["errors"].append("FBX import failed: {}".format(e))
        unreal.log_error("[PROKLADKA] FBX import error: {}".format(e))

    return result


# ════════════════════════════════════════════════════════════════════════════
# TEXTURES IMPORT
# ════════════════════════════════════════════════════════════════════════════

def detect_pbr_slot(filename: str) -> str:
    """Определить PBR слот по имени файла. Возвращает ключ PBR_SLOTS или ''."""
    name = os.path.splitext(os.path.basename(filename))[0].lower()
    compact = re.sub(r'[^a-z0-9]', '', name)
    for key in PBR_SLOTS:
        if key in compact:
            return key
    return ""


def import_textures(tex_paths: list, asset_name: str,
                    dest_folder: str = "") -> dict:
    """
    Импортировать текстуры. Возвращает {tex_path: asset_path}.
    Пропускает файлы которые не текстуры (по расширению).
    """
    dest_folder = dest_folder or "{}/{}".format(IMPORT_BASE, asset_name)
    out = {}
    tex_exts = ('.png', '.jpg', '.jpeg', '.tga', '.exr', '.tif', '.tiff', '.psd', '.hdr')

    for tex_path in tex_paths:
        if not tex_path.lower().endswith(tex_exts):
            continue
        slot = detect_pbr_slot(tex_path)
        if not slot:
            continue  # не-PBR текстура — пропустить

        # Имя: T_<asset>_<slot>
        clean_name = "T_{}_{}".format(asset_name, slot.capitalize())
        try:
            task = unreal.AssetImportTask()
            task.set_editor_property('filename', _normalize_slashes(tex_path))
            task.set_editor_property('destination_path', dest_folder)
            task.set_editor_property('destination_name', clean_name)
            task.set_editor_property('replace_existing', True)
            task.set_editor_property('automated', True)
            task.set_editor_property('save', True)
            # Текстуры не имеют FbxImportUI — обычный texture import
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

            imported = list(task.imported_object_paths or [])
            if imported:
                out[tex_path] = imported[0]
        except Exception as e:
            unreal.log_warning("[PROKLADKA] texture import failed {}: {}".format(tex_path, e))

    return out


# ════════════════════════════════════════════════════════════════════════════
# MATERIAL INSTANCE CREATION
# ════════════════════════════════════════════════════════════════════════════

def create_material_instance(asset_name: str, textures: dict,
                             dest_folder: str = "",
                             master_material_path: str = "/Game/MasterPBR_M") -> str:
    """
    Создать Material Instance из master material, назначить текстуры.
    textures: {tex_path: asset_path} из import_textures.
    Возвращает путь созданного MI или "" при ошибке.
    """
    dest_folder = dest_folder or "{}/{}".format(IMPORT_BASE, asset_name)
    mi_path = "{}/MI_{}".format(dest_folder, asset_name)

    try:
        master = unreal.load_asset(master_material_path)
    except Exception:
        master = None
    if not master:
        unreal.log_warning(
            "[PROKLADKA] Master material {} not found — skipping MI creation".format(
                master_material_path))
        return ""

    try:
        MEL = unreal.MaterialEditingLibrary
        # Удалить существующий MI если есть (иначе create упадёт)
        if _does_asset_exist(mi_path):
            try:
                unreal.EditorAssetLibrary.delete_asset(mi_path)
            except Exception:
                pass

        mi = MEL.create_material_instance(dest_folder, "MI_" + asset_name, master)
        if not mi:
            return ""

        # Назначить текстуры по слотам
        for tex_path, tex_asset_path in textures.items():
            slot = detect_pbr_slot(tex_path)
            if not slot:
                continue
            param_name = PBR_SLOTS[slot]
            try:
                tex_obj = unreal.load_asset(tex_asset_path)
                if tex_obj:
                    MEL.set_material_instance_texture_parameter_value(mi, param_name, tex_obj)
            except Exception as e:
                unreal.log_warning("[PROKLADKA] set tex param {} failed: {}".format(
                    param_name, e))

        return mi_path
    except Exception as e:
        unreal.log_warning("[PROKLADKA] Material instance creation failed: {}".format(e))
        return ""


def assign_material_to_meshes(mesh_asset_paths: list, material_path: str) -> int:
    """Назначить материал на slot 0 каждого Static/Skeletal Mesh."""
    if not material_path:
        return 0
    assigned = 0
    try:
        mat = unreal.load_asset(material_path)
        if not mat:
            return 0
        for mesh_path in mesh_asset_paths:
            try:
                mesh = unreal.load_asset(mesh_path)
                if mesh:
                    # StaticMesh / SkeletalMesh оба имеют set_material(slot, material)
                    mesh.set_material(0, mat)
                    assigned += 1
            except Exception:
                pass
    except Exception as e:
        unreal.log_warning("[PROKLADKA] assign material failed: {}".format(e))
    return assigned


# ════════════════════════════════════════════════════════════════════════════
# NAMING — apply UE convention
# ════════════════════════════════════════════════════════════════════════════

def apply_ue_naming(asset_path: str, asset_type: str) -> str:
    """
    Переименовать ассет с префиксом SM_/SK_/T_/MI_/Skeleton_.
    PascalCase для имени. Возвращает новый путь.
    """
    parts = asset_path.split("/")
    old_name = parts[-1]
    prefix = PREFIX.get(asset_type, "")
    if not prefix:
        return asset_path

    # Если уже правильно назван — не трогаем
    if old_name.startswith(prefix):
        return asset_path

    # Для текстур: keep slot info, добавить префикс
    if asset_type == "texture":
        # old_name: asset_Albedo → T_Asset_Albedo
        new_name = "T_" + _to_pascal_case(old_name.replace("_", " "))
        # Заменить пробелы на _ обратно
        new_name = new_name.replace(" ", "_")
    else:
        # PascalCase: wing_main_geo → WingMainGeo
        base = old_name
        # убрать типовой суффикс _geo/_grp/_skel/_jnt/_ctl
        for suf in ("_geo", "_grp", "_skel", "_jnt", "_ctl"):
            if base.lower().endswith(suf):
                base = base[:-len(suf)]
        new_name = prefix + _to_pascal_case(base)

    new_path = "/".join(parts[:-1] + [new_name])
    if new_path == asset_path:
        return asset_path
    if _does_asset_exist(new_path):
        unreal.log("[PROKLADKA] {} already exists, keeping original".format(new_path))
        return asset_path

    if _rename_asset(asset_path, new_path):
        return new_path
    return asset_path


# ════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════

def process_bridge_import(fbx_path: str,
                          mesh_type: str = "auto",
                          import_textures_alongside: bool = True,
                          master_material_path: str = "/Game/MasterPBR_M") -> dict:
    """
    Полный импорт FBX:
      1. Import FBX (Static/Skeletal)
      2. Import PBR textures (если есть рядом)
      3. Create Material Instance
      4. Assign material to meshes
      5. Apply UE naming convention
    """
    asset_name = _asset_name_from_fbx(fbx_path)
    unreal.log("[PROKLADKA] Importing bridge FBX: {} (as '{}')".format(fbx_path, asset_name))

    result = {
        "fbx_path": fbx_path,
        "asset_name": asset_name,
        "mesh_type": mesh_type,
        "imported_meshes": [],
        "imported_textures": [],
        "material_instance": "",
        "final_paths": [],
        "errors": [],
    }

    # 1. Import FBX
    fbx_result = import_fbx(fbx_path, asset_name, mesh_type)
    result["errors"].extend(fbx_result.get("errors", []))
    imported = fbx_result.get("imported_assets", [])
    if not imported:
        unreal.log_error("[PROKLADKA] No assets imported from FBX")
        return result

    # 2. Import textures (рядом с FBX)
    tex_assets = {}
    if import_textures_alongside:
        fbx_dir = os.path.dirname(fbx_path)
        # Ищем текстуры рядом с FBX с тем же asset-префиксом
        asset_basename = os.path.splitext(os.path.basename(fbx_path))[0]
        asset_prefix = asset_basename.replace("_bridge", "").replace("_rig", "")
        candidate_tex = []
        try:
            for f in os.listdir(fbx_dir):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tga', '.exr', '.tif', '.psd')):
                    if asset_prefix.lower() in f.lower():
                        candidate_tex.append(os.path.join(fbx_dir, f))
        except Exception:
            pass

        if candidate_tex:
            tex_assets = import_textures(candidate_tex, asset_name)
            result["imported_textures"] = list(tex_assets.values())

    # 3. Material Instance
    if tex_assets:
        mi_path = create_material_instance(
            asset_name, tex_assets,
            master_material_path=master_material_path)
        result["material_instance"] = mi_path
        if mi_path:
            # 4. Assign material
            meshes = [p for p in imported if 'Mesh' in str(type(unreal.load_asset(p)).__name__)]
            assign_material_to_meshes(imported, mi_path)

    # 5. Apply UE naming to all imported assets
    renamed = []
    for path in imported + result["imported_textures"]:
        if not path:
            continue
        # определить тип
        asset_obj = None
        try:
            asset_obj = unreal.load_asset(path)
        except Exception:
            pass
        if not asset_obj:
            continue

        cls_name = asset_obj.__class__.__name__
        if 'StaticMesh' in cls_name:
            atype = "static_mesh"
        elif 'SkeletalMesh' in cls_name:
            atype = "skeletal_mesh"
        elif 'Skeleton' in cls_name:
            atype = "skeleton"
        elif 'Texture' in cls_name or 'Image' in cls_name:
            atype = "texture"
        else:
            atype = ""

        new_path = apply_ue_naming(path, atype)
        renamed.append(new_path)

    result["final_paths"] = renamed

    # Sync Content Browser
    if renamed:
        _sync_browser_to_folder("/".join(renamed[0].split("/")[:-1]))

    return result


# ════════════════════════════════════════════════════════════════════════════
# UI — popup + file picker
# ════════════════════════════════════════════════════════════════════════════

def _pick_fbx_dialog() -> str:
    """Показать popup выбора FBX. Возвращает путь или ''."""
    recent = read_recent_fbx()

    # Сформировать сообщение с recent
    msg_lines = ["Выберите FBX для импорта:"]
    if recent:
        msg_lines.append("")
        msg_lines.append("Recent exports:")
        for i, p in enumerate(recent[:5], 1):
            msg_lines.append("  {}. {}".format(i, os.path.basename(p)))
    msg = "\n".join(msg_lines)

    try:
        result = unreal.EditorDialog.show_message(
            "PROKLADKA Import",
            msg,
            "OK",
            "Cancel",
            "Choose FBX...",
        )
    except Exception:
        result = "OK"

    if result == "Choose FBX...":
        # Открыть file picker
        try:
            path = unreal.EditorDialog.open_file("Select FBX", "FBX (*.fbx)|*.fbx", False)
            return path or ""
        except Exception as e:
            unreal.log_warning("[PROKLADKA] file picker error: {}".format(e))
            return ""
    elif result == "Cancel" or not result:
        return ""

    # OK → берём первый из recent
    if recent:
        return recent[0]

    # Нет recent → file picker
    try:
        return unreal.EditorDialog.open_file("Select FBX", "FBX (*.fbx)|*.fbx", False) or ""
    except Exception:
        return ""


def _pick_mesh_type_dialog() -> str:
    """Спросить как импортировать. Возвращает 'auto'/'static'/'skeletal'."""
    try:
        result = unreal.EditorDialog.show_message(
            "PROKLADKA — Mesh type",
            "Как импортировать FBX?",
            "Auto (detect)",
            "Force Static",
            "Force Skeletal",
            "Cancel",
        )
    except Exception:
        return "auto"

    if result == "Force Static":
        return "static"
    if result == "Force Skeletal":
        return "skeletal"
    if result == "Cancel":
        return ""
    return "auto"


# ════════════════════════════════════════════════════════════════════════════
# UI REGISTRATION — toolbar + Window submenu (UE 5.7+ ToolMenus API)
# ════════════════════════════════════════════════════════════════════════════

_MENU_OWNER = "PROKLADKA"
_SECTION_NAME = "ProkladkaSection"
_WINDOW_MENU = "LevelEditor.MainMenu.Window"
_TOOLBAR_CANDIDATES = (
    "LevelEditor.LevelEditorToolBar.User",        # расширяемая зона тулбара
    "LevelEditor.LevelEditorToolBar.PlayToolBar",  # play-тулбар (fallback)
    "LevelEditor.LevelEditorToolBar",               # весь тулбар (last resort)
)


def _make_entry(name, label, tooltip, command) -> unreal.ToolMenuEntry:
    """ToolMenuEntry с python-командой (UE 5.7+: label/tooltip/command — методы)."""
    entry = unreal.ToolMenuEntry(
        name=name,
        type=unreal.MultiBlockType.MENU_ENTRY,
        insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.FIRST),
    )
    entry.set_label(label)
    entry.set_tool_tip(tooltip)
    entry.set_string_command(
        type=unreal.ToolMenuStringCommandType.PYTHON,
        string=command,
        custom_type=unreal.Name(""),
    )
    return entry


def register_menu(menu_action_script: str = "") -> bool:
    """
    Регистрация подменю Window → PROKLADKA:
      Open Panel / Import Bridge FBX / Settings Folder.
    Возвращает True при успехе.
    """
    try:
        menus = unreal.ToolMenus.get()
        window_menu = menus.find_menu(_WINDOW_MENU)
        if not window_menu:
            window_menu = menus.extend_menu(_WINDOW_MENU)
        if not window_menu:
            unreal.log_warning("[PROKLADKA] Window menu not found")
            return False

        # Подменю PROKLADKA (если уже есть — переиспользуем)
        try:
            submenu = window_menu.add_sub_menu(
                _MENU_OWNER,           # owner
                _SECTION_NAME,         # section
                "PROKLADKA",           # имя подменю
                "PROKLADKA",           # label
                "PROKLADKA FBX Bridge (Blender/Maya/Houdini → UE)",
            )
        except Exception:
            submenu = menus.find_menu(_WINDOW_MENU + ".PROKLADKA")

        if not submenu:
            unreal.log_warning("[PROKLADKA] submenu creation failed")
            return False

        submenu.add_menu_entry(_SECTION_NAME, _make_entry(
            "ProkladkaOpenPanel", "Open Panel",
            "Open PROKLADKA dockable panel (Editor Utility Widget)",
            "import prokladka; prokladka.open_panel()"))
        submenu.add_menu_entry(_SECTION_NAME, _make_entry(
            "ProkladkaImportBridge", "Import Bridge FBX",
            "Import FBX from Blender/Maya PROKLADKA bridge (popup flow)",
            "import prokladka; prokladka.run_import_dialog()"))
        submenu.add_menu_entry(_SECTION_NAME, _make_entry(
            "ProkladkaSettingsFolder", "Settings Folder",
            "Open C:/temp (settings + bridge_last.json)",
            "import os; os.startfile(r'C:\\temp')"))

        menus.refresh_all_widgets()
        unreal.log("[PROKLADKA] Window → PROKLADKA submenu registered")
        return True

    except Exception as e:
        unreal.log_warning("[PROKLADKA] Menu registration failed: {}".format(e))
        return False


def register_toolbar() -> bool:
    """
    Toolbar кнопка PROKLADKA в Level Editor (открывает панель).
    Пробует несколько целевых меню — от расширяемой User-зоны до всего тулбара.
    """
    try:
        menus = unreal.ToolMenus.get()

        entry = unreal.ToolMenuEntry(
            name="ProkladkaToolbarButton",
            type=unreal.MultiBlockType.TOOL_BAR_BUTTON,
            insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.FIRST),
        )
        entry.set_label("PROKLADKA")
        entry.set_tool_tip("Open PROKLADKA Bridge Panel")
        entry.set_string_command(
            type=unreal.ToolMenuStringCommandType.PYTHON,
            string="import prokladka; prokladka.open_panel()",
            custom_type=unreal.Name(""),
        )
        # Иконка опциональна — без неё UE покажет label
        try:
            entry.set_icon("PlayWorld", "PlayWorld.Enter")
        except Exception:
            pass

        for menu_name in _TOOLBAR_CANDIDATES:
            toolbar = menus.find_menu(menu_name)
            if not toolbar:
                continue
            try:
                toolbar.add_menu_entry("ProkladkaToolbarSection", entry)
                menus.refresh_all_widgets()
                unreal.log("[PROKLADKA] Toolbar button registered: {}".format(menu_name))
                return True
            except Exception as e:
                unreal.log_warning("[PROKLADKA] Toolbar {} failed: {}".format(menu_name, e))

        unreal.log_warning("[PROKLADKA] No toolbar menu found — use Window → PROKLADKA")
        return False

    except Exception as e:
        unreal.log_warning("[PROKLADKA] Toolbar registration failed: {}".format(e))
        return False


def unregister_menu() -> bool:
    """Снять регистрацию UI (подменю + toolbar)."""
    ok = True
    try:
        menus = unreal.ToolMenus.get()
        menus.remove_menu_section(_WINDOW_MENU + ".PROKLADKA", _SECTION_NAME)
        for menu_name in _TOOLBAR_CANDIDATES:
            try:
                menus.remove_menu_section(menu_name, "ProkladkaToolbarSection")
            except Exception:
                pass
        menus.refresh_all_widgets()
    except Exception as e:
        unreal.log_warning("[PROKLADKA] Menu unregister failed: {}".format(e))
        ok = False
    return ok


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINT (для вызова из menu_action.py или из Output Log)
# ════════════════════════════════════════════════════════════════════════════

def run_import_dialog() -> None:
    """Полный flow: popup FBX → popup type → import. Главная точка входа."""
    fbx_path = _pick_fbx_dialog()
    if not fbx_path:
        return

    mesh_type = _pick_mesh_type_dialog()
    if not mesh_type:
        return  # Cancel

    result = process_bridge_import(fbx_path, mesh_type=mesh_type)
    _report_result(result)


def _report_result(result: dict) -> None:
    """Вывести результат в Output Log и popup."""
    if result.get("errors"):
        msg = "PROKLADKA import завершился с ошибками:\n\n"
        for err in result["errors"][:5]:
            msg += "  • " + str(err) + "\n"
        try:
            unreal.EditorDialog.show_message("PROKLADKA", msg, "OK")
        except Exception:
            pass
        unreal.log_error(msg)
        return

    final = result.get("final_paths", [])
    if final:
        msg = "Импортировано ассетов: {}\n\n".format(len(final))
        for p in final[:10]:
            msg += "  • " + p + "\n"
        try:
            unreal.EditorDialog.show_message("PROKLADKA", msg, "OK")
        except Exception:
            pass
        unreal.log("[PROKLADKA] " + msg.replace("\n", " | "))
    else:
        unreal.log_warning("[PROKLADKA] Nothing imported")


if __name__ == "__main__":
    # При запуске через Tools → Run Python Script
    run_import_dialog()
