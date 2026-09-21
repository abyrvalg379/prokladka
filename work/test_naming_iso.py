# -*- coding: utf-8 -*-
"""Изолированный фоновый тест PROKLADKA: рекурсия нейминга + авто-нейминг при импорте.
Запуск: set BLENDER_USER_RESOURCES=%TEMP%\prk_prefs && blender.exe -b -P test_naming_iso.py
Исходники подключаются напрямую из work-копии (как чистый пакет prokladka),
юзерские префы/расширения и юзерский bridge_last.json не используются.
"""
import bpy, os, sys, json, tempfile
from types import SimpleNamespace

RESULTS = []

def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[TEST] {} {} {}".format("PASS" if cond else "FAIL", name, detail),
          flush=True)

# ── 0. Чистый пакет из out-копии (BLENDER_USER_RESOURCES изолирован) ──────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import prokladka as pkg
except ImportError as e:
    print("[TEST] FATAL: import prokladka: {}".format(e), flush=True)
    os._exit(1)
check("addon_import", True)

# ── 1. Props: регистрируем только PropertyGroup (мост/панели не нужны) ────
bpy.utils.register_class(pkg.BridgeProperties)
bpy.types.WindowManager.bridge_props = bpy.props.PointerProperty(
    type=pkg.BridgeProperties)
wm = bpy.context.window_manager or bpy.data.window_managers[0]
props = wm.bridge_props
check("naming_default_on", props.apply_naming_on_import is True,
      "default = {}".format(props.apply_naming_on_import))

# ── 2. Пресет Default как live-объект (без AddonPreferences) ──────────────
preset = SimpleNamespace(
    prefix="", suffix_mesh="_geo", suffix_empty="_grp",
    suffix_armature="_skel", suffix_joint="_jnt", suffix_control="_ctl",
    lowercase=True, dots_to_underscore=True)

# ── 3. Тестовая иерархия «майский экспорт»: голые имена ───────────────────
scene = bpy.context.scene
# фабричный стартап изолированного конфига не должен попадать в FBX-экспорт
for ob in list(bpy.data.objects):
    if ob.name.startswith(("Cube", "Camera", "Light")):
        bpy.data.objects.remove(ob)

def mk(name, kind, parent=None):
    if kind == "EMPTY":
        ob = bpy.data.objects.new(name, None)
    else:
        me = bpy.data.meshes.new(name + "_data")
        ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    if parent:
        ob.parent = parent
    return ob

root   = mk("Asset",  "EMPTY")
static = mk("static", "EMPTY", root)
b1     = mk("bolt01", "MESH", static)
b2     = mk("bolt02", "MESH", static)
wing   = mk("wing",   "MESH")
bpy.context.view_layer.update()

# ── 4. Рекурсия: выделен только корень; wing НЕ в ветке — не должен
#      переименоваться ──────────────────────────────────────────────────────
bpy.ops.object.select_all(action="DESELECT")
root.select_set(True)
targets = pkg._naming_targets(bpy.context)
check("recursive_targets", len(targets) == 4,
      "targets = {}".format(sorted(o.name for o in targets)))

for ob in targets:
    nn = pkg.apply_preset_to_name(ob, preset)
    if nn != ob.name:
        ob.name = nn
check("names_correct",
      root.name == "asset_grp" and static.name == "static_grp"
      and b1.name == "bolt01_geo" and b2.name == "bolt02_geo"
      and wing.name == "wing",
      "root={} static={} b1={} b2={} wing={}".format(
          root.name, static.name, b1.name, b2.name, wing.name))

# ── 5. Идемпотентность ─────────────────────────────────────────────────────
changed = 0
for ob in pkg._naming_targets(bpy.context):
    nn = pkg.apply_preset_to_name(ob, preset)
    if nn != ob.name:
        changed += 1
check("idempotent", changed == 0, "повтор = {}".format(changed))

# ── 6. Импорт-контур: FBX с голыми именами → авто-нейминг ─────────────────
for ob in (root, static, b1, b2, wing):
    bpy.data.objects.remove(ob)
g_root   = mk("Asset",  "EMPTY")
g_static = mk("static", "EMPTY", g_root)
g_b1     = mk("bolt01", "MESH", g_static)
g_b2     = mk("bolt02", "MESH", g_static)
g_wing   = mk("wing",   "MESH")
bpy.context.view_layer.update()

fbx_path = os.path.join(tempfile.gettempdir(), "prokladka_test_src.fbx")
bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=False,
                         use_mesh_modifiers=False, bake_anim=False,
                         add_leaf_bones=False, axis_forward="-Z",
                         axis_up="Y", global_scale=1.0)
check("export_fbx", os.path.isfile(fbx_path), fbx_path)

for ob in (g_root, g_static, g_b1, g_b2, g_wing):
    bpy.data.objects.remove(ob)
bpy.context.view_layer.update()

before = set(o.name for o in bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=fbx_path)
imported_all = [o for o in bpy.data.objects if o.name not in before]
check("imported_raw", sorted(o.name for o in imported_all) ==
      ["Asset", "bolt01", "bolt02", "static", "wing"],
      "raw = {}".format(sorted(o.name for o in imported_all)))

# Логика авто-нейминга — те же строки, что в ImportBridgeOperator:
named = 0
for ob in imported_all:
    nn = pkg.apply_preset_to_name(ob, preset)
    if nn != ob.name:
        ob.name = nn
        named += 1
final = sorted(o.name for o in imported_all)
check("auto_naming_imported",
      final == ["asset_grp", "bolt01_geo", "bolt02_geo", "static_grp", "wing_geo"],
      "final = {}".format(final))

# ── Итог ───────────────────────────────────────────────────────────────────
fails = [r for r in RESULTS if not r[1]]
print("[TEST] ===== {} passed, {} failed =====".format(
    len(RESULTS) - len(fails), len(fails)), flush=True)
for name, ok, detail in fails:
    print("[TEST] FAILED: {} — {}".format(name, detail), flush=True)
os._exit(1 if fails else 0)
