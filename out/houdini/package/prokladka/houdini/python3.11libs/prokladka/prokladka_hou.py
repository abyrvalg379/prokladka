# -*- coding: utf-8 -*-
"""
prokladka_hou.py — PROKLADKA для Houdini 20.5+ (двусторонний мост).

Поддерживаемые форматы обмена (симметрично с Blender/Maya/UE):
  - FBX     — статичная/анимированная геометрия
  - VDB     — объёмные данные (дым, облака, огонь)
  - Alembic — baked geometry animation
  - USD     — Universal Scene Description (Solaris)

Принцип: ассет должен корректно приходить в обе стороны.
"""
from __future__ import annotations

import os
import json
import hou


# ════════════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════════════════════

TEMP_DIRECTORY = os.environ.get("PROKLADKA_TEMP", r"C:\temp")
RECENT_JSON    = os.path.join(TEMP_DIRECTORY, "bridge_last.json")
RECENT_MAX     = 5

# Конфигурация ROP-нод для каждого формата.
# "out" — тип ROP в /out/ контексте
# "sop" — тип ROP в SOP контексте
# "ext" — расширение файла
# "trange_supported" — поддерживает ли frame range (для sequence)
EXPORT_FORMATS = {
    "fbx": {
        "out": "filmboxfbx",
        "sop": "rop_fbx",
        "ext": ".fbx",
        "trange_supported": True,
        "label": "FBX (geometry + animation)",
    },
    "vdb": {
        "out": "rop_geometry",
        "sop": "rop_geometry",
        "ext": ".vdb",
        "trange_supported": True,
        "label": "VDB (volumes)",
    },
    "alembic": {
        "out": "alembic",
        "sop": "rop_alembic",
        "ext": ".abc",
        "trange_supported": True,
        "label": "Alembic (baked animation)",
    },
    "usd": {
        "out": "usd",
        "sop": "rop_usd",
        "ext": ".usd",
        "trange_supported": True,
        "label": "USD (Solaris)",
    },
}

# Naming convention (симметрично с другими DCC PROKLADKA)
HOUDINI_NAMING_PRESETS = {
    "Houdini": {
        "geo": "_geo", "vdb": "_vdb", "abc": "_abc", "usd": "_usd",
        "null": "_null", "lowercase": False,
    },
    "Default": {
        "geo": "_geo", "vdb": "_vdb", "abc": "_abc", "usd": "_usd",
        "null": "_grp", "lowercase": True,
    },
}


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════


def _ui_status(msg):
    """Статус-бар в GUI, print в headless (hou.ui недоступен в hython)."""
    try:
        _ui_status(msg, hou.severityType.Important)
    except Exception:
        print("[PROKLADKA] " + str(msg))


def _ui_message(msg):
    """Диалог в GUI, print в headless."""
    try:
        _ui_message(msg)
    except Exception:
        print("[PROKLADKA] " + str(msg))


def _normalize_slashes(path: str) -> str:
    """Windows path → Houdini-friendly (forward slashes)."""
    return path.replace("\\", "/")


def _get_scene_name() -> str:
    """Имя .hip файла без расширения, fallback 'untitled'."""
    hip = hou.hipFile.path()
    if hip and hip != "untitled.hip":
        name = os.path.splitext(os.path.basename(hip))[0]
    else:
        name = "untitled"
    safe = name.replace(".", "_").replace(" ", "_")
    return safe or "untitled"


def _get_export_path(fmt: str, frame: int = None) -> str:
    """C:\\temp\\<scene>_<format>.<ext> (или с $F4 для sequence)."""
    cfg = EXPORT_FORMATS.get(fmt)
    if not cfg:
        return ""
    ext = cfg["ext"]
    scene = _get_scene_name()
    if frame is not None:
        # Sequence path: вставляем frame number
        return "{}/{}_{}.{:04d}{}".format(TEMP_DIRECTORY, scene, fmt, frame, ext)
    return "{}/{}_{}{}".format(TEMP_DIRECTORY, scene, fmt, ext)


def update_recent_json(path: str) -> None:
    """Добавить path в bridge_last.json. Общий со всеми DCC PROKLADKA."""
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
    except Exception as e:
        _ui_status("PROKLADKA recent update: {}".format(e))


def read_recent_files() -> list:
    """Прочитать bridge_last.json. Возвращает список существующих путей."""
    paths = []
    try:
        if os.path.exists(RECENT_JSON):
            with open(RECENT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    paths = [p for p in data if isinstance(p, str)]
    except Exception:
        pass
    # Для sequence (.XXXX.vdb) проверяем существование первого файла
    valid = []
    for p in paths:
        if os.path.exists(p):
            valid.append(p)
        else:
            # Попробовать раскрыть шаблон для sequence (для display)
            import glob
            parent = os.path.dirname(p)
            base = os.path.basename(p)
            # Если имя содержит 4 цифры перед расширением — это может быть sequence
            import re
            m = re.match(r'^(.+?)\.(\d{4})(\..+)$', base)
            if m:
                pattern = m.group(1) + ".*" + m.group(3)
                matches = sorted(glob.glob(os.path.join(parent, pattern)))
                if matches:
                    valid.append(matches[0])
    return valid[:RECENT_MAX]


# ════════════════════════════════════════════════════════════════════════════
# SOP / NODE SELECTION HELPERS
# ════════════════════════════════════════════════════════════════════════════

def get_active_sop() -> hou.Node:
    """
    Получить активный SOP для экспорта.
    Приоритет: выделенный SOP -> display выбранного /obj/geo -> display geo
    текущей сети -> единственный geo в сцене.
    """
    # 1. Выделенные SOP nodes
    selected = hou.selectedNodes()
    for n in selected:
        if n.type().category().name() == "Sop":
            return n

    # 2. Выделенный /obj/geo: возвращаем ОБЪЕКТ — export запечёт его трансформ
    for n in selected:
        if n.isEditable() and hasattr(n, 'displayNode'):
            if n.displayNode():
                return n

    # 3. Мы внутри /obj/<geo>: display node этого geo
    try:
        parent = hou.pwd().parent()
        if parent is not None and hasattr(parent, 'displayNode'):
            disp = parent.displayNode()
            if disp:
                return disp
    except Exception:
        pass

    # 4. Единственный /obj/geo в сцене (не импорты)
    try:
        geos = []
        for c in hou.node('/obj').children():
            if hasattr(c, 'displayNode') and not c.name().startswith('prokladka_imports'):
                if c.displayNode():
                    geos.append(c)
        if len(geos) == 1:
            return geos[0].displayNode()
    except Exception:
        pass

    raise RuntimeError(
        "No geometry found. Select a SOP node or an /obj geometry first.")

    # 3. Если ничего не выделено — display node текущего /obj geo
    try:
        current = hou.node('/obj').currentLayer() if hasattr(hou.node('/obj'), 'currentLayer') else None
    except Exception:
        current = None
    # fallback: obj-level selection
    selected_obj = hou.node('/obj').selectedChildren()
    for n in selected_obj:
        if hasattr(n, 'displayNode'):
            disp = n.displayNode()
            if disp:
                return disp

    raise RuntimeError("No SOP selected. Select a SOP node or /obj/geo with display flag.")


def get_active_lop() -> hou.Node:
    """Активный LOP для USD export (Solaris)."""
    selected = hou.selectedNodes()
    for n in selected:
        if n.type().category().name() == "Lop":
            return n
    # /stage display
    stage = hou.node('/stage')
    if stage:
        for child in stage.children():
            if child.type().category().name() == "Lop":
                return child
    raise RuntimeError("No LOP selected. Select a LOP node in /stage/ for USD export.")


def detect_data_type(sop_node: hou.Node) -> str:
    """
    Определить тип данных SOP: 'volume' / 'geometry' / 'anim'.
    volume = VDB-данные; anim = time-dependent.
    """
    try:
        geo = sop_node.geometry()
        if geo is None:
            return "unknown"
        # Volume/VDB prims
        vdb_prims = geo.globPrims("@(volume = 1)") or geo.primsByGroup("volume", hou.geomType.Volume) if False else []
        # Более простой путь — итерировать первые N prims и проверить типы
        has_volume = False
        for prim in geo.prims()[:100]:  # check first 100 for speed
            if prim.type() == hou.primType.Volume or prim.type() == hou.primType.VDB:
                has_volume = True
                break
        if has_volume:
            return "volume"
        # time-dependent?
        if sop_node.isTimeDependent():
            return "anim"
        return "geometry"
    except Exception:
        return "unknown"


# ════════════════════════════════════════════════════════════════════════════
# EXPORT — все 4 формата
# ════════════════════════════════════════════════════════════════════════════

def _ensure_out_subnet():
    """Создать /out/prokladka/ subnet для чистоты (если нет)."""
    out = hou.node('/out')
    if not out:
        raise RuntimeError("/out context not found")
    sub = hou.node('/out/prokladka')
    if not sub:
        sub = out.createNode('subnet', 'prokladka')
    return sub


def _create_rop(format_key: str, name: str) -> hou.Node:
    """Создать ROP node в /out/prokladka/ для указанного формата."""
    sub = _ensure_out_subnet()
    node_type = EXPORT_FORMATS[format_key]["out"]
    existing = sub.node(name)
    if existing:
        return existing  # reuse
    return sub.createNode(node_type, name)


def _set_frame_range(rop: hou.Node, frame_range: tuple) -> None:
    """Установить trange/f1/f2/f3 на ROP."""
    if not frame_range or len(frame_range) < 2:
        rop.parm('trange').set(0)  # single frame (current)
        return
    start, end = int(frame_range[0]), int(frame_range[1])
    if start == end:
        rop.parm('trange').set(0)
    else:
        rop.parm('trange').set(1)  # range
        rop.parm('f1').set(start)
        rop.parm('f2').set(end)
        rop.parm('f3').set(1)  # step



def _bake_object_transform(geo_node: hou.Node) -> str:
    """
    Для /obj/geo с трансформом: вставить prk_bake_xform после display-ноды
    и скопировать в него t/r/s/p объекта. Возвращает путь bake-ноды
    (startnode для ROP), чтобы поворот/масштаб уехали в FBX.
    Идемпотентно: prk_bake_xform переиспользуется.
    """
    disp = geo_node.displayNode()
    if disp is None:
        return geo_node.path()
    bake = geo_node.node("prk_bake_xform")
    if bake is None:
        bake = geo_node.createNode("xform", "prk_bake_xform")
        bake.setInput(0, disp)
    for src, dst in (("t", "t"), ("r", "r"), ("s", "s"), ("p", "p")):
        try:
            pt = geo_node.parmTuple(src)
            pd = bake.parmTuple(dst)
            if pt is not None and pd is not None:
                pd.set(pt.eval())
        except Exception:
            pass
    try:
        us = geo_node.parm("scale")
        if us:
            bake.parm("scale").set(us.eval())
    except Exception:
        pass
    return bake.path()


def _export_startnode(sop_path: str) -> str:
    """
    Если путь указывает на /obj объект — запечь его трансформ и вернуть
    bake-ноду. Иначе (SOP внутри сети) вернуть путь как есть.
    """
    node = hou.node(sop_path)
    if node is not None and node.type().category().name() == "Object"             and hasattr(node, "displayNode"):
        return _bake_object_transform(node)
    return sop_path


def export_fbx(sop_path: str, frame_range: tuple = None) -> str:
    """Экспорт FBX из SOP. Возвращает путь к файлу."""
    if not os.path.exists(TEMP_DIRECTORY):
        os.makedirs(TEMP_DIRECTORY)

    out_path = _get_export_path("fbx")
    # Если sequence (frame_range с разными start/end), FBX всё равно один файл
    # с baked animation. Поэтому без $F4.

    rop = _create_rop("fbx", "fbx_export")
    start = _export_startnode(sop_path)
    # 20.5: startnode/sopoutput; старые версии: soppath/file|filename
    for node_parm in ("startnode", "soppath"):
        pp = rop.parm(node_parm)
        if pp:
            pp.set(start)
            break
    for file_parm in ("sopoutput", "file", "filename"):
        pp = rop.parm(file_parm)
        if pp:
            pp.set(_normalize_slashes(out_path))
            break
    # Blender-импортёр читает только BINARY FBX, а дефолт ROP — ASCII
    ak = rop.parm("exportkind")
    if ak:
        ak.set(0)
    # convertunits=1: числа в FBX-cm + корректная декларация юнитов
    # (проверено: Blender получает ровно 1.0 m; =0 даёт 0.01 m)
    cu = rop.parm("convertunits")
    if cu:
        cu.set(1)
    _set_frame_range(rop, frame_range or (1, 1))
    rop.render()

    update_recent_json(out_path)
    _ui_status("PROKLADKA: FBX exported → {}".format(out_path))
    return out_path


def export_vdb(sop_path: str, frame_range: tuple = None) -> str:
    """
    Экспорт VDB. Для sequence path с $F4.
    Single frame: <scene>_vdb.vdb
    Sequence: <scene>_vdb.$F4.vdb
    """
    if not os.path.exists(TEMP_DIRECTORY):
        os.makedirs(TEMP_DIRECTORY)

    is_sequence = frame_range and len(frame_range) >= 2 and frame_range[0] != frame_range[1]

    if is_sequence:
        scene = _get_scene_name()
        out_path_template = "{}/{}_vdb.$F4.vdb".format(TEMP_DIRECTORY, scene)
    else:
        out_path_template = _get_export_path("vdb")

    rop = _create_rop("vdb", "vdb_export")
    rop.parm('soppath').set(sop_path)
    for parm_name in ('file', 'filename'):
        if rop.parm(parm_name):
            rop.parm(parm_name).set(_normalize_slashes(out_path_template))
            break

    if is_sequence:
        rop.parm('trange').set(1)
        rop.parm('f1').set(int(frame_range[0]))
        rop.parm('f2').set(int(frame_range[1]))
        rop.parm('f3').set(1)
    else:
        rop.parm('trange').set(0)

    rop.render()

    # Для sequence добавляем первый кадр в recent
    if is_sequence:
        first = out_path_template.replace("$F4", "{:04d}".format(int(frame_range[0])))
        update_recent_json(first)
        return first
    update_recent_json(out_path_template)
    _ui_status("PROKLADKA: VDB exported → {}".format(out_path_template))
    return out_path_template


def export_alembic(sop_path: str, frame_range: tuple = None) -> str:
    """Экспорт Alembic (.abc) из SOP."""
    if not os.path.exists(TEMP_DIRECTORY):
        os.makedirs(TEMP_DIRECTORY)

    out_path = _get_export_path("alembic")

    rop = _create_rop("alembic", "abc_export")
    # OUT-context alembic использует 'root' (/obj), SOP-context — 'soppath'
    if rop.parm('soppath'):
        rop.parm('soppath').set(sop_path)
    elif rop.parm('root'):
        rop.parm('root').set('/obj')

    for parm_name in ('filename', 'file'):
        if rop.parm(parm_name):
            rop.parm(parm_name).set(_normalize_slashes(out_path))
            break

    _set_frame_range(rop, frame_range or (1, 1))
    rop.render()

    update_recent_json(out_path)
    _ui_status("PROKLADKA: Alembic exported → {}".format(out_path))
    return out_path


def export_usd(lop_path: str, frame_range: tuple = None) -> str:
    """
    Экспорт USD через Solaris.
    lop_path — путь к LOP node (например /stage/OUTPUT).
    """
    if not os.path.exists(TEMP_DIRECTORY):
        os.makedirs(TEMP_DIRECTORY)

    out_path = _get_export_path("usd")

    rop = _create_rop("usd", "usd_export")
    # USD ROP использует 'loppath'
    if rop.parm('loppath'):
        rop.parm('loppath').set(lop_path)
    for parm_name in ('outputimage', 'filename', 'file'):
        if rop.parm(parm_name):
            rop.parm(parm_name).set(_normalize_slashes(out_path))
            break

    _set_frame_range(rop, frame_range or (1, 1))
    rop.render()

    update_recent_json(out_path)
    _ui_status("PROKLADKA: USD exported → {}".format(out_path))
    return out_path


# ════════════════════════════════════════════════════════════════════════════
# IMPORT — авто-detect по расширению
# ════════════════════════════════════════════════════════════════════════════

def _check_and_fix_scale(sop: hou.Node) -> str:
    """
    Проверить масштаб импортированной геометрии по bounding box.
    Houdini = метры (1 unit = 1m).

    Эвристика по максимальной стороне bbox:
      > 100 units  → возможно сантиметры → scale 0.01 (auto-fix)
      < 0.01       → возможно километры  → scale 100 (auto-fix)
      0.01–100     → метры, корректно

    Возвращает строку-отчёт.
    """
    try:
        geo = sop.geometry()
        if geo is None:
            return "no geometry"
        bbox = geo.boundingBox()
        size = bbox.sizevec()
        max_dim = max(abs(size[0]), abs(size[1]), abs(size[2]))

        if max_dim == 0:
            return "empty bbox"

        # Эвристика масштаба
        if max_dim > 100:
            # Слишком большое — вероятно сантиметры, исправить на метры
            xform = sop.createInputNode(0, 'xform') if False else None
            # Создать Transform SOP после file SOP
            parent = sop.parent()
            transform = parent.createNode('xform', 'scale_fix')
            transform.setInput(0, sop)
            transform.parm('scale').set((0.01, 0.01, 0.01))
            transform.setDisplayFlag(True)
            transform.setRenderFlag(True)
            sop.setDisplayFlag(False)
            sop.setRenderFlag(False)
            return ("AUTO-FIXED: bbox {} units (likely cm) → applied scale 0.01"
                    .format(round(max_dim, 1)))

        elif max_dim < 0.01:
            # Слишком маленькое — вероятно километры
            parent = sop.parent()
            transform = parent.createNode('xform', 'scale_fix')
            transform.setInput(0, sop)
            transform.parm('scale').set((100, 100, 100))
            transform.setDisplayFlag(True)
            transform.setRenderFlag(True)
            sop.setDisplayFlag(False)
            sop.setRenderFlag(False)
            return ("AUTO-FIXED: bbox {} units (likely km) → applied scale 100"
                    .format(round(max_dim, 5)))

        else:
            return "OK: bbox {} units (meters)".format(round(max_dim, 2))

    except Exception as e:
        return "scale check failed: {}".format(e)


def import_file(path: str, name_hint: str = "") -> hou.Node:
    """
    Импорт файла в Houdini. Авто-detect по расширению.
    Создаёт SOP node в /obj/prokladka_imports/.
    Проверяет масштаб по bbox, auto-fix при расхождениях.

    Возвращает созданный SOP node или None при ошибке.
    """
    if not os.path.exists(path):
        _ui_message("File not found: {}".format(path))
        return None

    ext = path.lower().rsplit('.', 1)[-1] if '.' in path else ""
    base_name = name_hint or os.path.splitext(os.path.basename(path))[0]
    base_name = base_name.replace(".", "_").replace(" ", "_")[:30]

    # Создать /obj/prokladka_imports/ subnet
    imports = hou.node('/obj/prokladka_imports')
    if not imports:
        imports = hou.node('/obj').createNode('subnet', 'prokladka_imports')

    # Существующий imp_<name> -> обновить (smart refresh), иначе создать
    existing = imports.node('imp_' + base_name)
    if existing is not None:
        geo = existing
        for ch in geo.children():
            fp = ch.parm('file') or ch.parm('fileName')
            if fp is not None:
                fp.set(_normalize_slashes(path))
                _ui_status(
                    "PROKLADKA: refreshed {} <- {}".format(
                        geo.name(), os.path.basename(path)))
                return ch
    geo = imports.createNode('geo', 'imp_' + base_name)

    try:
        if ext == 'fbx':
            sop = geo.createNode('file')
            sop.parm('file').set(_normalize_slashes(path))
        elif ext == 'vdb':
            sop = geo.createNode('file')
            sop.parm('file').set(_normalize_slashes(path))
        elif ext in ('abc', 'alembic'):
            sop = geo.createNode('alembic')
            for parm_name in ('fileName', 'file', 'filename'):
                if sop.parm(parm_name):
                    sop.parm(parm_name).set(_normalize_slashes(path))
                    break
        elif ext in ('usd', 'usda', 'usdc'):
            sop = geo.createNode('usdimport')
            for parm_name in ('file', 'filename', 'filepath'):
                if sop.parm(parm_name):
                    sop.parm(parm_name).set(_normalize_slashes(path))
                    break
        else:
            _ui_message("Unknown format: .{}".format(ext))
            geo.destroy()
            return None

        sop.setDisplayFlag(True)
        sop.setRenderFlag(True)
        sop.setCurrent(True, clear_all_selected=True)

        # Проверка масштаба (только для геометрии, не VDB)
        scale_report = "skipped (vdb)"
        if ext != 'vdb':
            scale_report = _check_and_fix_scale(sop)

        # Показать импорт во вьюпорте: display на сабнете + фрейм камеры
        try:
            imports.setDisplayFlag(True)
            imports.setSelected(True, clear_all_selected=True)
            pt = hou.ui.paneTabUnderCursor()
            if pt and pt.type() == hou.paneTabType.SceneViewer:
                pt.frameView([imports])
        except Exception:
            pass

        _ui_status(
            "PROKLADKA: imported {} ({}) | scale: {}".format(
                os.path.basename(path), ext, scale_report))
        print("[PROKLADKA] Import: {} | Scale: {}".format(
            os.path.basename(path), scale_report))

        return sop
    except Exception as e:
        _ui_message("Import failed: {}".format(e))
        geo.destroy()
        return None


# ════════════════════════════════════════════════════════════════════════════
# NAMING
# ════════════════════════════════════════════════════════════════════════════

def _detect_node_suffix(node: hou.Node) -> str:
    """Определить тип-суффикс для Houdini node по его типу/данным."""
    try:
        cat = node.type().category().name()
        if cat == "Sop":
            dtype = detect_data_type(node)
            if dtype == "volume":
                return "_vdb"
            elif dtype == "anim":
                return "_abc"
            return "_geo"
        elif cat == "Lop":
            return "_usd"
        elif node.type().name() == "null":
            return "_null"
    except Exception:
        pass
    return "_geo"


def apply_hou_naming(node: hou.Node, preset_name: str = "Houdini",
                     recursive: bool = True) -> int:
    """
    Применить Houdini naming preset к node (и рекурсивно к детям).
    Возвращает количество переименованных nodes.
    """
    preset = HOUDINI_NAMING_PRESETS.get(preset_name, HOUDINI_NAMING_PRESETS["Houdini"])
    renamed = 0

    def _process(n):
        nonlocal renamed
        current = n.name()
        suffix = _detect_node_suffix(n)
        # Не добавлять если уже есть
        if current.endswith(suffix):
            new_name = current
        else:
            new_name = current + suffix
        # lowercase если в preset
        if preset.get("lowercase", False):
            new_name = new_name.lower()
        if new_name != current:
            try:
                n.setName(new_name)
                renamed += 1
            except Exception:
                pass
        if recursive and hasattr(n, 'children'):
            for child in n.children():
                _process(child)

    _process(node)
    return renamed


def set_primitive_names(geometry: hou.Geometry, base_name: str) -> int:
    """
    Назначить @name атрибут на примитивы — управляет FBX/USD hierarchy.
    Возвращает количество прims.
    """
    try:
        # Создать/получить атрибут
        try:
            geometry.addAttrib(hou.attribType.Prim, 'name', '')
        except Exception:
            pass  # already exists
        for i, prim in enumerate(geometry.prims()):
            prim.setAttribValue('name', "{}_{}".format(base_name, i))
        return len(geometry.prims())
    except Exception as e:
        _ui_status("PROKLADKA: set prim names failed: {}".format(e))
        return 0


# ════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR — используется UI
# ════════════════════════════════════════════════════════════════════════════

def export_current(format_key: str, frame_range: tuple = None) -> str:
    """
    Экспортировать текущий SOP/LOP в выбранный формат.
    Возвращает путь к файлу или "" при ошибке.
    """
    try:
        if format_key == "usd":
            node = get_active_lop()
            return export_usd(node.path(), frame_range)
        else:
            node = get_active_sop()
            if format_key == "fbx":
                return export_fbx(node.path(), frame_range)
            elif format_key == "vdb":
                return export_vdb(node.path(), frame_range)
            elif format_key == "alembic":
                return export_alembic(node.path(), frame_range)
            else:
                raise ValueError("Unknown format: {}".format(format_key))
    except Exception as e:
        _ui_message("Export failed: {}".format(e))
        return ""


def get_current_frame_range() -> tuple:
    """Текущий frame range сцены (start, end)."""
    try:
        start = int(hou.playbar.frameRange()[0])
        end = int(hou.playbar.frameRange()[1])
        return (start, end)
    except Exception:
        return (1, 1)


# ════════════════════════════════════════════════════════════════════════════
# LAUNCHER — импортируется из __init__.py
# ════════════════════════════════════════════════════════════════════════════

def launch():
    """Открыть Qt panel PROKLADKA."""
    try:
        from .bridge_qt import launch as _launch_qt
        return _launch_qt()
    except ImportError:
        # Если вызывается напрямую (не как package)
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from bridge_qt import launch as _launch_qt
        return _launch_qt()


if __name__ == "__main__":
    # При запуске через Python Source Editor
    launch()
