# -*- coding: utf-8 -*-
"""
bridge_qt.py — PROKLADKA (Maya сторона, Qt-версия).

FBX-мост между Blender и Maya. Симметричен Blender-аддону PROKLADKA.

Архитектура:
  - Бизнес-логика и UI в одном файле. Чистый PySide2/PySide6.
  - Стилизован под STUKACH (Blender-dark QSS) — готов к встраиванию как
    вкладка/секция в окно STUKACH.
  - Запуск: launch() — отдельное окно; BridgePanel(parent) — встроенный виджет.

Совместимость: Maya 2022+ (PySide2) / Maya 2025+ (PySide6).
"""
from __future__ import annotations

import os
import re
import json
import contextlib

import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui

try:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import Qt
    from shiboken2 import wrapInstance
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Qt
    from shiboken6 import wrapInstance


# Импорт rig-модулей (extract/reconstruct). Папка скрипта должна быть в sys.path.
import os as _os
_THIS_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _THIS_DIR not in __import__('sys').path:
    __import__('sys').path.insert(0, _THIS_DIR)

import rig_maya as _rig_maya
import rig_recipe as _rig_recipe


# ════════════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════════════════════

TEMP_DIRECTORY = r"C:\temp"
RECENT_JSON    = os.path.join(TEMP_DIRECTORY, "bridge_last.json")
RECENT_MAX     = 5

# Состояние между вызовами UI
LAST_IMPORTED_OBJECTS = []


# ════════════════════════════════════════════════════════════════════════════
# БИЗНЕС-ЛОГИКА (чистый maya.cmds, без Qt)
# ════════════════════════════════════════════════════════════════════════════

# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_asset_name() -> str:
    """Имя ассета из сцены: имя файла без расширения, fallback 'untitled'."""
    path = cmds.file(query=True, sceneName=True) or ""
    if path:
        name = os.path.splitext(os.path.basename(path))[0]
    else:
        name = "untitled"
    return name.replace(".", "_").replace(" ", "_").lower() or "untitled"


def _current_export_path() -> str:
    """Путь экспорта по умолчанию: C:/temp/<asset>_bridge.fbx"""
    return "C:/temp/{}_bridge.fbx".format(_get_asset_name())


def _read_recent_paths():
    """Список недавних FBX: bridge_last.json + fallback на *_bridge.fbx по mtime."""
    paths = []
    try:
        if os.path.exists(RECENT_JSON):
            with open(RECENT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    paths = [p for p in data if isinstance(p, str)]
    except Exception:
        pass
    if not paths and os.path.exists(TEMP_DIRECTORY):
        try:
            files = [os.path.join(TEMP_DIRECTORY, f) for f in os.listdir(TEMP_DIRECTORY)
                     if f.lower().endswith("_bridge.fbx")]
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            paths = files[:RECENT_MAX]
        except Exception:
            pass
    return [p for p in paths if os.path.exists(p)]


def _append_to_recent_json(path: str) -> None:
    """Добавить path в начало bridge_last.json, максимум RECENT_MAX, уникально."""
    try:
        recent = []
        if os.path.exists(RECENT_JSON):
            with open(RECENT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    recent = [p for p in data if isinstance(p, str)]
        norm = path.replace("\\", "/")
        recent = [p for p in recent if p.replace("\\", "/") != norm]
        recent.insert(0, norm)
        recent = recent[:RECENT_MAX]
        if not os.path.exists(TEMP_DIRECTORY):
            os.makedirs(TEMP_DIRECTORY)
        with open(RECENT_JSON, "w", encoding="utf-8") as f:
            json.dump(recent, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _ensure_maya_units_meters() -> None:
    """VVERH: Units=метры. Иерархию не трогает."""
    try:
        current = cmds.currentUnit(query=True, linear=True)
        if current != "meter":
            cmds.currentUnit(linear="meter")
            cmds.inViewMessage(amg="<hl>Maya units set to meter</hl>", pos="botLeft", fade=True)
    except Exception as e:
        cmds.warning("Не удалось проверить/установить units=meter: {}".format(e))


# ── Naming presets (симметрично с Blender) ──────────────────────────────────

# Те же пресеты что в Blender addon (_DEFAULT_PRESETS)
NAMING_PRESETS = {
    "Default": {
        "suffix_mesh": "_geo", "suffix_grp": "_grp", "suffix_skel": "_skel",
        "suffix_jnt": "_jnt", "suffix_ctl": "_ctl",
        "lowercase": True, "dots": True,
    },
    "Plain lowercase": {
        "suffix_mesh": "", "suffix_grp": "", "suffix_skel": "",
        "suffix_jnt": "", "suffix_ctl": "",
        "lowercase": True, "dots": True,
    },
    "Unreal": {
        "suffix_mesh": "_Mesh", "suffix_grp": "", "suffix_skel": "_SkelMesh",
        "suffix_jnt": "_jnt", "suffix_ctl": "_ctl",
        "lowercase": False, "dots": True,
    },
    "Dots only": {
        "suffix_mesh": "", "suffix_grp": "", "suffix_skel": "",
        "suffix_jnt": "", "suffix_ctl": "",
        "lowercase": False, "dots": True,
    },
    "Rig": {
        "suffix_mesh": "_geo", "suffix_grp": "_grp", "suffix_skel": "_skel",
        "suffix_jnt": "_jnt", "suffix_ctl": "_ctl",
        "lowercase": True, "dots": True,
    },
}


def _safe_name(name: str, dots: bool = True, lowercase: bool = True) -> str:
    """Нормализация имени: точки/пробелы → _, опционально lowercase."""
    if dots:
        name = name.replace('.', '_').replace(' ', '_').replace('-', '_')
    if lowercase:
        name = name.lower()
    return name


def _all_suffixes(preset: dict) -> list:
    """Все суффиксы пресета для отрезания старых."""
    out = []
    for key in ("suffix_mesh", "suffix_grp", "suffix_skel", "suffix_jnt", "suffix_ctl"):
        s = preset.get(key, "")
        if s:
            out.append(s)
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _detect_obj_type(obj: str) -> str:
    """Определить тип объекта Maya для выбора суффикса."""
    try:
        shapes = cmds.listRelatives(obj, shapes=True, fullPath=True) or []
        for s in shapes:
            nt = cmds.nodeType(s)
            if nt == "mesh":
                return "suffix_mesh"
            elif nt == "locator":
                return "suffix_grp"
        # Нет shape → группа
        return "suffix_grp"
    except Exception:
        return "suffix_grp"


def _fbxasc_cleanup(obj: str) -> str:
    """FBXASC cleanup — исправить имена после FBX import."""
    if "FBXASC" not in obj:
        return obj
    parts = obj.split("FBXASC")[0].rstrip(".")
    base, *suf = parts.split(".")
    num = suf[0] if suf else "1"
    try:
        return cmds.rename(obj, "{}_{}".format(base, num))
    except Exception:
        cmds.warning("Не удалось переименовать {}".format(obj))
        return obj


def apply_naming_preset(objs, preset_name: str = "Default") -> int:
    """
    Применить naming preset к списку объектов. Иерархию не трогает.
    Возвращает количество переименованных.
    """
    preset = NAMING_PRESETS.get(preset_name, NAMING_PRESETS["Default"])
    suffixes = _all_suffixes(preset)
    renamed = 0

    for obj in objs:
        # 1) FBXASC cleanup
        new_obj = _fbxasc_cleanup(obj)

        # 2) Нормализация
        base = _safe_name(new_obj, dots=preset.get("dots", True),
                          lowercase=preset.get("lowercase", True))

        # 3) Отрезать старый суффикс если есть
        for s in suffixes:
            if base.endswith(s):
                base = base[:-len(s)]
                break

        # 4) Определить тип и добавить правильный суффикс
        type_key = _detect_obj_type(new_obj)
        suffix = preset.get(type_key, "")
        if suffix and not base.endswith(suffix):
            base = base + suffix

        # 5) Переименовать если изменилось
        if base != new_obj:
            try:
                new_obj = cmds.rename(new_obj, base)
                renamed += 1
            except Exception:
                pass

    return renamed


def rename_fbxasc_objects(preset_name: str = "Default"):
    """Применить naming preset к выделению (или всем с FBXASC)."""
    # Приоритет: выделение; если пусто — все с FBXASC
    sel = cmds.ls(selection=True, type="transform") or []
    if not sel:
        sel = [o for o in cmds.ls(type="transform") if "FBXASC" in o]

    if not sel:
        cmds.warning("Нет выделения и нет объектов с FBXASC.")
        return

    renamed = apply_naming_preset(sel, preset_name)
    cmds.inViewMessage(
        amg="<hl>{}: {} renamed</hl>".format(preset_name, renamed),
        pos="botLeft", fade=True)


# ── Universal UV renamer ────────────────────────────────────────────────────
#
# Конвенции имён UV-сетов в разных DCC. Primary — целевое имя для главного UV.
# secondary_target — целевое имя для вторичных UV (None = не трогать).
# Для Unreal: primary остаётся (текстурный), secondary → LightmassUV (lightmap).

UV_CONVENTIONS = {
    "Maya":     {"primary": "map1",        "secondary": None},
    "Blender":  {"primary": "UVMap",       "secondary": None},
    "Houdini":  {"primary": "uv",          "secondary": None},
    "Unreal":   {"primary": None,          "secondary": "LightmassUV"},
    "Custom":   {"primary": None,          "secondary": None},  # берётся из custom_name
}


def rename_uv_universal(target: str, custom: str = "") -> dict:
    """
    Переименовать primary UV set выделенных мешей под конвенцию target.
    target — ключ из UV_CONVENTIONS ('Maya'/'Blender'/'Houdini'/'Unreal'/'Custom').
    custom — имя для Custom пресета.

    Алгоритм:
      - если 1 UV → переименовать в target_primary
      - если N>1 → переименовать primary (первый в списке) в target_primary,
                   вторичные НЕ трогать (только сигнал)
      - для Unreal: если N>=2, secondary[0] → LightmassUV, primary не трогать

    Возвращает dict:
      meshes_processed, renamed_count, multi_uv_meshes, multi_uv_list
    """
    conv = UV_CONVENTIONS.get(target, UV_CONVENTIONS["Maya"])

    # Определить целевые имена
    if target == "Custom":
        primary_target = custom.strip() or "map1"
        secondary_target = None
    else:
        primary_target = conv["primary"]
        secondary_target = conv["secondary"]

    selection = cmds.ls(selection=True, dag=True, type="mesh") or []
    stats = {
        "meshes_processed": 0,
        "renamed_count": 0,
        "multi_uv_meshes": 0,
        "multi_uv_list": [],
        "errors": [],
    }
    if not selection:
        cmds.warning("Нет выделенных мешей")
        return stats

    for mesh in selection:
        stats["meshes_processed"] += 1
        try:
            uv_sets = cmds.polyUVSet(mesh, query=True, allUVSets=True) or []
            if not uv_sets:
                continue

            short_name = mesh.split("|")[-1]

            if len(uv_sets) == 1:
                # Один UV — переименовать в primary_target
                if primary_target:
                    old = uv_sets[0]
                    if old != primary_target:
                        try:
                            cmds.polyUVSet(mesh, rename=True,
                                           uvSet=old, newUVSet=primary_target)
                            stats["renamed_count"] += 1
                        except Exception as e:
                            stats["errors"].append("{}: {}".format(short_name, e))
            else:
                # N > 1: primary → target, secondary по стратегии
                if primary_target:
                    old = uv_sets[0]
                    if old != primary_target:
                        try:
                            cmds.polyUVSet(mesh, rename=True,
                                           uvSet=old, newUVSet=primary_target)
                            stats["renamed_count"] += 1
                        except Exception as e:
                            stats["errors"].append("{}: {}".format(short_name, e))

                # Стратегия Unreal: secondary[0] → LightmassUV
                if secondary_target and len(uv_sets) >= 2:
                    old_sec = uv_sets[1]
                    if old_sec != secondary_target:
                        try:
                            cmds.polyUVSet(mesh, rename=True,
                                           uvSet=old_sec, newUVSet=secondary_target)
                            stats["renamed_count"] += 1
                        except Exception as e:
                            stats["errors"].append("{}: {}".format(short_name, e))

                # Сигнал: меш имеет доп. UV sets (которые мы не переименовали)
                untouched = len(uv_sets) - 1
                if untouched > 0 and not secondary_target:
                    stats["multi_uv_meshes"] += 1
                    stats["multi_uv_list"].append(short_name)
        except Exception as e:
            stats["errors"].append("{}: {}".format(mesh, e))

    return stats


# Обратная совместимость — старая функция как алиас
def rename_uv_set_to_map1_all_selected():
    """Алиас к rename_uv_universal('Maya'). Оставлен для совместимости."""
    rename_uv_universal("Maya")


# ── Set Raw colorSpace для normal-map file nodes ────────────────────────────

def set_color_space_for_normal_maps():
    sel_shapes = cmds.ls(selection=True, dag=True, shapes=True)
    if not sel_shapes:
        cmds.warning("No objects/shapes selected!")
        return
    shading_engines = cmds.listConnections(sel_shapes, type='shadingEngine') or []
    if not shading_engines:
        cmds.warning("No shading engines found.")
        return
    file_nodes = set()
    for se in shading_engines:
        for attr in ("surfaceShader", "displacementShader", "volumeShader"):
            mats = cmds.listConnections("{}.{}".format(se, attr), source=True, destination=False) or []
            for m in mats:
                hist = cmds.listHistory(m, future=False) or []
                for n in hist:
                    if cmds.nodeType(n) == "file":
                        file_nodes.add(n)
    if not file_nodes:
        cmds.warning("No file nodes found.")
        return
    changed = 0
    for fn in file_nodes:
        path = cmds.getAttr(fn + ".fileTextureName") or ""
        is_norm = False
        conns = cmds.listConnections(fn, destination=True, source=False, plugs=True) or []
        for c in conns:
            n = c.split('.')[0]
            if cmds.nodeType(n) in ("bump2d", "bump3d", "aiNormalMap"):
                is_norm = True
                break
        if "normal" in path.lower():
            is_norm = True
        if is_norm:
            try:
                cmds.setAttr(fn + ".colorSpace", "Raw", type="string")
                changed += 1
            except Exception as e:
                cmds.warning("Не удалось установить Raw для {}: {}".format(fn, e))
    if changed == 0:
        cmds.warning("Не найдено нормал-мапов для установки Raw.")


# ── FBX Export/Import ───────────────────────────────────────────────────────

def export_selected_to_fbx(plain: bool = False) -> None:
    """
    Экспорт выделения в FBX.
    legacy/plain (escape hatch): голый FBXExport, без правок units.
    Симметрично с Legacy scale в Blender.
    """
    if not cmds.pluginInfo('fbxmaya', query=True, loaded=True):
        cmds.loadPlugin('fbxmaya')
    path = _current_export_path()
    folder = os.path.dirname(path)
    if not os.path.exists(folder):
        os.makedirs(folder)
    try:
        mel.eval("FBXResetExport;")
    except Exception:
        pass
    mel.eval('FBXExport -f "{}" -s;'.format(path.replace("\\", "/")))
    _append_to_recent_json(path)
    cmds.inViewMessage(amg="<hl>Exported to {}</hl>".format(path), pos="botLeft", fade=True)


def _check_and_fix_object_names(objs):
    """FBXASC cleanup для свеже-импортированных объектов."""
    updated = []
    for obj in objs:
        new_obj = obj
        if "FBXASC" in obj:
            parts = obj.split("FBXASC")[0].rstrip(".")
            base, *suf = parts.split(".")
            num = suf[0] if suf else "1"
            try:
                new_obj = cmds.rename(obj, "{}_{}".format(base, num))
            except Exception:
                cmds.warning("Не удалось переименовать {}".format(obj))
        updated.append(new_obj)
    return updated


def convert_locators_to_groups(objs) -> None:
    """
    Превращает локаторы в группы: удаляет locator shape, оставляя transform.
    Иерархия (parent/children), transform-значения и имена НЕ трогаются.
    """
    for o in objs:
        for s in cmds.listRelatives(o, shapes=True, fullPath=True) or []:
            try:
                if cmds.objectType(s) == "locator":
                    cmds.delete(s)
            except Exception:
                pass
        for d in cmds.listRelatives(o, allDescendents=True, fullPath=True) or []:
            if cmds.objectType(d) == "transform":
                for s in cmds.listRelatives(d, shapes=True, fullPath=True) or []:
                    try:
                        if cmds.objectType(s) == "locator":
                            cmds.delete(s)
                    except Exception:
                        pass


def recent_history_report() -> str:
    """Форматированная история экспортов (новые сверху)."""
    try:
        with open(RECENT_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid = [p for p in (data if isinstance(data, list) else [])
                 if isinstance(p, str) and os.path.exists(p)]
        if not valid:
            return "Export history is empty."
        import time
        lines = []
        for i, p in enumerate(valid, 1):
            try:
                st = os.stat(p)
                stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
                lines.append("{}. {} | {} KB | {}".format(
                    i, os.path.basename(p), max(1, st.st_size // 1024), stamp))
            except Exception:
                lines.append("{}. {} | (unavailable)".format(i, p))
        return chr(10).join(lines)
    except Exception:
        return "Export history is empty."

def clear_recent_json() -> None:
    """Очистить общий список экспортов (bridge_last.json)."""
    try:
        with open(RECENT_JSON, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
    except Exception:
        pass


def import_fbx(path: str, plain: bool, unlock_normals: bool,
               loc_to_grp: bool) -> None:
    """
    Импорт FBX. units=meter (если не plain), иерархия не нарушается.

    Использует cmds.file() вместо MEL FBXImport — MEL-путь терял меши
    (приходили только группы). cmds.file() с явными опциями работает корректно.
    """
    global LAST_IMPORTED_OBJECTS

    if not os.path.exists(path):
        cmds.warning("Файл не найден: {}".format(path))
        return

    if not plain:
        _ensure_maya_units_meters()

    before = set(cmds.ls(type="transform"))

    # Unlock normals опция (через MEL до импорта)
    try:
        mel.eval('FBXImportUnlockNormals -v {};'.format(
            "true" if unlock_normals else "false"))
    except Exception:
        pass

    # Импорт через cmds.file() — надёжнее чем MEL FBXImport
    clean_path = path.replace("\\", "/")
    cmds.file(clean_path, i=True, type="FBX", ignoreVersion=True,
              mergeNamespacesOnClash=False, options="mo=1", pr=True)

    cmds.inViewMessage(amg="<hl>Imported {}</hl>".format(path), pos="botLeft", fade=True)

    after = set(cmds.ls(type="transform"))
    new = list(after - before)
    LAST_IMPORTED_OBJECTS = _check_and_fix_object_names(new)

    if loc_to_grp:
        convert_locators_to_groups(LAST_IMPORTED_OBJECTS)
        cmds.inViewMessage(amg="<hl>Locators converted to groups</hl>",
                           pos="botLeft", fade=True)


def apply_identity_transform(flags, unlock_soften: bool, loc_to_grp: bool) -> None:
    """
    Применить makeIdentity (T/R/S по flags dict) на выделении или LAST_IMPORTED_OBJECTS.
    Иерархию не меняет.
    """
    sels = cmds.ls(selection=True, type="transform")
    if sels:
        targets, label = sels, "selected objects"
    elif LAST_IMPORTED_OBJECTS:
        targets, label = LAST_IMPORTED_OBJECTS, "imported objects"
    else:
        cmds.warning("Нечего преобразовывать.")
        return

    t = int(flags.get("translate", False))
    r = int(flags.get("rotate", True))
    s = int(flags.get("scale", False))

    for o in targets:
        try:
            cmds.makeIdentity(o, apply=True, t=t, r=r, s=s, n=0, pn=1)
            cmds.inViewMessage(amg="<hl>Applied identity on {}</hl>".format(o),
                               pos="botLeft", fade=True)
        except Exception as e:
            cmds.warning("Не удалось makeIdentity для {}: {}".format(o, e))

    if unlock_soften:
        try:
            cmds.select(targets, replace=True)
            mel.eval("UnlockNormals; PolygonSoftenEdge; SoftPolyEdgeElements 1;")
            cmds.inViewMessage(amg="<hl>Unlocked & softened edges for {}</hl>".format(label),
                               pos="botLeft", fade=True)
        except Exception as e:
            cmds.warning("Не удалось unlock/soften edges: {}".format(e))

    if loc_to_grp:
        convert_locators_to_groups(targets)
        cmds.inViewMessage(amg="<hl>Locators → groups for {}</hl>".format(label),
                           pos="botLeft", fade=True)


# ── Materials ───────────────────────────────────────────────────────────────

MATERIAL_TYPES = {
    "Standard Surface": "standardSurface",
    "Lambert": "lambert",
    "Blinn": "blinn",
    "Phong": "phong",
    "Phong E": "phongE",
    "Ramp Shader": "rampShader",
    "Layered Shader": "layeredShader",
    "Ocean Shader": "oceanShader",
    "Hair Physical Shader": "hairPhysicalShader",
    "Hair Tube Shader": "hairTubeShader",
    "Shading Map": "shadingMap",
}


def _material_default_name() -> str:
    return "{}_mat".format(_get_asset_name())


def find_material_duplicates() -> None:
    all_mats = cmds.ls(materials=True)
    groups = {}
    for m in all_mats:
        base = ''.join(c for c in m if not c.isdigit())
        groups.setdefault(base, []).append(m)
    for base, dup in groups.items():
        if len(dup) < 2:
            continue
        main = next((m for m in dup if cmds.listConnections(m, type="file")), dup[0])
        try:
            main = cmds.rename(main, base)
        except Exception:
            pass
        sgs = cmds.listConnections(main, type="shadingEngine") or []
        sg_main = sgs[0] if sgs else None
        for m in dup:
            if m == main:
                continue
            for sg in cmds.listConnections(m, type="shadingEngine") or []:
                for o in cmds.sets(sg, query=True) or []:
                    if sg_main:
                        cmds.sets(o, edit=True, forceElement=sg_main)
            try:
                cmds.delete(m)
            except Exception:
                pass
        cmds.inViewMessage(amg="<hl>Removed material duplicates</hl>",
                           pos="botLeft", fade=True)


def apply_material(flags) -> None:
    """
    Применить материал к выделению. flags:
        material_type: 'standardSurface'|'lambert'|'blinn'|'phong' (или None)
        mclean:  bool — убрать дубликаты материалов
        raw:     bool — Raw colorSpace на normal maps
        copy:    bool — копировать SG с последнего выделенного
    Имя материала: <asset>_mat. SG не трогаем.
    """
    mat_type = flags.get("material_type")
    mclean = flags.get("mclean", False)
    raw = flags.get("raw", False)
    copy = flags.get("copy", False)

    # Copy material mode
    if copy and not mat_type and not mclean and not raw:
        sel = cmds.ls(selection=True, type="transform")
        if len(sel) < 2:
            cmds.warning("Выберите минимум два объекта.")
            return
        src = sel[-1]
        sg = None
        for s in cmds.listRelatives(src, shapes=True, noIntermediate=True) or []:
            c = cmds.listConnections(s, type="shadingEngine")
            if c:
                sg = c[0]; break
        if not sg:
            cmds.warning("Материал на последнем объекте не найден.")
            return
        for o in sel[:-1]:
            try:
                cmds.sets(o, edit=True, forceElement=sg)
                cmds.inViewMessage(amg="<hl>Copied material from {} to {}</hl>".format(src, o),
                                   pos="botLeft", fade=True)
            except Exception as e:
                cmds.warning("Не удалось скопировать материал: {}".format(e))
        return

    sel_objs = cmds.ls(selection=True, type="transform")

    if not mat_type:
        if raw:
            set_color_space_for_normal_maps()
            return
        if mclean:
            find_material_duplicates()
            return
        cmds.warning("Не выбран тип материала.")
        return

    # Использовать существующий материал этого типа или создать с VVERH-именем
    all_mats = cmds.ls(materials=True)
    found = next((m for m in all_mats if cmds.nodeType(m) == mat_type), None)
    material = found if found else cmds.shadingNode(mat_type, asShader=True,
                                                    name=_material_default_name())
    sgs = cmds.listConnections(material, type="shadingEngine")
    if sgs:
        sg = sgs[0]
    else:
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True,
                       name="{}_SG".format(_get_asset_name()))
        try:
            cmds.connectAttr("{}.outColor".format(material),
                             "{}.surfaceShader".format(sg), force=True)
        except Exception:
            pass

    if not sel_objs:
        cmds.warning("Нет выбранных объектов.")
        return

    for o in sel_objs:
        has = cmds.listConnections(o, type="shadingEngine")
        if not has:
            try:
                cmds.sets(o, edit=True, forceElement=sg)
                cmds.inViewMessage(amg="<hl>Applied {} to {}</hl>".format(material, o),
                                   pos="botLeft", fade=True)
            except Exception as e:
                cmds.warning("Не удалось назначить материал: {}".format(e))
        else:
            cmds.warning("{} уже имеет материал.".format(o))

    if mclean:
        find_material_duplicates()
    if raw:
        set_color_space_for_normal_maps()


def change_material_type(new_type: str) -> None:
    """Сменить тип материалов выделения. Имена материалов сохраняются."""
    sel = cmds.ls(selection=True, long=True)
    if not sel:
        cmds.warning("Нечего менять.")
        return
    target = MATERIAL_TYPES.get(new_type, "standardSurface")
    for o in sel:
        for s in cmds.listRelatives(o, shapes=True, noIntermediate=True, fullPath=True) or []:
            for sg in cmds.listConnections(s, type='shadingEngine') or []:
                old_mats = cmds.listConnections("{}.surfaceShader".format(sg),
                                                source=True, destination=False) or []
                for old in old_mats:
                    if cmds.nodeType(old) == target:
                        continue
                    temp_old = "{}_oldTemp".format(old)
                    cmds.rename(old, temp_old)
                    new_temp = cmds.shadingNode(target, asShader=True, name="temp_" + new_type)
                    new_mat = cmds.rename(new_temp, old)  # сохранить имя материала!
                    _copy_common_attributes(temp_old, new_mat)
                    if cmds.objExists("{}.outColor".format(new_mat)):
                        cmds.connectAttr("{}.outColor".format(new_mat),
                                         "{}.surfaceShader".format(sg), force=True)
                    if cmds.objExists(temp_old):
                        cmds.delete(temp_old)
    cmds.inViewMessage(amg="<hl>Changed material type to {}</hl>".format(new_type),
                       pos="botLeft", fade=True)


def _copy_common_attributes(old_mat, new_mat) -> None:
    attrs = ["color", "transparency", "ambientColor", "incandescence",
             "normalCamera", "diffuse", "specularColor", "bumpMapping"]
    for a in attrs:
        oa, na = "{}.{}".format(old_mat, a), "{}.{}".format(new_mat, a)
        if not cmds.objExists(oa) or not cmds.objExists(na):
            continue
        con = cmds.listConnections(oa, source=True, destination=False, plugs=True)
        if con:
            cmds.connectAttr(con[0], na, force=True)
        else:
            try:
                val = cmds.getAttr(oa)
                if isinstance(val, (tuple, list)):
                    cmds.setAttr(na, *val, type="double3")
                else:
                    cmds.setAttr(na, val)
            except Exception:
                pass


# ── PBR Texture Assigner (бизнес-логика) ────────────────────────────────────

# Слоты VVERH: key (подстрока в имени файла) → (attr material node, output channel)
PBR_SLOTS = {
    'basecolor':    ('baseColor', 'outColor'),
    'basecolour':   ('baseColor', 'outColor'),
    'diffuse':      ('baseColor', 'outColor'),
    'diffusecolor': ('baseColor', 'outColor'),
    'diffusecolour':('baseColor', 'outColor'),
    'albedo':       ('baseColor', 'outColor'),
    'color':        ('baseColor', 'outColor'),
    'colour':       ('baseColor', 'outColor'),
    'roughness':    ('specularRoughness', 'outAlpha'),
    'metallic':     ('metalness', 'outAlpha'),
    'metalness':    ('metalness', 'outAlpha'),
    'metal':        ('metalness', 'outAlpha'),
    'specular':     ('specularColor', 'outColor'),
    'specularcolor':('specularColor', 'outColor'),
    'emissive':     ('emissionColor', 'outColor'),
    'emission':     ('emissionColor', 'outColor'),
    'opacity':      ('transmission', 'outAlpha'),
    'normal':       ('normalCamera', 'outNormal'),
    'norm':         ('normalCamera', 'outNormal'),
    'bump':         ('normalCamera', 'outNormal'),
}


def _file_ext(path: str) -> str:
    try:
        return os.path.splitext(path)[1].lower().lstrip(".")
    except Exception:
        return ""


def _is_udim(path_or_name: str) -> bool:
    n = path_or_name.lower()
    return ("<udim>" in n) or bool(re.search(r'1\d{3}', n))


def _set_file_colorspace(fn: str, key: str, file_path: str) -> None:
    """VVERH colorSpace: линейные данные → Raw, sRGB albedo → sRGB."""
    try:
        ext = _file_ext(file_path)
        if (key == 'normal' or ext in ("exr", "hdr")
                or key in ('roughness', 'metallic', 'metalness', 'metal',
                           'opacity', 'specular', 'specularcolor')):
            cmds.setAttr(fn + ".colorSpace", "Raw", type="string")
        else:
            cmds.setAttr(fn + ".colorSpace", "sRGB", type="string")
    except Exception:
        pass


def _create_file_node(file_path: str) -> str:
    fn = cmds.shadingNode('file', asTexture=True, isColorManaged=True)
    p2d = cmds.shadingNode('place2dTexture', asUtility=True)
    cmds.connectAttr("{}.outUV".format(p2d), "{}.uvCoord".format(fn), force=True)
    cmds.connectAttr("{}.outUvFilterSize".format(p2d), "{}.uvFilterSize".format(fn), force=True)
    cmds.setAttr("{}.fileTextureName".format(fn), file_path, type="string")
    if _is_udim(file_path):
        try:
            cmds.setAttr("{}.uvTilingMode".format(fn), 3)  # UDIM
        except Exception:
            pass
    return fn


def _connect_normal(fn: str, mat: str, normal_attr: str, shader_type: str) -> None:
    """Normal map: aiNormalMap для Arnold, иначе bump2d."""
    if shader_type in ('aiStandardSurface', 'standardSurface'):
        nn = cmds.shadingNode('aiNormalMap', asUtility=True)
        cmds.connectAttr("{}.outColor".format(fn), "{}.input".format(nn), force=True)
        cmds.connectAttr("{}.outValue".format(nn), "{}.{}".format(mat, normal_attr), force=True)
    else:
        bump = cmds.shadingNode('bump2d', asUtility=True)
        cmds.setAttr("{}.bumpInterp".format(bump), 1)
        cmds.connectAttr("{}.outAlpha".format(fn), "{}.bumpValue".format(bump), force=True)
        cmds.connectAttr("{}.outNormal".format(bump), "{}.{}".format(mat, normal_attr), force=True)


def assign_pbr_textures(mat: str, files) -> None:
    """Назначить набор PBR-текстур на материал (auto-detect слотов, UDIM, colorSpace)."""
    shader_type = cmds.nodeType(mat)
    if shader_type in ('aiStandardSurface', 'standardSurface'):
        slot_map = dict(PBR_SLOTS)
    elif shader_type in ('lambert', 'blinn', 'phong'):
        slot_map = {
            'basecolor':    ('color', 'outColor'),
            'basecolour':   ('color', 'outColor'),
            'diffuse':      ('color', 'outColor'),
            'diffusecolor': ('color', 'outColor'),
            'diffusecolour':('color', 'outColor'),
            'albedo':       ('color', 'outColor'),
            'color':        ('color', 'outColor'),
            'colour':       ('color', 'outColor'),
            'normal':       ('normalCamera', 'outNormal'),
            'norm':         ('normalCamera', 'outNormal'),
            'bump':         ('normalCamera', 'outNormal'),
        }
    else:
        cmds.warning("Unsupported shader '{}' on {}".format(shader_type, mat))
        return

    # 1 файл → assume base color
    if len(files) == 1:
        f = files[0]
        base_attr, _ = slot_map.get('basecolor', ('baseColor', 'outColor'))
        olds = cmds.listConnections("{}.{}".format(mat, base_attr), source=True) or []
        for o in olds:
            try:
                if cmds.nodeType(o) in ('file', 'bump2d', 'aiNormalMap'):
                    cmds.delete(o)
            except Exception:
                pass
        fn = _create_file_node(f)
        cmds.connectAttr("{}.outColor".format(fn), "{}.{}".format(mat, base_attr), force=True)
        _set_file_colorspace(fn, 'basecolor', f)
        return

    # Распределение по ключам
    loaded_keys = set()
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0].lower()
        compact = re.sub(r'[^a-z0-9]', '', name)
        for key in slot_map:
            if key in compact:
                loaded_keys.add(key)
                break

    for key, (mat_attr, _) in slot_map.items():
        if key in loaded_keys:
            olds = cmds.listConnections("{}.{}".format(mat, mat_attr), source=True) or []
            for o in olds:
                try:
                    if cmds.nodeType(o) in ('file', 'bump2d', 'aiNormalMap'):
                        cmds.delete(o)
                except Exception:
                    pass

    assigned = set()
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0].lower()
        compact = re.sub(r'[^a-z0-9]', '', name)
        matched_key = None
        for key in slot_map:
            if key in compact and key not in assigned:
                matched_key = key
                break
        if not matched_key:
            continue
        assigned.add(matched_key)
        mat_attr, out_chan = slot_map[matched_key]
        fn = _create_file_node(f)
        if matched_key in ('normal', 'norm', 'bump'):
            _connect_normal(fn, mat, mat_attr, shader_type)
        else:
            cmds.connectAttr("{}.{}".format(fn, out_chan),
                             "{}.{}".format(mat, mat_attr), force=True)
        _set_file_colorspace(fn, matched_key, f)


def toggle_normal_handedness() -> None:
    """Переключить tangentSpace (Left/Right) на выделенных мешах."""
    sel = cmds.ls(selection=True)
    meshes = []
    for obj in sel:
        shapes = cmds.listRelatives(obj, shapes=True, fullPath=True) or []
        for s in shapes:
            if cmds.nodeType(s) == 'mesh':
                meshes.append(s)
    meshes = list(set(meshes))
    if not meshes:
        cmds.warning("Нет mesh-шейпов в текущей селекции.")
        return
    current = cmds.getAttr(meshes[0] + ".tangentSpace")
    new_val = 2 if current == 0 else 0
    for m in meshes:
        try:
            cmds.setAttr(m + ".tangentSpace", new_val)
        except Exception as e:
            cmds.warning("Не удалось установить tangentSpace на {}: {}".format(m, e))
    cmds.inViewMessage(
        amg="Handedness set to {} on {} mesh(es)".format(
            'Left' if new_val == 2 else 'Right', len(meshes)),
        pos='topCenter', fade=True
    )


def get_materials_on_selection_mesh() -> list:
    """Список материалов на первом выделенном мешe."""
    sel_shapes = cmds.ls(selection=True, dag=True, shapes=True)
    if not sel_shapes:
        return []
    shape = sel_shapes[0]
    sgs = cmds.listConnections(shape, type="shadingEngine") or []
    mats = []
    for sg in sgs:
        surf = cmds.listConnections("{}.surfaceShader".format(sg)) or []
        for m in surf:
            if m not in mats:
                mats.append(m)
    return mats


# ════════════════════════════════════════════════════════════════════════════
# Qt UI
# ════════════════════════════════════════════════════════════════════════════

# ── DPI scaling (формулы из STUKACH ui.py) ─────────────────────────────────

def _get_base_font_size() -> int:
    try:
        app = QtWidgets.QApplication.instance()
        return app.font().pixelSize() if app.font().pixelSize() > 0 else 13
    except Exception:
        return 13

_FONT_PX = _get_base_font_size()
_S = _FONT_PX / 13.0

def _px(base: int) -> int:
    return max(1, int(base * _S))


@contextlib.contextmanager
def block_signals(*widgets):
    for w in widgets:
        w.blockSignals(True)
    try:
        yield
    finally:
        for w in widgets:
            w.blockSignals(False)


# ── Blender-dark QSS (как в STUKACH) ───────────────────────────────────────

def _build_qss() -> str:
    f = _FONT_PX
    c = _px(16)
    return (
        "QWidget { background: #1d1d1d; color: #e6e6e6; font-family: 'Segoe UI','Arial',sans-serif; font-size: %dpx; }"
        "QPushButton { background: #303030; color: #e6e6e6; border: 1px solid #3a3a3a; border-radius: 3px; padding: %dpx %dpx; font-size: %dpx; }"
        "QPushButton:hover { background: #3d3d3d; }"
        "QPushButton:pressed { background: #252525; }"
        "QPushButton:disabled { color: #606060; background: #252525; }"
        "QCheckBox { spacing: 5px; }"
        "QCheckBox::indicator { width: %dpx; height: %dpx; border: 1px solid #555; border-radius: 2px; background: #252525; }"
        "QCheckBox::indicator:hover { border-color: #4772b3; }"
        "QCheckBox::indicator:checked { background: #4772b3; border-color: #4772b3; image: none; }"
        "QGroupBox { border: none; border-top: 1px solid #2a2a2a; margin-top: 0px; padding-top: 0px; font-weight: bold; }"
        "QListWidget { background: #252525; color: #e6e6e6; border: 1px solid #2a2a2a; font-size: %dpx; outline: none; }"
        "QListWidget::item { padding: 3px 5px; border: none; }"
        "QListWidget::item:selected { background: #3d5d8a; }"
        "QComboBox { background: #303030; color: #e6e6e6; border: 1px solid #3a3a3a; padding: 3px 8px; font-size: %dpx; border-radius: 3px; }"
        "QComboBox::drop-down { border: none; width: %dpx; }"
        "QComboBox QAbstractItemView { background: #252525; color: #e6e6e6; selection-background-color: #3d5d8a; border: 1px solid #3a3a3a; outline: none; }"
        "QScrollArea { border: none; background: transparent; }"
        "QScrollBar:vertical { background: #1d1d1d; width: %dpx; border: none; }"
        "QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 4px; min-height: %dpx; }"
        "QScrollBar::handle:vertical:hover { background: #4a4a4a; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        "QLabel { background: transparent; }"
        "QToolButton { color: #8c8c8c; border: none; font-size: %dpx; padding: 0; }"
        "QToolButton:hover { color: #e6e6e6; }"
    ) % (f, _px(4), _px(10), f, c, c, f, f, _px(20), _px(10), _px(30), f)

_QSS = _build_qss()


# ── Палитра (как в STUKACH) ────────────────────────────────────────────────

_C_BUTTON   = "#4772b3"
_C_GREEN    = "#477a3c"
_C_RED      = "#ad4133"
_C_SUBTEXT  = "#8c8c8c"


def _maya_main_window():
    try:
        ptr = omui.MQtUtil.mainWindow()
        if ptr:
            return wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        pass
    return None


# ── Collapse-секция (упрощённый аналог STUKACH _CategoryBox) ────────────────

class _CollapseBox(QtWidgets.QWidget):
    """Свёртываемая секция: заголовок с ▼/▶ и контент."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(_px(2), _px(3), _px(2), _px(3))
        header.setSpacing(_px(4))

        self._collapse_btn = QtWidgets.QPushButton("▼")
        self._collapse_btn.setFixedSize(_px(16), _px(16))
        self._collapse_btn.setFlat(True)
        self._collapse_btn.setStyleSheet(
            "QPushButton { color: #8c8c8c; border: none; font-size: %dpx; padding: 0; }"
            "QPushButton:hover { color: #e6e6e6; }" % _FONT_PX)
        self._collapse_btn.clicked.connect(self._on_collapse)
        header.addWidget(self._collapse_btn)

        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet("color: #c8c8c8; font-size: %dpx; font-weight: bold;" % _FONT_PX)
        header.addWidget(title_lbl)
        header.addStretch()
        outer.addLayout(header)

        sep = QtWidgets.QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2a2a2a;")
        outer.addWidget(sep)

        self._content = QtWidgets.QWidget()
        self._content_layout = QtWidgets.QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(_px(8), _px(4), 0, _px(4))
        self._content_layout.setSpacing(_px(4))
        outer.addWidget(self._content)

        self._open = True

    def addWidget(self, widget) -> None:
        self._content_layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        self._content_layout.addLayout(layout)

    def _on_collapse(self) -> None:
        self._open = not self._open
        self._content.setVisible(self._open)
        self._collapse_btn.setText("▼" if self._open else "▶")


# ════════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ПАНЕЛЬ
# ════════════════════════════════════════════════════════════════════════════

class BridgePanel(QtWidgets.QWidget):
    """
    Qt-панель бриджа. Может использоваться как:
      - самостоятельное окно: launch()
      - встроенный виджет (положить в layout STUKACH)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PROKLADKA — Maya сторона")
        self.setObjectName("BridgePanelV7")
        self.setMinimumWidth(_px(380))
        self.setStyleSheet(_QSS)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(_px(8), _px(8), _px(8), _px(8))
        root.setSpacing(_px(6))

        root.addWidget(self._build_header())
        root.addWidget(self._build_recent_row())
        root.addWidget(self._build_io_buttons())
        root.addWidget(self._build_uv_section())
        root.addWidget(self._build_transform_section())
        root.addWidget(self._build_material_section())
        root.addWidget(self._build_rig_section())
        root.addStretch()

    # ── Header ────────────────────────────────────────────────────────────
    def _build_header(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel("PROKLADKA")
        title.setStyleSheet("color: #c8c8c8; font-size: %dpx; font-weight: bold;" % (_FONT_PX + 2))
        lay.addWidget(title)
        lay.addStretch()
        self._status_lbl = QtWidgets.QLabel("")
        self._status_lbl.setStyleSheet("color: %s; font-size: %dpx;" % (_C_SUBTEXT, _FONT_PX))
        lay.addWidget(self._status_lbl)
        return w

    # ── Recent FBX ────────────────────────────────────────────────────────
    def _build_recent_row(self) -> QtWidgets.QWidget:
        box = _CollapseBox("Recent FBX")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(_px(4))
        self._recent_combo = QtWidgets.QComboBox()
        self._recent_combo.setMinimumWidth(_px(260))
        row.addWidget(self._recent_combo, 1)
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh_recent)
        row.addWidget(refresh_btn)
        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self._on_clear_recent)
        row.addWidget(clear_btn)
        hist_btn = QtWidgets.QPushButton("History")
        hist_btn.clicked.connect(self._show_history)
        row.addWidget(hist_btn)
        box.addLayout(row)
        self._refresh_recent_combo()
        return box

    # ── Import/Export + naming ────────────────────────────────────────────
    def _show_history(self):
        cmds.confirmDialog(title="PROKLADKA Export History",
                           message=recent_history_report(),
                           button=["OK"], messageAlign="left")

    def _on_clear_recent(self):
        ret = QtWidgets.QMessageBox.question(
            self, "PROKLADKA", "Очистить историю экспортов?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if ret != QtWidgets.QMessageBox.Yes:
            return
        clear_recent_json()
        self._refresh_recent_combo()

    def _build_io_buttons(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_px(4))

        # Legacy FBX — escape hatch для чужих ассетов (симметрично с Legacy scale в Blender)
        self._plain_cb = QtWidgets.QCheckBox("Legacy FBX (режим V6, без правок масштаба)")
        self._plain_cb.setChecked(False)
        self._plain_cb.setToolTip("Для чужих ассетов с необычным масштабом. "
                                  "Симметрично с Legacy scale в Blender: голый FBXImport/Export "
                                  "без правок units.")
        lay.addWidget(self._plain_cb)

        btn_export = QtWidgets.QPushButton("Export")
        btn_export.clicked.connect(self._on_export)
        btn_export.setStyleSheet(
            "QPushButton { background: %s; color: #fff; font-weight: bold; }"
            "QPushButton:hover { background: #5683c8; }" % _C_BUTTON)
        lay.addWidget(btn_export)

        btn_import = QtWidgets.QPushButton("Import")
        btn_import.clicked.connect(self._on_import)
        btn_import.setStyleSheet(
            "QPushButton { background: %s; color: #fff; font-weight: bold; }"
            "QPushButton:hover { background: #589456; }" % _C_GREEN)
        lay.addWidget(btn_import)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(_px(4))
        # Naming preset dropdown (симметрично с Blender)
        self._naming_combo = QtWidgets.QComboBox()
        for preset_name in NAMING_PRESETS:
            self._naming_combo.addItem(preset_name)
        self._naming_combo.setCurrentText("Default")
        row.addWidget(self._naming_combo, 1)

        btn_naming = QtWidgets.QPushButton("Apply Naming")
        btn_naming.clicked.connect(self._on_apply_naming)
        row.addWidget(btn_naming)
        lay.addLayout(row)

        # Hint: краткое описание пресета
        self._naming_hint = QtWidgets.QLabel("")
        self._naming_hint.setStyleSheet("color: %s; font-size: %dpx;" % (_C_SUBTEXT, _FONT_PX - 1))
        lay.addWidget(self._naming_hint)
        self._naming_combo.currentTextChanged.connect(self._update_naming_hint)
        self._update_naming_hint()

        return w

    def _update_naming_hint(self) -> None:
        """Обновить hint с описанием активного пресета."""
        preset_name = self._naming_combo.currentText()
        preset = NAMING_PRESETS.get(preset_name, {})
        parts = []
        if preset.get("suffix_mesh") or preset.get("suffix_grp"):
            parts.append("_type")
        if preset.get("lowercase"):
            parts.append("lower")
        if not preset.get("dots", True):
            parts.append("keep dots")
        desc = " · ".join(parts) if parts else "no transform"
        self._naming_hint.setText("  {}".format(desc))

    # ── Universal UV renamer ──────────────────────────────────────────────
    def _build_uv_section(self) -> "_CollapseBox":
        box = _CollapseBox("UV Convention")

        # Dropdown конвенции
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(_px(4))
        row.addWidget(QtWidgets.QLabel("Target:"))
        self._uv_target_combo = QtWidgets.QComboBox()
        for key in UV_CONVENTIONS.keys():
            self._uv_target_combo.addItem(key)
        # Дефолт — Maya (т.к. PROKLADKA Maya сторона)
        self._uv_target_combo.setCurrentText("Maya")
        self._uv_target_combo.currentTextChanged.connect(self._on_uv_target_changed)
        row.addWidget(self._uv_target_combo, 1)
        box.addLayout(row)

        # Custom name field (показывается только для Custom)
        self._uv_custom_edit = QtWidgets.QLineEdit()
        self._uv_custom_edit.setPlaceholderText("custom UV name")
        self._uv_custom_edit.setVisible(False)
        box.addWidget(self._uv_custom_edit)

        # Apply button
        btn = QtWidgets.QPushButton("Apply UV Convention")
        btn.clicked.connect(self._on_apply_uv)
        box.addWidget(btn)

        # Hint-строка для multi-UV сигнала
        self._uv_hint_lbl = QtWidgets.QLabel("")
        self._uv_hint_lbl.setStyleSheet("color: #b0a060; font-size: %dpx;" % _FONT_PX)
        self._uv_hint_lbl.setWordWrap(True)
        self._uv_hint_lbl.setVisible(False)
        box.addWidget(self._uv_hint_lbl)

        return box

    def _on_uv_target_changed(self, text: str) -> None:
        """Показать/скрыть custom name field."""
        self._uv_custom_edit.setVisible(text == "Custom")

    def _on_apply_uv(self) -> None:
        target = self._uv_target_combo.currentText()
        custom = self._uv_custom_edit.text() if target == "Custom" else ""
        stats = rename_uv_universal(target, custom)

        if stats["meshes_processed"] == 0:
            self._set_status("No meshes", _C_SUBTEXT)
            self._uv_hint_lbl.setVisible(False)
            return

        # Сигнал о multi-UV
        if stats["multi_uv_meshes"] > 0:
            names = "; ".join(stats["multi_uv_list"][:5])
            if len(stats["multi_uv_list"]) > 5:
                names += "; +{}".format(len(stats["multi_uv_list"]) - 5)
            self._uv_hint_lbl.setText(
                "⚠ {} mesh(es) have additional UV sets (untouched): {}".format(
                    stats["multi_uv_meshes"], names))
            self._uv_hint_lbl.setVisible(True)
        else:
            self._uv_hint_lbl.setVisible(False)

        if stats["errors"]:
            for err in stats["errors"][:3]:
                cmds.warning("UV rename: {}".format(err))

        self._set_status(
            "UV: {} renamed".format(stats["renamed_count"])
            + (", {} have extras".format(stats["multi_uv_meshes"]) if stats["multi_uv_meshes"] else ""),
            _C_GREEN if not stats["multi_uv_meshes"] else "#b0a060"
        )

    # ── Transform Options ─────────────────────────────────────────────────
    def _build_transform_section(self) -> _CollapseBox:
        box = _CollapseBox("Transform Options")

        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(_px(8))
        self._t_cb = QtWidgets.QCheckBox("Translate"); self._t_cb.setChecked(False)
        self._r_cb = QtWidgets.QCheckBox("Rotate");    self._r_cb.setChecked(True)
        self._s_cb = QtWidgets.QCheckBox("Scale");     self._s_cb.setChecked(False)
        self._soften_cb = QtWidgets.QCheckBox("Unlock/Soften"); self._soften_cb.setChecked(False)
        for cb in (self._t_cb, self._r_cb, self._s_cb, self._soften_cb):
            row1.addWidget(cb)
        box.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(_px(8))
        self._loc_cb = QtWidgets.QCheckBox("Loc→Grp"); self._loc_cb.setChecked(False)
        self._norm_cb = QtWidgets.QCheckBox("Import Normals"); self._norm_cb.setChecked(True)
        row2.addWidget(self._loc_cb)
        row2.addWidget(self._norm_cb)
        box.addLayout(row2)

        btn = QtWidgets.QPushButton("Apply Identity")
        btn.clicked.connect(self._on_apply_identity)
        box.addWidget(btn)

        return box

    # ── Material ──────────────────────────────────────────────────────────
    def _build_material_section(self) -> _CollapseBox:
        box = _CollapseBox("Material")

        # Типы материалов — radio-поведение (эксклюзивны)
        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(_px(6))
        self._mat_type_group = QtWidgets.QButtonGroup(self)
        self._mat_type_group.setExclusive(False)  # чтобы можно было снять выделение
        self._mat_cbs = {}
        for key, label, default in [
            ("standardSurface", "StdSurface", True),
            ("lambert",         "Lambert",    False),
            ("blinn",           "Blinn",      False),
            ("phong",           "Phong",      False),
        ]:
            cb = QtWidgets.QCheckBox(label)
            cb.setChecked(default)
            self._mat_cbs[key] = cb
            self._mat_type_group.addButton(cb)
            cb.stateChanged.connect(lambda s, n=key: self._on_mat_radio(n, s))
            row1.addWidget(cb)
        box.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(_px(6))
        self._mclean_cb = QtWidgets.QCheckBox("mClean");  self._mclean_cb.setChecked(False)
        self._raw_cb    = QtWidgets.QCheckBox("Raw");     self._raw_cb.setChecked(False)
        self._copy_cb   = QtWidgets.QCheckBox("Copy Mat"); self._copy_cb.setChecked(False)
        for cb in (self._mclean_cb, self._raw_cb, self._copy_cb):
            row2.addWidget(cb)
        box.addLayout(row2)

        btn = QtWidgets.QPushButton("Apply Material")
        btn.clicked.connect(self._on_apply_material)
        box.addWidget(btn)

        btn_change = QtWidgets.QPushButton("Change Material Type…")
        btn_change.clicked.connect(self._on_change_material_type)
        box.addWidget(btn_change)

        btn_pbr = QtWidgets.QPushButton("PBR Texture Assigner…")
        btn_pbr.clicked.connect(self._on_pbr_assigner)
        box.addWidget(btn_pbr)

        return box

    # ── Rig Transfer ─────────────────────────────────────────────────────
    def _build_rig_section(self) -> "_CollapseBox":
        box = _CollapseBox("Rig Transfer")

        # Export block
        export_label = QtWidgets.QLabel("Export rig:")
        export_label.setStyleSheet("color: #c8c8c8; font-size: %dpx; font-weight: bold;" % _FONT_PX)
        box.addWidget(export_label)

        self._rig_bake_cb = QtWidgets.QCheckBox("Bake animation")
        self._rig_bake_cb.setChecked(False)
        box.addWidget(self._rig_bake_cb)

        self._rig_sel_only_cb = QtWidgets.QCheckBox("Selection only")
        self._rig_sel_only_cb.setChecked(True)
        box.addWidget(self._rig_sel_only_cb)

        btn_export = QtWidgets.QPushButton("Export Rig (FBX + Recipe)")
        btn_export.clicked.connect(self._on_export_rig)
        box.addWidget(btn_export)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2a2a2a;")
        box.addWidget(sep)

        # Reconstruct block
        rec_label = QtWidgets.QLabel("Reconstruct rig:")
        rec_label.setStyleSheet("color: #c8c8c8; font-size: %dpx; font-weight: bold;" % _FONT_PX)
        box.addWidget(rec_label)

        # Recipe path — dropdown по файлам *_rig_recipe.json в C:\temp
        self._rig_recipe_combo = QtWidgets.QComboBox()
        self._refresh_rig_recipes()
        box.addWidget(self._rig_recipe_combo)

        rec_row = QtWidgets.QHBoxLayout()
        btn_refresh = QtWidgets.QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_rig_recipes)
        rec_row.addWidget(btn_refresh)
        btn_reconstruct = QtWidgets.QPushButton("Reconstruct")
        btn_reconstruct.clicked.connect(self._on_reconstruct_rig)
        rec_row.addWidget(btn_reconstruct)
        box.addLayout(rec_row)

        # Hint
        hint = QtWidgets.QLabel("Recipe rebuilds constraints + control shapes")
        hint.setStyleSheet("color: #606060; font-size: %dpx;" % (_FONT_PX - 1))
        hint.setWordWrap(True)
        box.addWidget(hint)

        return box

    def _refresh_rig_recipes(self) -> None:
        """Заполнить combo списком recipe-файлов в C:\\temp."""
        self._rig_recipe_combo.clear()
        import glob
        patterns = [
            r"C:\temp\*_rig_recipe.json",
            r"C:\temp\*_recipe.json",
        ]
        files = []
        for pat in patterns:
            files.extend(glob.glob(pat))
        # уникальные + отсортировать по mtime (свежие сверху)
        seen = set()
        unique = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        try:
            unique.sort(key=lambda p: _os.path.getmtime(p), reverse=True)
        except Exception:
            pass
        if not unique:
            self._rig_recipe_combo.addItem("(no recipes in C:\\temp)")
        else:
            for f in unique:
                self._rig_recipe_combo.addItem(_os.path.basename(f), f)

    def _on_export_rig(self) -> None:
        asset = _get_asset_name()
        fbx_path = "C:/temp/{}_rig.fbx".format(asset)
        recipe_path = "C:/temp/{}_rig_recipe.json".format(asset)
        result = _rig_maya.export_rig(
            fbx_path=fbx_path,
            recipe_path=recipe_path,
            bake_animation=self._rig_bake_cb.isChecked(),
            selection_only=self._rig_sel_only_cb.isChecked(),
            asset_name=asset,
        )
        if result.get("error"):
            self._set_status("Rig export failed", _C_RED)
            cmds.warning("Rig export: {}".format(result["error"]))
        else:
            self._set_status("Rig exported", _C_GREEN)
            self._refresh_rig_recipes()

    def _on_reconstruct_rig(self) -> None:
        idx = self._rig_recipe_combo.currentIndex()
        if idx < 0:
            return
        recipe_path = self._rig_recipe_combo.itemData(idx)
        if not recipe_path or not _os.path.exists(recipe_path):
            cmds.warning("Recipe file not found")
            return
        stats = _rig_maya.import_rig_with_recipe(recipe_path)
        if "error" in stats:
            self._set_status("Reconstruct failed", _C_RED)
        else:
            extra = ""
            if stats.get("missing_names"):
                extra = " ({} missing)".format(len(stats["missing_names"]))
            self._set_status(
                "Rig: {} ctrl, {} constr{}".format(
                    stats["controls_applied"], stats["constraints_created"], extra),
                _C_GREEN if not stats.get("missing_names") else "#b0a060"
            )

    # ── Слоты ─────────────────────────────────────────────────────────────

    def _selected_mat_type(self):
        for key, cb in self._mat_cbs.items():
            if cb.isChecked():
                return key
        return None

    def _on_refresh_recent(self) -> None:
        self._refresh_recent_combo()

    def _refresh_recent_combo(self) -> None:
        self._recent_combo.clear()
        paths = _read_recent_paths()
        if not paths:
            self._recent_combo.addItem("(none)")
            return
        for p in paths:
            # Показывать имя + размер — сразу видно полный файл или частичный
            try:
                size_kb = os.path.getsize(p) // 1024
                label = "{} ({} KB)".format(os.path.basename(p), size_kb)
            except Exception:
                label = os.path.basename(p)
            self._recent_combo.addItem(label, p)  # data = полный путь

    def _selected_recent_path(self) -> str:
        if self._recent_combo.count() == 0:
            return _current_export_path()
        # currentData() = полный путь ( addItem(label, path) )
        val = self._recent_combo.currentData()
        if not val:
            # Fallback: если data не задан, попробовать text как путь
            text = self._recent_combo.currentText()
            if text and text != "(none)" and os.path.exists(text):
                return text
            return _current_export_path()
        return val

    def _on_export(self) -> None:
        try:
            export_selected_to_fbx(plain=self._plain_cb.isChecked())
            self._set_status("Exported", _C_GREEN)
            self._refresh_recent_combo()
        except Exception as e:
            self._set_status("Export failed", _C_RED)
            cmds.warning("Bridge export: {}".format(e))

    def _on_import(self) -> None:
        chosen = self._selected_recent_path()
        try:
            import_fbx(
                path=chosen,
                plain=self._plain_cb.isChecked(),
                unlock_normals=self._norm_cb.isChecked(),
                loc_to_grp=self._loc_cb.isChecked(),
            )
            self._set_status("Imported", _C_GREEN)
        except Exception as e:
            self._set_status("Import failed", _C_RED)
            cmds.warning("Bridge import: {}".format(e))

    def _on_apply_naming(self) -> None:
        preset_name = self._naming_combo.currentText()
        try:
            rename_fbxasc_objects(preset_name=preset_name)
            self._set_status("Naming: {} applied".format(preset_name), _C_GREEN)
        except Exception as e:
            self._set_status("Naming failed", _C_RED)
            cmds.warning("Bridge naming: {}".format(e))

    def _on_map1(self) -> None:
        try:
            rename_uv_set_to_map1_all_selected()
            self._set_status("UV → map1", _C_GREEN)
        except Exception as e:
            self._set_status("map1 failed", _C_RED)
            cmds.warning("map1: {}".format(e))

    def _on_apply_identity(self) -> None:
        try:
            apply_identity_transform(
                flags={
                    "translate": self._t_cb.isChecked(),
                    "rotate":    self._r_cb.isChecked(),
                    "scale":     self._s_cb.isChecked(),
                },
                unlock_soften=self._soften_cb.isChecked(),
                loc_to_grp=self._loc_cb.isChecked(),
            )
            self._set_status("Identity applied", _C_GREEN)
        except Exception as e:
            self._set_status("Identity failed", _C_RED)
            cmds.warning("Apply identity: {}".format(e))

    def _on_apply_material(self) -> None:
        try:
            apply_material(flags={
                "material_type": self._selected_mat_type(),
                "mclean": self._mclean_cb.isChecked(),
                "raw":    self._raw_cb.isChecked(),
                "copy":   self._copy_cb.isChecked(),
            })
            self._set_status("Material applied", _C_GREEN)
        except Exception as e:
            self._set_status("Material failed", _C_RED)
            cmds.warning("Apply material: {}".format(e))

    def _on_mat_radio(self, name: str, state: int) -> None:
        """StdSurface/Lambert/Blinn/Phong — эксклюзивны (radio).
        STUKACH-кодировка: int(state) == 2 → Qt.Checked."""
        if int(state) == 2:  # Qt.Checked
            for other_key, other_cb in self._mat_cbs.items():
                if other_key != name:
                    with block_signals(other_cb):
                        other_cb.setChecked(False)

    def _on_change_material_type(self) -> None:
        items = list(MATERIAL_TYPES.keys())
        chosen, ok = QtWidgets.QInputDialog.getItem(
            self, "Change Material Type", "New type:", items, 0, False)
        if ok and chosen:
            try:
                change_material_type(chosen)
                self._set_status("Type → {}".format(chosen), _C_GREEN)
            except Exception as e:
                self._set_status("Change type failed", _C_RED)
                cmds.warning("Change material type: {}".format(e))

    def _on_pbr_assigner(self) -> None:
        dlg = PBRTextureAssignerDialog(self)
        dlg.exec_()

    def _set_status(self, text: str, color: str = _C_SUBTEXT) -> None:
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet("color: %s; font-size: %dpx;" % (color, _FONT_PX))


# ════════════════════════════════════════════════════════════════════════════
# PBR TEXTURE ASSIGNER (Qt-диалог)
# ════════════════════════════════════════════════════════════════════════════

class PBRTextureAssignerDialog(QtWidgets.QDialog):
    """Диалог назначения PBR-текстур. Бизнес-логика: assign_pbr_textures()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PROKLADKA — PBR Texture Assigner")
        self.setMinimumWidth(_px(360))
        self.setStyleSheet(_QSS)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(_px(8), _px(8), _px(8), _px(8))
        lay.setSpacing(_px(6))

        lay.addWidget(self._lbl("1) Select mesh and its materials:"))
        self.mat_list = QtWidgets.QListWidget()
        self.mat_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.mat_list.setMinimumHeight(_px(100))
        lay.addWidget(self.mat_list)

        btn_refresh = QtWidgets.QPushButton("Refresh Materials")
        btn_refresh.clicked.connect(self.refresh_materials)
        lay.addWidget(btn_refresh)

        lay.addWidget(self._lbl("2) Load PBR textures and assign (UDIM/ACES auto):"))
        btn_load = QtWidgets.QPushButton("Load & Assign Textures")
        btn_load.clicked.connect(self.load_and_assign)
        lay.addWidget(btn_load)

        lay.addWidget(self._lbl("3) Toggle Normal-Map Handedness:"))
        btn_hand = QtWidgets.QPushButton("Toggle Normal Handedness")
        btn_hand.clicked.connect(self.toggle_handedness)
        lay.addWidget(btn_hand)

        self.refresh_materials()

    def _lbl(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet("color: #c8c8c8; font-size: %dpx;" % _FONT_PX)
        return lbl

    def refresh_materials(self) -> None:
        self.mat_list.clear()
        mats = get_materials_on_selection_mesh()
        if not mats:
            cmds.warning("На меш не назначен ни один материал (или меш не выделен).")
        else:
            self.mat_list.addItems(mats)

    def load_and_assign(self) -> None:
        mats = [it.text() for it in self.mat_list.selectedItems()]
        if not mats:
            cmds.warning("Сначала выберите хотя бы один материал.")
            return
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select PBR textures", "",
            "Images (*.png *.jpg *.jpeg *.exr *.hdr *.tiff *.tif)")
        if not files:
            return
        for mat in mats:
            assign_pbr_textures(mat, files)
        cmds.inViewMessage(amg="Textures assigned", pos='topCenter', fade=True)

    def toggle_handedness(self) -> None:
        toggle_normal_handedness()


# ════════════════════════════════════════════════════════════════════════════
# LAUNCHER
# ════════════════════════════════════════════════════════════════════════════

_PANEL_INSTANCE = None

def launch() -> "BridgePanel":
    """Открыть панель бриджа как самостоятельное окно Maya."""
    global _PANEL_INSTANCE
    if _PANEL_INSTANCE is not None:
        try:
            _PANEL_INSTANCE.close()
            _PANEL_INSTANCE.deleteLater()
        except Exception:
            pass
        _PANEL_INSTANCE = None
    parent = _maya_main_window()
    _PANEL_INSTANCE = BridgePanel(parent=parent)
    _PANEL_INSTANCE.setWindowFlags(Qt.Window)
    _PANEL_INSTANCE.show()
    _PANEL_INSTANCE.raise_()
    return _PANEL_INSTANCE


def close() -> None:
    global _PANEL_INSTANCE
    if _PANEL_INSTANCE is not None:
        try:
            _PANEL_INSTANCE.close()
            _PANEL_INSTANCE.deleteLater()
        except Exception:
            pass
        _PANEL_INSTANCE = None


if __name__ == "__main__":
    launch()
