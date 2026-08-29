# -*- coding: utf-8 -*-
"""
prokladka_ui.py — Editor Utility Widget panel для PROKLADKA (UE 5.7+).

Автоматически создаёт /Game/Prokladka/BP_ProkladkaPanel (EditorUtilityWidget
Blueprint), программно строит UMG-дерево, биндит кнопки к Python-callbacks.
Панель открывается как dockable tab (как панели в других DCC).

Использование:
    import prokladka
    prokladka.open_panel()
"""
from __future__ import annotations

import os

try:
    import unreal
except ImportError:
    raise ImportError("prokladka_ui is UE-only")

# Ядро импорта (тот же пакет). В UE пакет называется "prokladka".
try:
    from . import prokladka_ue as core
    from . import prokladka_settings as settings
except ImportError:
    import prokladka_ue as core
    import prokladka_settings as settings


# ════════════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════════════════════

PANEL_BP_PATH = "/Game/Prokladka/BP_ProkladkaPanel"
PANEL_PACKAGE = "/Game/Prokladka"
PANEL_TAB_LABEL = "PROKLADKA"

MESH_TYPES = ["auto", "static", "skeletal"]
MESH_TYPE_LABELS = {
    "auto":     "Auto (detect)",
    "static":   "Force Static",
    "skeletal": "Force Skeletal",
}

# Живые ссылки на spawned-панель (заполняются в open_panel)
_live = {
    "widget": None,       # EditorUtilityWidget instance
    "status": None,       # TextBlock статуса
    "recent_text": None,  # TextBlock текущего recent
    "mesh_type_btn": None,
    "mesh_type_state": 0,  # индекс в MESH_TYPES
    "recents": [],
    "recent_idx": 0,
    "tex_checkbox": None,
    "path_boxes": {},     # {"import_base": EditableTextBox, ...}
}


# ════════════════════════════════════════════════════════════════════════════
# ЗАЩИТНЫЕ ХЕЛПЕРЫ (UE Python API местами сломан/различается по версиям)
# ════════════════════════════════════════════════════════════════════════════

def _log(msg: str) -> None:
    unreal.log("[PROKLADKA] " + str(msg))


def _warn(msg: str) -> None:
    unreal.log_warning("[PROKLADKA] " + str(msg))


def _safe_set(obj, prop, value) -> None:
    """set_editor_property с игнорированием несуществующих свойств."""
    try:
        obj.set_editor_property(prop, value)
    except Exception:
        pass


def _T(text: str):
    """str → unreal.Text (fallback: сырой str)."""
    try:
        return unreal.Text(str(text))
    except Exception:
        return str(text)


def _name(widget, name: str) -> None:
    """Дать имя виджету (для поиска после spawn). Fallback: без имени."""
    try:
        widget.rename(name)
    except Exception:
        try:
            widget.set_editor_property("name", name)
        except Exception:
            pass


def _bind_click(button, callback) -> None:
    """Биндить on_clicked. Разные версии UE: add_callable / bind_callable."""
    try:
        button.on_clicked.add_callable(callback)
        return
    except AttributeError:
        pass
    except Exception:
        pass
    try:
        button.on_clicked.bind_callable(callback)
    except Exception as e:
        _warn("bind click failed: {}".format(e))


def _set_text(widget, text: str) -> None:
    """Обновить TextBlock текст (живой или template)."""
    if widget is None:
        return
    try:
        widget.set_text(_T(text))
    except Exception:
        pass


def _set_status(text: str, color=None) -> None:
    """Обновить строку статуса панели."""
    st = _live.get("status")
    if st is None:
        _log("status: " + text)
        return
    _set_text(st, text)
    if color is not None:
        try:
            lc = unreal.LinearColor(*color)
            st.set_editor_property("color_and_opacity", unreal.SlateColor(lc))
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
# ПОСТРОЕНИЕ UMG-ДЕРЕВА
# ════════════════════════════════════════════════════════════════════════════

def _mk(cls, name: str):
    """Создать UMG виджет с именем. Возвращает None если класс недоступен."""
    try:
        cls_obj = getattr(unreal, cls)  # НЕ getattr с default — сломан в UE
        w = cls_obj()
        _name(w, name)
        return w
    except AttributeError:
        _warn("Widget class not found: {}".format(cls))
        return None
    except Exception as e:
        _warn("Widget {} creation failed: {}".format(cls, e))
        return None


def _add_child_vb(vbox, child) -> None:
    """add_child_to_vertical_box с fallback на add_child."""
    if vbox is None or child is None:
        return
    try:
        vbox.add_child_to_vertical_box(child)
        return
    except Exception:
        pass
    try:
        vbox.add_child(child)
    except Exception as e:
        _warn("add_child failed: {}".format(e))


def _add_child_hb(hbox, child) -> None:
    if hbox is None or child is None:
        return
    try:
        hbox.add_child_to_horizontal_box(child)
        return
    except Exception:
        pass
    try:
        hbox.add_child(child)
    except Exception as e:
        _warn("add_child failed: {}".format(e))


def _label(text: str, name: str = "", size: int = 0):
    """TextBlock с текстом."""
    tb = _mk("TextBlock", name or ("Txt_" + text[:12].replace(" ", "_")))
    if tb is None:
        return None
    _set_text(tb, text)
    if size:
        try:
            fo = unreal.SlateFontInfo()
            _safe_set(fo, "size", size)
            _safe_set(tb, "font", fo)
        except Exception:
            pass
    return tb


def _section_header(title: str):
    """Заголовок секции в стиле STUKACH: '── TITLE ──'."""
    return _label("-- {} --".format(title), name="Hdr_" + title)


def build_panel_tree():
    """
    Построить корневой VerticalBox со всеми секциями.
    Возвращает (root, widgets_dict). widgets_dict — именованные виджеты
    для последующего бинда на живом инстансе.
    """
    root = _mk("VerticalBox", "ProkladkaRoot")
    if root is None:
        return None, {}

    w = {}  # registry: имя → виджет

    # ── Header ──────────────────────────────────────────────────────────────
    header_hb = _mk("HorizontalBox", "HeaderBox")
    title = _label("PROKLADKA", "Txt_Title", size=16)
    status = _label("READY", "Txt_Status")
    if header_hb:
        _add_child_hb(header_hb, title)
        _add_child_hb(header_hb, status)
        _add_child_vb(root, header_hb)
    w["status"] = status

    # ── Recent FBX ──────────────────────────────────────────────────────────
    _add_child_vb(root, _section_header("RECENT FBX"))
    recent_hb = _mk("HorizontalBox", "RecentBox")
    btn_prev = _mk("Button", "BtnRecentPrev")
    _add_child_hb(btn_prev, _label("<", "Txt_RecentPrev")) if btn_prev else None
    btn_next = _mk("Button", "BtnRecentNext")
    _add_child_hb(btn_next, _label(">", "Txt_RecentNext")) if btn_next else None
    recent_text = _label("(no recent)", "Txt_Recent")
    if recent_hb:
        _add_child_hb(recent_hb, btn_prev)
        _add_child_hb(recent_hb, recent_text)
        _add_child_hb(recent_hb, btn_next)
        _add_child_vb(root, recent_hb)
    w["recent_prev"] = btn_prev
    w["recent_next"] = btn_next
    w["recent_text"] = recent_text

    # ── Import ──────────────────────────────────────────────────────────────
    _add_child_vb(root, _section_header("IMPORT"))
    mt_row = _mk("HorizontalBox", "MeshTypeRow")
    mt_label = _label("Mesh type:", "Txt_MeshTypeLabel")
    mt_btn = _mk("Button", "BtnMeshType")
    _add_child_hb(mt_btn, _label(MESH_TYPE_LABELS["auto"], "Txt_MeshType")) if mt_btn else None
    if mt_row:
        _add_child_hb(mt_row, mt_label)
        _add_child_hb(mt_row, mt_btn)
        _add_child_vb(root, mt_row)
    w["mesh_type_btn"] = mt_btn

    btn_import = _mk("Button", "BtnImport")
    _add_child_hb(btn_import, _label("IMPORT FBX", "Txt_Import")) if btn_import else None
    _add_child_vb(root, btn_import)
    w["import"] = btn_import

    btn_browse = _mk("Button", "BtnBrowse")
    _add_child_hb(btn_browse, _label("Browse...", "Txt_Browse")) if btn_browse else None
    _add_child_vb(root, btn_browse)
    w["browse"] = btn_browse

    # ── Naming (info) ───────────────────────────────────────────────────────
    _add_child_vb(root, _section_header("NAMING"))
    _add_child_vb(root, _label(
        "UE convention auto-applied on import:", "Txt_NamingInfo1"))
    _add_child_vb(root, _label(
        "SM_/SK_/T_/MI_ + PascalCase", "Txt_NamingInfo2"))

    # ── Settings ────────────────────────────────────────────────────────────
    _add_child_vb(root, _section_header("SETTINGS"))
    path_boxes = {}
    for key, caption in (
        ("import_base", "Import path:"),
        ("master_material", "Master mat:"),
        ("import_scale", "Scale:"),
    ):
        row = _mk("HorizontalBox", "Row_" + key)
        lbl = _label(caption, "Txt_" + key)
        box = _mk("EditableTextBox", "Edit_" + key)
        if box is not None:
            _set_text(box, str(settings.get(key)))
        if row:
            _add_child_hb(row, lbl)
            _add_child_hb(row, box)
            _add_child_vb(root, row)
        path_boxes[key] = box
    w["path_boxes"] = path_boxes

    tex_cb = _mk("CheckBox", "CbAutoTextures")
    if tex_cb is not None:
        try:
            tex_cb.set_is_checked(bool(settings.get("auto_import_textures")))
        except Exception:
            pass
    tex_row = _mk("HorizontalBox", "Row_AutoTex")
    if tex_row:
        _add_child_hb(tex_row, tex_cb)
        _add_child_hb(tex_row, _label("Auto-import textures", "Txt_AutoTex"))
        _add_child_vb(root, tex_row)
    w["tex_checkbox"] = tex_cb

    btn_save = _mk("Button", "BtnSaveSettings")
    _add_child_hb(btn_save, _label("SAVE SETTINGS", "Txt_Save")) if btn_save else None
    _add_child_vb(root, btn_save)
    w["save"] = btn_save

    return root, w


# ════════════════════════════════════════════════════════════════════════════
# BLUEPRINT ASSET
# ════════════════════════════════════════════════════════════════════════════

def ensure_panel_blueprint():
    """
    Создать /Game/Prokladka/BP_ProkladkaPanel если нет, построить дерево,
    сохранить. Возвращает Blueprint asset или None.
    """
    try:
        ESS = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        exists = ESS.does_asset_exist(PANEL_BP_PATH)
    except Exception:
        exists = unreal.EditorAssetLibrary.does_asset_exist(PANEL_BP_PATH)

    if exists:
        bp = unreal.load_asset(PANEL_BP_PATH)
    else:
        try:
            factory = unreal.EditorUtilityWidgetBlueprintFactory()
            _safe_set(factory, "parent_class", unreal.EditorUtilityWidget)
        except Exception as e:
            _warn("EUW factory unavailable: {}".format(e))
            return None
        try:
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            bp = asset_tools.create_asset(
                "BP_ProkladkaPanel", PANEL_PACKAGE,
                unreal.EditorUtilityWidgetBlueprint, factory)
        except Exception as e:
            _warn("EUW asset creation failed: {}".format(e))
            return None

    if not bp:
        _warn("Panel Blueprint unavailable: {}".format(PANEL_BP_PATH))
        return None

    # (Пере)строить дерево — идемпотентно, заодно обновляет layout
    root, _widgets = build_panel_tree()
    if root is None:
        _warn("UMG tree build failed — panel will be empty")
        return bp

    try:
        tree = bp.get_editor_property("widget_tree")
    except Exception:
        tree = None
    if tree is None:
        try:
            tree = bp.widget_tree
        except Exception:
            tree = None
    if tree is None:
        _warn("widget_tree not accessible on Blueprint")
        return bp

    try:
        tree.set_editor_property("root_widget", root)
    except Exception:
        try:
            tree.root_widget = root
        except Exception as e:
            _warn("root_widget set failed: {}".format(e))
            return bp

    try:
        unreal.EditorAssetLibrary.save_asset(PANEL_BP_PATH)
        _log("Panel Blueprint ready: {}".format(PANEL_BP_PATH))
    except Exception as e:
        _warn("save_asset failed: {}".format(e))
    return bp


# ════════════════════════════════════════════════════════════════════════════
# ПОИСК ВИДЖЕТОВ НА ЖИВОМ ИНСТАНСЕ
# ════════════════════════════════════════════════════════════════════════════

def _iter_children(panel):
    """Итерация детей PanelWidget — разные API по версиям."""
    for meth in ("get_children",):
        try:
            kids = getattr(panel, meth)()
            # ArrayWrapper → list
            try:
                kids = list(kids)
            except Exception:
                pass
            if kids:
                return kids
            return []
        except AttributeError:
            continue
        except Exception:
            continue
    try:
        count = panel.get_children_count()
        return [panel.get_child_at(i) for i in range(count)]
    except Exception:
        return []


def _find_by_name(widget, name: str, depth: int = 0):
    """Рекурсивный поиск виджета по имени в живом дереве."""
    if widget is None or depth > 12:
        return None
    try:
        if str(widget.get_name()) == name:
            return widget
    except Exception:
        pass
    for child in _iter_children(widget):
        found = _find_by_name(child, name, depth + 1)
        if found is not None:
            return found
    return None


def _bind_live_widgets(widget: object) -> None:
    """Найти виджеты по имени на живом EUW и забиндить callbacks."""
    _live["widget"] = widget

    def find(name):
        # 1. Прямой API UserWidget.get_widget_from_name
        try:
            result = widget.get_widget_from_name(unreal.Name(name))
            if result is not None:
                return result
        except Exception:
            pass
        # 2. Рекурсивный обход дерева
        try:
            tree = widget.widget_tree
            try:
                result = tree.find_widget(unreal.Name(name))
                if result is not None:
                    return result
            except Exception:
                pass
            root = None
            try:
                root = tree.get_editor_property("root_widget")
            except Exception:
                try:
                    root = tree.root_widget
                except Exception:
                    root = None
            if root is not None:
                return _find_by_name(root, name)
        except Exception:
            pass
        return _find_by_name(widget, name)

    # Status + recent text
    _live["status"] = find("Txt_Status")
    _live["recent_text"] = find("Txt_Recent")

    # Recent prev/next
    btn_prev = find("BtnRecentPrev")
    btn_next = find("BtnRecentNext")
    if btn_prev:
        _bind_click(btn_prev, on_recent_prev)
    if btn_next:
        _bind_click(btn_next, on_recent_next)

    # Mesh type cycle
    mt_btn = find("BtnMeshType")
    _live["mesh_type_btn"] = mt_btn
    if mt_btn:
        _bind_click(mt_btn, on_mesh_type_clicked)
        try:
            last = str(settings.get("last_mesh_type", "auto"))
            _live["mesh_type_state"] = MESH_TYPES.index(last) if last in MESH_TYPES else 0
        except Exception:
            _live["mesh_type_state"] = 0
        _update_mesh_type_label()

    # Import / Browse
    btn_import = find("BtnImport")
    if btn_import:
        _bind_click(btn_import, on_import_clicked)
    btn_browse = find("BtnBrowse")
    if btn_browse:
        _bind_click(btn_browse, on_browse_clicked)

    # Settings
    _live["path_boxes"] = {}
    for key in ("import_base", "master_material", "import_scale"):
        box = find("Edit_" + key)
        if box:
            _live["path_boxes"][key] = box
            try:
                box.set_text(_T(str(settings.get(key))))
            except Exception:
                pass
    tex_cb = find("CbAutoTextures")
    _live["tex_checkbox"] = tex_cb
    btn_save = find("BtnSaveSettings")
    if btn_save:
        _bind_click(btn_save, on_save_settings_clicked)

    _refresh_recent_display()
    _set_status("READY", (0.4, 0.8, 0.4, 1.0))
    _log("Panel widgets bound")


# ════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ════════════════════════════════════════════════════════════════════════════

def _refresh_recent_display() -> None:
    """Перечитать bridge_last.json и показать текущий recent."""
    recents = core.read_recent_fbx()
    _live["recents"] = recents
    if not recents:
        _live["recent_idx"] = 0
        _set_text(_live.get("recent_text"), "(no recent exports)")
        return
    idx = _live.get("recent_idx", 0)
    idx = max(0, min(idx, len(recents) - 1))
    _live["recent_idx"] = idx
    path = recents[idx]
    label = "[{}/{}] {}".format(idx + 1, len(recents), os.path.basename(path))
    _set_text(_live.get("recent_text"), label)


def on_recent_prev() -> None:
    if _live.get("recents"):
        _live["recent_idx"] = max(0, _live.get("recent_idx", 0) - 1)
        _refresh_recent_display()


def on_recent_next() -> None:
    recents = _live.get("recents") or []
    if recents:
        _live["recent_idx"] = min(len(recents) - 1, _live.get("recent_idx", 0) + 1)
        _refresh_recent_display()


def _update_mesh_type_label() -> None:
    state = _live.get("mesh_type_state", 0)
    key = MESH_TYPES[state]
    # Обновить текст внутри кнопки (первый ребёнок TextBlock)
    btn = _live.get("mesh_type_btn")
    if btn:
        for child in _iter_children(btn):
            _set_text(child, MESH_TYPE_LABELS[key])
            break


def on_mesh_type_clicked() -> None:
    """Циклический переключатель: auto → static → skeletal → auto."""
    _live["mesh_type_state"] = (_live.get("mesh_type_state", 0) + 1) % len(MESH_TYPES)
    key = MESH_TYPES[_live["mesh_type_state"]]
    settings.set("last_mesh_type", key)
    _update_mesh_type_label()


def _current_fbx() -> str:
    """Путь FBX: из recent-списка, иначе ''."""
    recents = _live.get("recents") or core.read_recent_fbx()
    if recents:
        idx = min(_live.get("recent_idx", 0), len(recents) - 1)
        return recents[idx]
    return ""


def on_browse_clicked() -> None:
    """Выбрать FBX через file dialog → положить в recent selection."""
    try:
        path = unreal.EditorDialog.open_file(
            "Select FBX", "FBX (*.fbx)|*.fbx", False)
    except Exception as e:
        _warn("file picker failed: {}".format(e))
        return
    if path and os.path.exists(path):
        # Добавить выбранный путь в начало списка recent
        recents = _live.get("recents") or []
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        _live["recents"] = recents
        _live["recent_idx"] = 0
        _refresh_recent_display()
        settings.set("last_fbx_path", path)


def on_import_clicked() -> None:
    """IMPORT FBX — полный pipeline из core."""
    fbx_path = _current_fbx()
    if not fbx_path:
        _set_status("NO FBX — use Browse", (1.0, 0.7, 0.2, 1.0))
        _warn("No FBX selected — use Browse")
        return

    key = MESH_TYPES[_live.get("mesh_type_state", 0)]
    master = ""
    try:
        box = _live.get("path_boxes", {}).get("master_material")
        if box:
            master = str(box.get_text())
    except Exception:
        pass

    _set_status("IMPORTING...", (0.4, 0.7, 1.0, 1.0))
    _log("Import started: {} (as {})".format(fbx_path, key))
    try:
        kwargs = {}
        if master:
            kwargs["master_material_path"] = master
        result = core.process_bridge_import(fbx_path, mesh_type=key, **kwargs)
    except Exception as e:
        _set_status("ERROR: {}".format(e), (1.0, 0.3, 0.3, 1.0))
        _warn("import failed: {}".format(e))
        return

    if result.get("errors"):
        _set_status("ERROR (see log)", (1.0, 0.3, 0.3, 1.0))
        return

    n = len(result.get("final_paths", []))
    _set_status("IMPORTED {} assets".format(n), (0.4, 0.8, 0.4, 1.0))
    settings.set("last_fbx_path", fbx_path)
    # Обновить recent из общего bridge_last.json
    _refresh_recent_display()


def on_save_settings_clicked() -> None:
    """Сохранить настройки из полей панели."""
    boxes = _live.get("path_boxes", {})
    for key in ("import_base", "master_material", "import_scale"):
        box = boxes.get(key)
        if not box:
            continue
        try:
            value = str(box.get_text())
        except Exception:
            continue
        if key == "import_scale":
            try:
                settings.set(key, float(value))
            except ValueError:
                _warn("Scale is not a number: {}".format(value))
                continue
        else:
            settings.set(key, value)
    tex_cb = _live.get("tex_checkbox")
    if tex_cb:
        try:
            settings.set("auto_import_textures", bool(tex_cb.is_checked()))
        except Exception:
            pass
    _set_status("SETTINGS SAVED", (0.4, 0.8, 0.4, 1.0))


# ════════════════════════════════════════════════════════════════════════════
# OPEN / CLOSE
# ════════════════════════════════════════════════════════════════════════════

def open_panel() -> bool:
    """
    Открыть панель как dockable tab. Главная точка входа.
    Возвращает True при успехе.
    """
    bp = ensure_panel_blueprint()
    if not bp:
        _warn("Cannot open panel: Blueprint unavailable")
        return False

    try:
        eus = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem)
    except Exception as e:
        _warn("EditorUtilitySubsystem unavailable: {}".format(e))
        return False

    widget = None
    try:
        # UE 5.1+: возвращает EditorUtilityWidget instance
        widget = eus.spawn_and_register_tab(bp)
    except Exception as e:
        _warn("spawn_and_register_tab failed: {}".format(e))
        try:
            widget = eus.spawn_widget(bp)
        except Exception as e2:
            _warn("spawn_widget failed: {}".format(e2))
            return False

    if widget is None:
        _warn("Panel spawn returned None")
        return False

    _bind_live_widgets(widget)
    _log("Panel opened ({} tab)".format(PANEL_TAB_LABEL))
    return True


def close_panel() -> None:
    """Закрыть панель (если открыта)."""
    widget = _live.get("widget")
    if widget is None:
        return
    try:
        widget.remove_from_parent()
    except Exception:
        pass
    _live["widget"] = None
    _log("Panel closed")
