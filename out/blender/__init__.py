"""
PROKLADKA — FBX-мост между Blender и Maya (стиль STUKACH, naming presets)
==========================================================================
Пайплайн-инструмент: FBX I/O, naming presets, transform apply, hierarchy utils.
Визуально стилизован под STUKACH (collapsible-секции, status badge, big buttons).

Возможности:
  - Экспорт/импорт FBX (C:\\temp\\<scene>_bridge.fbx)
  - Legacy scale — escape hatch для чужих ассетов (режим V6)
  - Naming presets — редактируемые пресеты нейминга (Default, Plain, Unreal, Dots)
  - Collection↔Empty, MayaRotate (нативный transform_apply)

Нейминг-пресеты хранятся в AddonPreferences, доступны во всех .blend.
"""

import bpy
import os
import sys
import json
import time
from bpy.props import (BoolProperty, StringProperty, IntProperty,
                       CollectionProperty, PointerProperty, EnumProperty)
from bpy.types import PropertyGroup, Panel, Operator, UIList, AddonPreferences
from bpy.utils import register_class, unregister_class

bl_info = {
    "name": "PROKLADKA",
    "blender": (4, 5, 0),
    "category": "Import-Export",
    "author": "Ismailov Dmitry / VVERH adapt",
    "version": (1, 9, 0),
    "description": "FBX-мост между Blender и Maya. Naming presets, transform apply, hierarchy utils.",
    "location": "View3D > Sidebar > PROKLADKA",
}

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------
TEMP_DIRECTORY = r"C:\temp"
RECENT_JSON    = os.path.join(TEMP_DIRECTORY, "bridge_last.json")
RECENT_MAX     = 5


# Импорт rig-модулей. Т.к. аддон — package, используем relative imports.
try:
    from . import rig_blender as _rig_blender
    from . import rig_recipe as _rig_recipe
    _RIG_AVAILABLE = True
except Exception as _e:
    _RIG_AVAILABLE = False
    print("[PROKLADKA] rig modules not available: {}".format(_e))


def get_temp_directory():
    return TEMP_DIRECTORY


def get_scene_asset_name():
    """Имя ассета для FBX: имя .blend / активной коллекции / 'untitled'."""
    blend = bpy.data.filepath
    if blend:
        name = os.path.splitext(os.path.basename(blend))[0]
    else:
        try:
            name = bpy.context.view_layer.active_layer_collection.collection.name
        except Exception:
            name = ""
    if not name:
        name = "untitled"
    safe = name.replace(".", "_").replace(" ", "_").replace("/", "_").replace("\\", "_")
    return safe or "untitled"


def get_fbx_path():
    return os.path.join(TEMP_DIRECTORY, f"{get_scene_asset_name()}_bridge.fbx")


def update_recent_json(path):
    try:
        recent = []
        if os.path.exists(RECENT_JSON):
            with open(RECENT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    recent = [p for p in data if isinstance(p, str)]
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:RECENT_MAX]
        if not os.path.exists(TEMP_DIRECTORY):
            os.makedirs(TEMP_DIRECTORY)
        with open(RECENT_JSON, "w", encoding="utf-8") as f:
            json.dump(recent, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _read_recent_fbx():
    """Прочитать bridge_last.json → список существующих FBX путей.
    Симметрично с _read_recent_paths() в Maya."""
    paths = []
    try:
        if os.path.exists(RECENT_JSON):
            with open(RECENT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    paths = [p for p in data if isinstance(p, str)]
    except Exception:
        pass
    return [p for p in paths if os.path.exists(p)][:RECENT_MAX]


# ════════════════════════════════════════════════════════════════════════════
# NAMING PRESETS
# ════════════════════════════════════════════════════════════════════════════

class NamingPreset(PropertyGroup):
    """Один пресет нейминга. Хранится в AddonPreferences."""
    name: StringProperty(name="Preset Name", default="Default")
    prefix: StringProperty(
        name="Prefix",
        description="Добавляется в начало имени (если ещё нет)",
        default="",
    )
    suffix_mesh: StringProperty(name="Mesh Suffix",  default="_geo")
    suffix_empty: StringProperty(name="Empty Suffix", default="_grp")
    suffix_armature: StringProperty(name="Armature Suffix", default="_skel")
    # Rig-specific: bones (joints) и controls. В Blender применяются к bones armature.
    suffix_joint: StringProperty(name="Joint Suffix",  default="_jnt")
    suffix_control: StringProperty(name="Control Suffix", default="_ctl")
    lowercase: BoolProperty(
        name="Lowercase",
        description="Привести итоговое имя к нижнему регистру",
        default=True,
    )
    dots_to_underscore: BoolProperty(
        name="Dots → Underscore",
        description="Заменить '.' и пробелы на '_'",
        default=True,
    )


def _preset_all_suffixes(preset) -> list:
    """Все суффиксы пресета (для удаления старых перед постановкой новых)."""
    out = []
    for attr in ("suffix_mesh", "suffix_empty", "suffix_armature",
                 "suffix_joint", "suffix_control"):
        s = getattr(preset, attr, "")
        if s:
            out.append(s)
    # dedupe preserving order
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _strip_existing_suffix(name: str, suffixes: list) -> str:
    """Отрезать существующий суффикс из списка (для замены на правильный)."""
    for s in suffixes:
        if s and name.endswith(s):
            return name[:-len(s)]
    return name


def _ensure_prefix(name: str, prefix: str) -> str:
    if prefix and not name.startswith(prefix):
        return prefix + name
    return name


def apply_preset_to_name(obj, preset) -> str:
    """
    Вычислить новое имя объекта по пресету.
    Логика: отрезать старый суффикс → lowercase/dots → prefix → правильный суффикс.
    """
    suffixes = _preset_all_suffixes(preset)
    base = _strip_existing_suffix(obj.name, suffixes)

    # Префикс отрезаем перед lower/dots чтобы не было дублирования
    if preset.prefix and base.startswith(preset.prefix):
        base = base[len(preset.prefix):]

    if preset.dots_to_underscore:
        base = base.replace('.', '_').replace(' ', '_').replace('-', '_')
    if preset.lowercase:
        base = base.lower()

    base = _ensure_prefix(base, preset.prefix)

    # Суффикс по типу
    if obj.type == 'MESH' and preset.suffix_mesh:
        if not base.endswith(preset.suffix_mesh):
            base += preset.suffix_mesh
    elif obj.type == 'EMPTY' and preset.suffix_empty:
        if not base.endswith(preset.suffix_empty):
            base += preset.suffix_empty
    elif obj.type == 'ARMATURE' and preset.suffix_armature:
        if not base.endswith(preset.suffix_armature):
            base += preset.suffix_armature

    return base


# --- Дефолтные пресеты -----------------------------------------------------

def _add_default_preset(presets_col, name, prefix="", s_mesh="_geo",
                        s_empty="_grp", s_arm="_skel",
                        s_jnt="_jnt", s_ctl="_ctl",
                        lower=True, dots=True):
    p = presets_col.add()
    p.name = name
    p.prefix = prefix
    p.suffix_mesh = s_mesh
    p.suffix_empty = s_empty
    p.suffix_armature = s_arm
    p.suffix_joint = s_jnt
    p.suffix_control = s_ctl
    p.lowercase = lower
    p.dots_to_underscore = dots
    return p


_DEFAULT_PRESETS = [
    # name,             prefix, s_mesh,   s_empty, s_arm,       s_jnt,   s_ctl,   lower, dots
    ("Default",         "",     "_geo",   "_grp",  "_skel",     "_jnt",  "_ctl",  True,  True),
    ("Plain lowercase", "",     "",       "",      "",          "",      "",      True,  True),
    ("Unreal",          "",     "_Mesh",  "",      "_SkelMesh", "_jnt",  "_ctl",  False, True),
    ("Dots only",       "",     "",       "",      "",          "",      "",      False, True),
    ("Rig",             "",     "_geo",   "_grp",  "_skel",     "_jnt",  "_ctl",  True,  True),
]


def ensure_default_presets(prefs):
    """Заполнить дефолтные пресеты если коллекция пуста."""
    if len(prefs.presets) > 0:
        return
    for args in _DEFAULT_PRESETS:
        _add_default_preset(prefs.presets, *args)


def get_addon_preferences(context):
    """Получить BridgePreferences текущего аддона."""
    try:
        return context.preferences.addons[__name__].preferences
    except KeyError:
        # При установке single-file имя модуля может отличаться
        return None


def preset_enum_items(self, context):
    """Динамический EnumProperty: список имён пресетов."""
    prefs = get_addon_preferences(context)
    if not prefs or len(prefs.presets) == 0:
        ensure_default_presets(prefs) if prefs else None
    items = []
    if prefs:
        for i, p in enumerate(prefs.presets):
            items.append((str(i), p.name, f"Apply '{p.name}' preset"))
    if not items:
        items.append(("0", "(no presets)", ""))
    return items


# ════════════════════════════════════════════════════════════════════════════
# OPERATORS
# ════════════════════════════════════════════════════════════════════════════

# --- FBX Export/Import -----------------------------------------------------

class ExportBridgeOperator(Operator):
    """Экспорт выделения в C:\\temp\\<scene>_bridge.fbx. rot+scale применяются."""
    bl_idname = "export_scene.bridge_fbx"
    bl_label  = "Export Selected to Bridge FBX"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'ERROR'}, "Нет выделенных объектов для экспорта.")
            context.window_manager.bridge_props.last_status = "ERROR"
            return {'CANCELLED'}

        props = context.window_manager.bridge_props
        legacy = props.legacy_scale

        # ══════════════════════════════════════════════════════════════
        # PRE-EXPORT VALIDATION
        # ══════════════════════════════════════════════════════════════

        # Предупредить о несохранённой сцене (файл будет untitled_bridge.fbx)
        if not bpy.data.filepath:
            self.report({'WARNING'},
                        "Сцена НЕ СОХРАНЕНА — экспорт пойдёт в untitled_bridge.fbx. "
                        "Сохраните сцену (Ctrl+S) для правильного имени файла.")

        # ── Расширить выделение до детей ────────────────────────────────
        # Если выделен только Empty/группа без мешей — добавить всех детей.
        # FBX use_selection=True экспортирует ТОЛЬКО выделенные объекты,
        # дети автоматически не включаются.
        has_mesh = any(o.type == 'MESH' for o in context.selected_objects)
        if not has_mesh:
            to_select = set()
            for obj in context.selected_objects:
                to_select.add(obj)
                for child in obj.children_recursive:
                    to_select.add(child)

            if any(o.type == 'MESH' for o in to_select):
                bpy.ops.object.select_all(action='DESELECT')
                for obj in to_select:
                    obj.select_set(True)
                context.view_layer.objects.active = next(
                    (o for o in to_select if o.type == 'MESH'), None)
                self.report({'INFO'},
                            "Selection expanded to include child meshes")
            else:
                self.report({'WARNING'},
                            "No MESH objects in selection hierarchy — exporting empties only")

        # Зафиксировать ожидания ДО экспорта
        expected_total = len(context.selected_objects)
        expected_meshes = sum(1 for o in context.selected_objects if o.type == 'MESH')

        if not os.path.exists(TEMP_DIRECTORY):
            os.makedirs(TEMP_DIRECTORY)

        # ╀─ Сохранить выделение ПЕРЕД transform_apply ───────────────────
        saved_selection = set(context.selected_objects)
        saved_active = context.view_layer.objects.active

        if not legacy:
            try:
                if context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            except Exception as e:
                self.report({'WARNING'}, f"transform_apply пропущен: {e}")

        # ── Восстановить выделение ПОСЛЕ transform_apply ─────────────────
        bpy.ops.object.select_all(action='DESELECT')
        restored = 0
        for obj in saved_selection:
            try:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
                    restored += 1
            except Exception:
                pass
        if saved_active and saved_active.name in bpy.data.objects:
            context.view_layer.objects.active = saved_active

        if restored < expected_total:
            self.report({'WARNING'},
                        f"Выделение: {restored}/{expected_total} объектов восстановлено")

        fbx_filepath = get_fbx_path()
        global_scale = 0.01 if legacy else 1.0

        # ══════════════════════════════════════════════════════════════
        # EXPORT — настройки из референсного V6 (проверено работает)
        # ══════════════════════════════════════════════════════════════
        # НЕ добавлять: axis_forward, axis_up, object_types, use_visible,
        # use_active_collection — эти параметры ломали экспорт
        # (object_types фильтровал кривые, use_visible мог не существовать).

        bpy.ops.export_scene.fbx(
            filepath=fbx_filepath,
            use_selection=True,
            apply_unit_scale=True,
            bake_anim=False,
            global_scale=global_scale,
        )

        # ══════════════════════════════════════════════════════════════
        # POST-EXPORT VALIDATION
        # ══════════════════════════════════════════════════════════════

        if not os.path.exists(fbx_filepath):
            self.report({'ERROR'}, f"FBX файл не создан: {fbx_filepath}")
            props.last_status = "ERROR"
            return {'CANCELLED'}

        fbx_size = os.path.getsize(fbx_filepath)

        # КРИТИЧЕСКО: файл почти пустой (< 5 KB) при ожидаемых мешах
        if expected_meshes > 0 and fbx_size < 5120:
            self.report({'ERROR'},
                        f"FBX подозрительно мал ({fbx_size // 1024} KB) "
                        f"при {expected_meshes} мешах! Экспорт неполный — "
                        "файл НЕ добавлен в Recent.")
            props.last_status = "ERROR"
            return {'CANCELLED'}

        # WARNING: эвристика — минимум ~300 bytes на меш
        if expected_meshes > 0 and fbx_size < (expected_meshes * 300):
            self.report({'WARNING'},
                        f"FBX {fbx_size // 1024} KB возможно неполный "
                        f"(ожидалось минимум {expected_meshes * 300 // 1024} KB "
                        f"для {expected_meshes} мешей). Проверьте результат в Maya.")

        # Экспорт успешен — обновить recent и статус
        update_recent_json(fbx_filepath)
        props.last_status = "EXPORTED"
        self.report({'INFO'},
                    f"Экспорт: {expected_total} объектов ({expected_meshes} мешей) "
                    f"→ {os.path.basename(fbx_filepath)} ({fbx_size // 1024} KB)")
        return {'FINISHED'}


class ClearRecentOperator(Operator):
    """Очистить историю экспортов (bridge_last.json)."""
    bl_idname = "bridge.clear_recent"
    bl_label  = "Clear Export History"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            with open(RECENT_JSON, "w", encoding="utf-8") as f:
                json.dump([], f)
            # обновить панель
            context.area.tag_redraw()
            self.report({'INFO'}, "Export history cleared")
        except Exception as e:
            self.report({'ERROR'}, str(e))
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class ImportBridgeOperator(Operator):
    """Импорт FBX текущей сцены."""
    bl_idname = "import_scene.bridge_fbx"
    bl_label  = "Import Bridge FBX"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.window_manager.bridge_props
        # Общий recent: последний экспорт из ЛЮБОГО DCC (Houdini/Maya/UE тоже пишут сюда).
        # Fallback — файл по имени своей сцены (старое поведение).
        recent = [p for p in _read_recent_fbx() if p]
        fbx_filepath = recent[0] if recent else get_fbx_path()
        if not os.path.exists(fbx_filepath):
            props.last_status = "ERROR"
            self.report({'ERROR'}, f"Файл не найден: {fbx_filepath}")
            return {'CANCELLED'}

        global_scale = 100.0 if props.legacy_scale else 1.0
        before = set(bpy.data.objects.keys())
        try:
            bpy.ops.import_scene.fbx(filepath=fbx_filepath, global_scale=global_scale)
        except RuntimeError as e:
            props.last_status = "ERROR"
            msg = str(e)
            if "cast_shadow" in msg or "CyclesLightSettings" in msg:
                self.report({'ERROR'},
                    "K-Cycles падает на свете из FBX. Убери свет в исходной сцене "
                    "и переэкспортируй (или обнови K-Cycles).")
            else:
                self.report({'ERROR'}, "Импорт не удался: " + msg[:180])
            return {'CANCELLED'}

        # Правило приёмника: статичные меши -> нода 0/0/1, габариты в мешах
        imported = [o for o in bpy.data.objects
                    if o.name not in before and o.type == 'MESH']
        for o in imported:
            if any(par.type == 'ARMATURE' for par in o.parents):
                continue  # скинутые ассеты не трогаем
            try:
                if max(o.dimensions) > 50.0:
                    o.scale = (0.01, 0.01, 0.01)  # FBX в cm прочитан как м
                bpy.context.view_layer.objects.active = o
                o.select_set(True)
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                o.select_set(False)
            except Exception:
                pass

        props.last_status = "IMPORTED"
        self.report({'INFO'}, f"Импортирован файл: {fbx_filepath}")
        return {'FINISHED'}


# --- Naming ----------------------------------------------------------------

class ApplyNamingPresetOperator(Operator):
    """Применить активный пресет нейминга к выделению."""
    bl_idname = "object.apply_naming_preset"
    bl_label  = "Apply Naming Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.window_manager.bridge_props
        prefs = get_addon_preferences(context)
        if not prefs:
            self.report({'ERROR'}, "Addon preferences недоступны.")
            return {'CANCELLED'}
        ensure_default_presets(prefs)

        try:
            idx = int(props.active_preset)
        except (ValueError, TypeError):
            idx = 0
        if idx >= len(prefs.presets):
            self.report({'ERROR'}, "Пресет не найден.")
            return {'CANCELLED'}
        preset = prefs.presets[idx]

        renamed = 0
        for obj in context.selected_objects:
            new_name = apply_preset_to_name(obj, preset)
            if new_name != obj.name:
                obj.name = new_name
                renamed += 1
        self.report({'INFO'}, f"Применён '{preset.name}': {renamed} объектов переименовано.")
        return {'FINISHED'}


class PresetAddOperator(Operator):
    """Добавить новый пресет (копия Default)."""
    bl_idname = "bridge.preset_add"
    bl_label  = "Add Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = get_addon_preferences(context)
        if not prefs:
            return {'CANCELLED'}
        ensure_default_presets(prefs)
        # Копируем Default как базу
        _add_default_preset(prefs.presets, "New Preset")
        prefs.active_preset_index = len(prefs.presets) - 1
        return {'FINISHED'}


class PresetDuplicateOperator(Operator):
    """Дублировать активный пресет."""
    bl_idname = "bridge.preset_duplicate"
    bl_label  = "Duplicate Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = get_addon_preferences(context)
        if not prefs or len(prefs.presets) == 0:
            return {'CANCELLED'}
        src = prefs.presets[prefs.active_preset_index]
        new = prefs.presets.add()
        new.name = src.name + " copy"
        new.prefix = src.prefix
        new.suffix_mesh = src.suffix_mesh
        new.suffix_empty = src.suffix_empty
        new.suffix_armature = src.suffix_armature
        new.lowercase = src.lowercase
        new.dots_to_underscore = src.dots_to_underscore
        prefs.active_preset_index = len(prefs.presets) - 1
        return {'FINISHED'}


class PresetDeleteOperator(Operator):
    """Удалить активный пресет."""
    bl_idname = "bridge.preset_delete"
    bl_label  = "Delete Preset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        prefs = get_addon_preferences(context)
        return prefs is not None and len(prefs.presets) > 1

    def execute(self, context):
        prefs = get_addon_preferences(context)
        if not prefs or len(prefs.presets) <= 1:
            return {'CANCELLED'}
        prefs.presets.remove(prefs.active_preset_index)
        if prefs.active_preset_index >= len(prefs.presets):
            prefs.active_preset_index = len(prefs.presets) - 1
        return {'FINISHED'}


class OpenPresetEditorOperator(Operator):
    """Открыть редактор пресетов в Preferences аддона."""
    bl_idname = "bridge.open_preset_editor"
    bl_label  = "Edit Presets…"

    def execute(self, context):
        # Открываем Preferences с раскрытым аддоном
        bpy.ops.preferences.addon_expand(module=__name__)
        return {'FINISHED'}


# --- Collection <-> Empty, MayaRotate --------------------------------------

class CollectionToEmptyOperator(Operator):
    bl_idname = "object.collection_to_empty"
    bl_label = "Collection → Empty"
    bl_description = ("Для каждого выделенного меша, находящегося в коллекции (не в главной), "
                      "коллекция преобразуется в пустышку. Рекурсивно.")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene_coll = context.scene.collection
        to_process = set()
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                for coll in obj.users_collection:
                    if coll != scene_coll:
                        to_process.add(coll)
        if not to_process:
            self.report({'WARNING'}, "Нет коллекций для конвертации.")
            return {'CANCELLED'}
        top = []
        for coll in to_process:
            is_top = True
            for other in to_process:
                if other != coll and coll.name in [sub.name for sub in other.children]:
                    is_top = False
                    break
            if is_top:
                top.append(coll)
        for coll in top:
            self._convert(coll, None, scene_coll)
        for obj in context.scene.objects:
            obj.name = obj.name.replace('.', '_')
        self.report({'INFO'}, "Конвертация коллекций завершена.")
        return {'FINISHED'}

    def _convert(self, coll, parent_empty, scene_coll):
        new_empty = bpy.data.objects.new(coll.name.replace('.', '_'), None)
        if parent_empty:
            new_empty.parent = parent_empty
        scene_coll.objects.link(new_empty)
        for obj in list(coll.objects):
            obj.parent = new_empty
            try:
                coll.objects.unlink(obj)
            except Exception:
                pass
            if obj.name not in scene_coll.objects:
                scene_coll.objects.link(obj)
        for subcoll in list(coll.children):
            self._convert(subcoll, new_empty, scene_coll)
        bpy.data.collections.remove(coll)


class EmptyToCollectionOperator(Operator):
    bl_idname = "object.empty_to_collection"
    bl_label = "Empty → Collection"
    bl_description = ("Верхняя пустышка выделенного меша преобразуется в коллекцию. Рекурсивно.")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene_coll = context.scene.collection
        to_process = set()
        for obj in context.selected_objects:
            if obj.type == 'MESH' and obj.parent and obj.parent.type == 'EMPTY':
                to_process.add(self._root(obj))
        if not to_process:
            self.report({'WARNING'}, "Нет пустышек для конвертации.")
            return {'CANCELLED'}
        for empty_obj in to_process:
            self._convert(empty_obj, None, scene_coll)
        for obj in context.scene.objects:
            obj.name = obj.name.replace('.', '_')
        self.report({'INFO'}, "Конвертация пустышек завершена.")
        return {'FINISHED'}

    def _root(self, obj):
        current = obj
        while current.parent and current.parent.type == 'EMPTY':
            current = current.parent
        return current

    def _convert(self, empty_obj, parent_coll, scene_coll):
        new_coll = bpy.data.collections.new(empty_obj.name.replace('.', '_'))
        if parent_coll:
            parent_coll.children.link(new_coll)
        else:
            scene_coll.children.link(new_coll)
        for child in list(empty_obj.children):
            if child.type == 'MESH':
                for coll in list(child.users_collection):
                    try:
                        coll.objects.unlink(child)
                    except Exception:
                        pass
                new_coll.objects.link(child)
            elif child.type == 'EMPTY':
                self._convert(child, new_coll, scene_coll)
        bpy.data.objects.remove(empty_obj, do_unlink=True)


class MayaRotateOperator(Operator):
    """Применить вращение к пустышкам (нативный transform_apply вместо Pies Plus)."""
    bl_idname = "object.maya_rotate"
    bl_label = "MayaRotate"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        processed = set()

        def proc(empty_obj):
            if empty_obj.name in processed:
                return
            processed.add(empty_obj.name)
            bpy.ops.object.select_all(action='DESELECT')
            empty_obj.select_set(True)
            context.view_layer.objects.active = empty_obj
            try:
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
            except Exception:
                pass
            for child in empty_obj.children:
                if child.type == 'EMPTY':
                    proc(child)

        for obj in context.selected_objects:
            if obj.type == 'MESH':
                current = obj.parent
                while current and current.type == 'EMPTY':
                    proc(current)
                    current = current.parent
            elif obj.type == 'EMPTY':
                proc(obj)
        self.report({'INFO'}, "Применено вращение к пустышкам.")
        return {'FINISHED'}


# ════════════════════════════════════════════════════════════════════════════
# UNIVERSAL UV RENAMER
# ════════════════════════════════════════════════════════════════════════════
#
# Конвенции имён UV layers. Симметрично с bridge_qt.py (UV_CONVENTIONS).
# Primary — целевое имя для главного UV.
# Для Unreal: primary остаётся, secondary → LightmassUV (lightmap).

UV_CONVENTIONS = {
    "MAYA":    {"primary": "map1",        "secondary": None,    "label": "Maya (map1)"},
    "BLENDER": {"primary": "UVMap",       "secondary": None,    "label": "Blender (UVMap)"},
    "HOUDINI": {"primary": "uv",          "secondary": None,    "label": "Houdini (uv)"},
    "UNREAL":  {"primary": None,          "secondary": "LightmassUV", "label": "Unreal (Lightmass)"},
    "CUSTOM":  {"primary": None,          "secondary": None,    "label": "Custom"},
}


def _uv_target_items(self, context):
    """Динамические items для EnumProperty uv_target."""
    items = []
    for key in UV_CONVENTIONS:
        items.append((key, UV_CONVENTIONS[key]["label"], ""))
    return items


class BridgeUVRenameOperator(Operator):
    """Переименовать primary UV layer выделенных мешей под конвенцию."""
    bl_idname = "object.bridge_uv_rename"
    bl_label = "Apply UV Convention"
    bl_options = {'REGISTER', 'UNDO'}

    target: EnumProperty(
        name="Target",
        description="Целевая конвенция UV имён",
        items=_uv_target_items,
    )
    custom_name: StringProperty(
        name="Custom Name",
        description="Имя для Custom пресета",
        default="",
    )

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        conv = UV_CONVENTIONS.get(self.target, UV_CONVENTIONS["MAYA"])

        # Определить целевые имена
        if self.target == "CUSTOM":
            primary_target = self.custom_name.strip() or "UVMap"
            secondary_target = None
        else:
            primary_target = conv["primary"]
            secondary_target = conv["secondary"]

        meshes_processed = 0
        renamed = 0
        multi_uv = 0
        multi_uv_names = []
        errors = []

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            mesh = obj.data
            uv_layers = mesh.uv_layers
            if not uv_layers or len(uv_layers) == 0:
                continue
            meshes_processed += 1
            n = len(uv_layers)

            try:
                if n == 1:
                    # Один UV — переименовать в primary
                    if primary_target and uv_layers[0].name != primary_target:
                        uv_layers[0].name = primary_target
                        renamed += 1
                else:
                    # N > 1: primary → target, secondary по стратегии
                    if primary_target and uv_layers[0].name != primary_target:
                        uv_layers[0].name = primary_target
                        renamed += 1

                    # Unreal: secondary[0] → LightmassUV
                    if secondary_target and n >= 2:
                        if uv_layers[1].name != secondary_target:
                            uv_layers[1].name = secondary_target
                            renamed += 1

                    # Сигнал: доп. UV не тронуты
                    untouched = n - 1
                    if untouched > 0 and not secondary_target:
                        multi_uv += 1
                        multi_uv_names.append(obj.name)
            except Exception as e:
                errors.append("{}: {}".format(obj.name, e))

        # Report
        msg = "UV: {} mesh(es) processed, {} renamed".format(meshes_processed, renamed)
        if multi_uv > 0:
            short = ", ".join(multi_uv_names[:5])
            if len(multi_uv_names) > 5:
                short += ", +{}".format(len(multi_uv_names) - 5)
            msg += " | WARNING: {} mesh(es) have extra UVs (untouched): {}".format(multi_uv, short)
            self.report({'WARNING'}, msg)
        else:
            self.report({'INFO'}, msg)

        for err in errors[:3]:
            self.report({'WARNING'}, "UV rename error: {}".format(err))

        return {'FINISHED'}


# ════════════════════════════════════════════════════════════════════════════
# RIG TRANSFER OPERATORS
# ════════════════════════════════════════════════════════════════════════════

class RigExportOperator(Operator):
    """Экспорт рига в FBX + recipe.json для Maya."""
    bl_idname = "bridge.rig_export"
    bl_label = "Export Rig"
    bl_options = {'REGISTER'}

    bake_animation: BoolProperty(name="Bake Animation", default=False)
    selection_only: BoolProperty(name="Selection Only", default=False)

    @classmethod
    def poll(cls, context):
        return _RIG_AVAILABLE and any(o.type == 'ARMATURE' for o in context.selected_objects)

    def execute(self, context):
        arm_obj = next((o for o in context.selected_objects if o.type == 'ARMATURE'), None)
        if not arm_obj:
            arm_obj = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
        if not arm_obj:
            self.report({'ERROR'}, "No armature in scene")
            return {'CANCELLED'}

        asset = get_scene_asset_name()
        fbx_path = os.path.join(TEMP_DIRECTORY, "{}_rig.fbx".format(asset))
        recipe_path = os.path.join(TEMP_DIRECTORY, "{}_rig_recipe.json".format(asset))

        result = _rig_blender.export_rig(
            fbx_path=fbx_path,
            recipe_path=recipe_path,
            bake_animation=self.bake_animation,
            selection_only=self.selection_only,
            asset_name=asset,
            armature_obj=arm_obj,
        )

        if result.get("error"):
            self.report({'ERROR'}, "Rig export: {}".format(result["error"]))
            return {'CANCELLED'}

        self.report({'INFO'},
                    "Rig exported: {} + {}".format(
                        os.path.basename(result["fbx"]),
                        os.path.basename(result["recipe"])))
        return {'FINISHED'}


class RigReconstructOperator(Operator):
    """Восстановить риг из recipe.json после FBX-импорта."""
    bl_idname = "bridge.rig_reconstruct"
    bl_label = "Reconstruct Rig"
    bl_options = {'REGISTER', 'UNDO'}

    recipe_path: StringProperty(
        name="Recipe Path",
        description="Путь к *_rig_recipe.json",
        default="",
    )

    @classmethod
    def poll(cls, context):
        return _RIG_AVAILABLE

    def invoke(self, context, event):
        # Открыть FileBrowser для выбора recipe
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not self.recipe_path or not os.path.exists(self.recipe_path):
            self.report({'ERROR'}, "Recipe file not found: {}".format(self.recipe_path))
            return {'CANCELLED'}

        stats = _rig_blender.import_rig_with_recipe(self.recipe_path)
        if "error" in stats:
            self.report({'ERROR'}, "Reconstruct: {}".format(stats["error"]))
            return {'CANCELLED'}

        extra = ""
        if stats.get("missing_names"):
            extra = ", {} missing".format(len(stats["missing_names"]))
        self.report({'INFO'},
                    "Rig reconstructed: {} controls, {} constraints, {} parents{}".format(
                        stats["controls_applied"], stats["constraints_created"],
                        stats["parents_applied"], extra))
        return {'FINISHED'}


# ════════════════════════════════════════════════════════════════════════════
# ADDON PREFERENCES (хранилище пресетов)
# ════════════════════════════════════════════════════════════════════════════

class BridgePreferences(AddonPreferences):
    bl_idname = __name__

    presets: CollectionProperty(type=NamingPreset)
    active_preset_index: IntProperty(default=0)

    def draw(self, context):
        layout = self.layout
        ensure_default_presets(self)

        # Заголовок секции (STUKACH-стиль)
        hdr = layout.row()
        hdr.label(text="Naming Presets", icon='SYNTAX_ON')

        # UIList + кнопки управления
        row = layout.row()
        row.template_list(
            "BRIDGE_UL_Presets", "",
            self, "presets",
            self, "active_preset_index",
            rows=6,
        )

        col = row.column(align=True)
        col.operator("bridge.preset_add", text="", icon='ADD')
        col.operator("bridge.preset_duplicate", text="", icon='COPY_ID')
        col.operator("bridge.preset_delete", text="", icon='REMOVE')

        # Свойства активного пресета
        if 0 <= self.active_preset_index < len(self.presets):
            p = self.presets[self.active_preset_index]
            box = layout.box()
            box.label(text="Edit Preset", icon='GREASEPENCIL')

            box.prop(p, "name")

            box.prop(p, "prefix")
            row = box.row(align=True)
            row.prop(p, "suffix_mesh")
            row.prop(p, "suffix_empty")
            row.prop(p, "suffix_armature")

            row = box.row(align=True)
            row.prop(p, "lowercase")
            row.prop(p, "dots_to_underscore")


class BRIDGE_UL_Presets(UIList):
    """Список пресетов нейминга."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.name, icon='SYNTAX_OFF')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.name, icon='SYNTAX_OFF')


# ════════════════════════════════════════════════════════════════════════════
# Window-manager props (состояние UI)
# ════════════════════════════════════════════════════════════════════════════

class BridgeProperties(PropertyGroup):
    sec_recent_open:    BoolProperty(name="Recent",    default=True)
    sec_naming_open:    BoolProperty(name="Naming",    default=True)
    sec_uv_open:        BoolProperty(name="UV",        default=False)
    sec_hierarchy_open: BoolProperty(name="Hierarchy", default=False)
    sec_rig_open:       BoolProperty(name="Rig",       default=False)

    # Rig Transfer state
    rig_bake_animation: BoolProperty(
        name="Bake Animation",
        description="Bake animation before export (запечь кривые на bones)",
        default=False,
    )
    rig_selection_only: BoolProperty(
        name="Selection Only",
        description="Экспортировать только выделение (иначе вся сцена)",
        default=False,
    )

    # UV Convention state
    uv_target: EnumProperty(
        name="UV Convention",
        description="Целевая конвенция имён UV layers",
        items=[
            ("MAYA",    "Maya (map1)",        "Переименовать primary UV в map1"),
            ("BLENDER", "Blender (UVMap)",    "Переименовать primary UV в UVMap"),
            ("HOUDINI", "Houdini (uv)",       "Переименовать primary UV в uv"),
            ("UNREAL",  "Unreal (Lightmass)", "Secondary UV → LightmassUV, primary не трогать"),
            ("CUSTOM",  "Custom",             "Задать своё имя"),
        ],
        default="BLENDER",  # дефолт — Blender (мы на его стороне)
    )
    uv_custom_name: StringProperty(
        name="Custom UV Name",
        description="Имя для Custom пресета",
        default="",
    )

    legacy_scale: BoolProperty(
        name="Legacy scale",
        description=("Escape hatch для чужих ассетов с необычным масштабом. "
                     "ON: режим V6 (global_scale=0.01 при экспорте, 100 при импорте) — "
                     "масштаб НЕ применяется, FBX уходит «как есть». "
                     "OFF (по умолчанию): rot+scale применяются, честные метры в FBX."),
        default=False
    )

    active_preset: EnumProperty(
        name="Preset",
        description="Активный пресет нейминга",
        items=preset_enum_items,
    )

    last_status: StringProperty(
        name="Last Status",
        default="READY",
    )


# ════════════════════════════════════════════════════════════════════════════
# UI HELPERS (STUKACH-style)
# ════════════════════════════════════════════════════════════════════════════

_STATUS_ICONS = {
    "READY":    ("CHECKMARK",     "READY"),
    "EXPORTED": ("CHECKMARK",     "FBX EXPORTED"),
    "IMPORTED": ("CHECKMARK",     "FBX IMPORTED"),
    "WARNING":  ("INFO",          "WARNING"),
    "ERROR":    ("ERROR",         "ERROR"),
    "NONE":     ("RADIOBUT_OFF",  "IDLE"),
}


def draw_section(layout, props, open_prop, title, icon, draw_fn):
    """Collapsible-секция в стиле STUKACH (TRIA + emboss=False)."""
    is_open = getattr(props, open_prop, False)
    tria = "TRIA_DOWN" if is_open else "TRIA_RIGHT"

    hdr = layout.row(align=True)
    hdr.prop(props, open_prop, text="", icon=tria, emboss=False)
    hdr.label(text=title, icon=icon)

    if is_open:
        inner = layout.column(align=True)
        draw_fn(inner)


def draw_status_badge(layout, status_key):
    """Compact status badge (аналог STUKACH _draw_score_block)."""
    icon, label = _STATUS_ICONS.get(status_key, _STATUS_ICONS["NONE"])
    box = layout.box()
    row = box.row(align=True)
    row.alert = status_key in ("ERROR", "WARNING")
    row.label(text=label, icon=icon)
    asset_row = row.row(align=True)
    asset_row.alignment = 'RIGHT'
    asset_row.label(text=get_scene_asset_name(), icon="FILE_3D")


# ════════════════════════════════════════════════════════════════════════════
# PANEL
# ════════════════════════════════════════════════════════════════════════════

class BridgePanel(Panel):
    bl_label = "PROKLADKA"
    bl_idname = "PROKLADKA_PT_bridge_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PROKLADKA'

    def draw(self, context):
        layout = self.layout
        props = context.window_manager.bridge_props

        # ── Header: PROKLADKA + статус (как Maya) ──────────────────────
        header = layout.row(align=True)
        header.scale_y = 0.8
        header.label(text="PROKLADKA", icon='MODIFIER')
        header.alignment = 'RIGHT'
        status_icon = {"READY": 'CHECKMARK', "EXPORTED": 'CHECKMARK',
                       "IMPORTED": 'CHECKMARK', "ERROR": 'ERROR',
                       "NONE": 'RADIOBUT_OFF'}.get(props.last_status, 'RADIOBUT_OFF')
        header.label(text=props.last_status, icon=status_icon)

        # ── Recent FBX (collapsible, как Maya) ──────────────────────────
        def _recent_content(inner):
            recents = _read_recent_fbx()
            if not recents:
                hint = inner.row()
                hint.scale_y = 0.7
                hint.enabled = False
                hint.label(text="  (no recent exports)")
                return
            for i, path in enumerate(recents[:5]):
                try:
                    st = os.stat(path)
                    info = "  {} | {} KB | {}".format(
                        os.path.basename(path), max(1, st.st_size // 1024),
                        time.strftime("%d.%m %H:%M", time.localtime(st.st_mtime)))
                except Exception:
                    info = "  " + os.path.basename(path)
                row = inner.row(align=True)
                row.scale_y = 0.75
                row.enabled = False
                row.label(text=info,
                          icon='FILE_CACHE' if i == 0 else 'FILE')
            inner.operator("bridge.clear_recent", text="Clear History", icon='TRASH')

        draw_section(layout, props, "sec_recent_open", "Recent FBX",
                     "RECOVER_LAST", _recent_content)

        # ── IO Buttons (как Maya — не collapsible) ─────────────────────
        # Export / Import большие кнопки
        export_row = layout.row(align=True)
        export_row.scale_y = 1.4
        export_row.operator("export_scene.bridge_fbx", text="Export", icon='EXPORT')

        import_row = layout.row(align=True)
        import_row.scale_y = 1.4
        import_row.operator("import_scene.bridge_fbx", text="Import", icon='IMPORT')

        # Hint: имя файла
        hint = layout.row()
        hint.scale_y = 0.7
        hint.enabled = False
        _recent = _read_recent_fbx()
        _target = os.path.basename(_recent[0]) if _recent else f"{get_scene_asset_name()}_bridge.fbx"
        hint.label(text=f"  → {_target}")

        # Legacy scale
        layout.prop(props, "legacy_scale", icon='MOD_OUTLINE')

        # ── Naming (как Maya: dropdown + явная кнопка) ─────────────────
        naming_label = layout.row()
        naming_label.scale_y = 0.75
        naming_label.label(text="Naming preset:", icon='SYNTAX_OFF')

        naming_row = layout.row(align=True)
        naming_row.prop(props, "active_preset", text="")

        # Явная кнопка Apply Naming — полная ширина, видна сразу
        apply_row = layout.row(align=True)
        apply_row.scale_y = 1.1
        apply_row.operator("object.apply_naming_preset",
                           text="Apply Naming", icon='SYNTAX_ON')

        # Naming hint
        prefs = get_addon_preferences(context)
        if prefs and len(prefs.presets) > 0:
            ensure_default_presets(prefs)
            try:
                idx = int(props.active_preset)
                p = prefs.presets[idx]
                h = layout.row()
                h.scale_y = 0.65
                h.enabled = False
                parts = []
                if p.prefix: parts.append(f"+{p.prefix}")
                if p.suffix_mesh or p.suffix_empty or p.suffix_armature:
                    parts.append("_type")
                if p.lowercase: parts.append("lower")
                desc = " · ".join(parts) if parts else "no transform"
                h.label(text=f"  {desc}")
            except (ValueError, IndexError):
                pass

        # Edit presets button (компактно)
        edit_row = layout.row(align=True)
        edit_row.scale_y = 0.75
        edit_row.operator("bridge.open_preset_editor", text="Edit Presets…",
                          icon='PREFERENCES')

        # --- UV Convention секция (collapsible) ---
        def _uv_content(inner):
            # Dropdown конвенции
            inner.prop(props, "uv_target", text="")

            # Custom name field — только для CUSTOM
            if props.uv_target == 'CUSTOM':
                inner.prop(props, "uv_custom_name", text="", icon='GROUP_UVS')

            # Apply button — передаём активные props в operator через properties
            op_row = inner.row(align=True)
            op = op_row.operator("object.bridge_uv_rename", text="Apply UV Convention",
                                 icon='GROUP_UVS')
            op.target = props.uv_target
            op.custom_name = props.uv_custom_name

            # Hint про multi-UV (статичный текст-подсказка, не live)
            hint = inner.row()
            hint.scale_y = 0.6
            hint.enabled = False
            hint.label(text="  primary → target · secondary untouched")

        draw_section(layout, props, "sec_uv_open", "UV",
                     "GROUP_UVS", _uv_content)

        # --- Hierarchy секция (collapsible) ---
        def _hierarchy_content(inner):
            row = inner.row(align=True)
            row.operator("object.collection_to_empty", text="Coll → Empty",
                         icon='OUTLINER_OB_EMPTY')
            row.operator("object.empty_to_collection", text="Empty → Coll",
                         icon='OUTLINER_COLLECTION')
            inner.operator("object.maya_rotate", text="MayaRotate",
                           icon='EMPTY_AXIS')

        draw_section(layout, props, "sec_hierarchy_open", "Hierarchy",
                     "OUTLINER", _hierarchy_content)

        # --- Rig Transfer секция (collapsible) ---
        def _rig_content(inner):
            if not _RIG_AVAILABLE:
                warn = inner.row()
                warn.alert = True
                warn.label(text="Rig modules not available", icon='ERROR')
                return

            # Export block
            lbl_export = inner.row()
            lbl_export.label(text="Export rig:", icon='ARMATURE_DATA')

            inner.prop(props, "rig_bake_animation")
            inner.prop(props, "rig_selection_only")

            op_export = inner.operator("bridge.rig_export", text="Export Rig (FBX + Recipe)",
                                        icon='EXPORT')
            op_export.bake_animation = props.rig_bake_animation
            op_export.selection_only = props.rig_selection_only

            # Separator
            inner.separator()

            # Reconstruct block
            lbl_rec = inner.row()
            lbl_rec.label(text="Reconstruct rig:", icon='MOD_ARMATURE')

            inner.operator("bridge.rig_reconstruct", text="Load Recipe & Reconstruct",
                           icon='FILE_REFRESH')

            hint = inner.row()
            hint.scale_y = 0.6
            hint.enabled = False
            hint.label(text="  rebuild constraints + control shapes from JSON")

        draw_section(layout, props, "sec_rig_open", "Rig Transfer",
                     "ARMATURE_DATA", _rig_content)


# ════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ════════════════════════════════════════════════════════════════════════════

_classes = (
    NamingPreset,
    BridgeProperties,
    BridgePreferences,
    BRIDGE_UL_Presets,
    ExportBridgeOperator,
    ImportBridgeOperator,
    ClearRecentOperator,
    ApplyNamingPresetOperator,
    PresetAddOperator,
    PresetDuplicateOperator,
    PresetDeleteOperator,
    OpenPresetEditorOperator,
    CollectionToEmptyOperator,
    EmptyToCollectionOperator,
    MayaRotateOperator,
    BridgeUVRenameOperator,
    RigExportOperator,
    RigReconstructOperator,
    BridgePanel,
)


def register():
    for cls in _classes:
        register_class(cls)
    bpy.types.WindowManager.bridge_props = PointerProperty(type=BridgeProperties)
    # Заполнить дефолтные пресеты при первой регистрации
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        if prefs:
            ensure_default_presets(prefs)
    except KeyError:
        pass


def unregister():
    if hasattr(bpy.types.WindowManager, "bridge_props"):
        del bpy.types.WindowManager.bridge_props
    for cls in reversed(_classes):
        unregister_class(cls)


if __name__ == "__main__":
    register()
