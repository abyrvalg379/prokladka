# -*- coding: utf-8 -*-
"""
build_hda_exporter.py — сборка PROKLADKA Export HDA (запускать через hython).

    ".../hython.exe" work/build_hda_exporter.py

Создаёт out/houdini/hda/prokladka_export.hda:
  - SOP-нода prokladka::export (появляется в TAB-меню + авто-кнопка на полке
    через секцию Tools.shelf)
  - Параметры: SOP to export (drag node в поле), Output FBX, Animation Range
  - Кнопка EXPORT BRIDGE FBX -> C:\\temp\\<scene>_bridge.fbx + bridge_last.json
  - PythonModule self-contained (не зависит от пакета prokladka)

Копия в package .../otls/ — авто-установка через HOUDINI_PATH (bat/hython installer).
Ручная установка: перетащить .hda в окно Houdini (нативный drag&drop).
"""
import os
import shutil

import hou

ROOT = r"D:\AI\ZCode\Project\prokladka"
HDA_DIR = os.path.join(ROOT, "out", "houdini", "hda")
HDA_FILE = os.path.join(HDA_DIR, "prokladka_export.hda")
PKG_OTLS = os.path.join(ROOT, "out", "houdini", "package", "prokladka", "houdini", "otls")

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect x="3" y="10" width="14" height="14" rx="2" fill="#2b2b2b"/>
<rect x="3" y="10" width="14" height="4" fill="#4772b3"/>
<polygon points="18,17 24,17 24,13 31,19 24,25 24,21 18,21" fill="#4d8b46"/>
</svg>
"""

PYTHON_MODULE = '''
import os
import json
import hou

RECENT = "C:/temp/bridge_last.json"


def export(kwargs):
    node = kwargs["node"]
    sop_path = node.evalParm("soppath")
    if not sop_path:
        hou.ui.setStatusMessage("PROKLADKA: SOP to export is not set")
        return
    out_path = node.evalParm("path").replace("\\\\", "/")
    if not out_path:
        hou.ui.setStatusMessage("PROKLADKA: output path is empty")
        return
    d = os.path.dirname(out_path)
    if d and not os.path.isdir(d):
        os.makedirs(d)

    out = hou.node("/out")
    sub = hou.node("/out/prokladka")
    if sub is None:
        sub = out.createNode("subnet", "prokladka")
    rop = sub.node("hda_fbx_export")
    if rop is None:
        rop = sub.createNode("filmboxfbx", "hda_fbx_export")
    def _setfirst(rop, names, value):
        for n in names:
            pp = rop.parm(n)
            if pp:
                pp.set(value)
                return
    # 20.5: startnode/sopoutput; старые версии: soppath/file
    _setfirst(rop, ("startnode", "soppath"), sop_path)
    _setfirst(rop, ("sopoutput", "file", "filename"), out_path)
    ak = rop.parm("exportkind")  # binary: Blender ASCII FBX не читает
    if ak:
        ak.set(0)
    cu = rop.parm("convertunits")  # FBX-cm: Blender получит метры
    if cu:
        cu.set(1)

    if node.evalParm("userange"):
        s = int(node.evalParm("fstart"))
        e = int(node.evalParm("fend"))
        if s == e:
            rop.parm("trange").set(0)
        else:
            rop.parm("trange").set(1)
            rop.parm("f1").set(s)
            rop.parm("f2").set(e)
            rop.parm("f3").set(1)
    else:
        rop.parm("trange").set(0)

    rop.render()
    _update_recent(out_path)
    try:
        hou.ui.setStatusMessage(
            "PROKLADKA: FBX exported -> {}".format(out_path))
    except Exception:
        print("[PROKLADKA] FBX exported -> " + out_path)


def _update_recent(path):
    try:
        data = []
        if os.path.exists(RECENT):
            with open(RECENT, "r") as f:
                data = json.load(f)
        if isinstance(data, list):
            if path in data:
                data.remove(path)
            data.insert(0, path)
            data = data[:5]
            with open(RECENT, "w") as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass
'''

TOOLS_SHELF = """<?xml version="1.0" encoding="UTF-8"?>
<shelfDocument>
  <tool name="$HDA_DEFAULT_TOOL" label="$HDA_LABEL" icon="$HDA_ICON">
    <toolMenuContext name="viewer">
      <contextNetType>SOP</contextNetType>
    </toolMenuContext>
    <toolMenuContext name="network">
      <contextOpType>$HDA_TABLE_AND_NAME</contextOpType>
    </toolMenuContext>
    <toolSubmenu>PROKLADKA</toolSubmenu>
    <script scriptType="python"><![CDATA[import soptoolutils

soptoolutils.genericTool(kwargs, '$HDA_NAME')]]></script>
  </tool>
</shelfDocument>
"""

ON_CREATED = """kwargs["node"].setColor(hou.Color((0.28, 0.47, 0.7)))"""


def build():
    os.makedirs(HDA_DIR, exist_ok=True)
    if os.path.isfile(HDA_FILE):
        os.remove(HDA_FILE)

    geo = hou.node("/obj").createNode("geo", "prk_hda_build")
    subnet = geo.createNode("subnet")

    group = hou.ParmTemplateGroup()
    sop_t = hou.StringParmTemplate(
        "soppath", "SOP to Export", 1,
        string_type=hou.stringParmType.NodeReference)
    sop_t.setTags({"opfilter": '"!!OBJECT"', "oprelative": "."})
    group.addParmTemplate(sop_t)
    path_t = hou.StringParmTemplate(
        "path", "Output FBX", 1,
        default_value=("C:/temp/$HIPNAME_fbx.fbx",),
        string_type=hou.stringParmType.FileReference)
    group.addParmTemplate(path_t)
    group.addParmTemplate(hou.ToggleParmTemplate(
        "userange", "Animation Range", default_value=False))
    fs = hou.IntParmTemplate("fstart", "Start", 1, default_value=(1,))
    fs.disable_when = "userange == 0"
    group.addParmTemplate(fs)
    fe = hou.IntParmTemplate("fend", "End", 1, default_value=(240,))
    fe.disable_when = "userange == 0"
    group.addParmTemplate(fe)
    btn = hou.ButtonParmTemplate(
        "export", "EXPORT BRIDGE FBX",
        script_callback="hou.phm().export(kwargs)",
        script_callback_language=hou.scriptLanguage.Python)
    group.addParmTemplate(btn)

    hda = subnet.createDigitalAsset(
        "prokladka::export",
        hda_file_name=HDA_FILE,
        description="PROKLADKA Bridge Export")

    hda_def = hda.type().definition()
    hda_def.setParmTemplateGroup(group)
    hda_def.setExtraFileOption("OnCreated/IsPython", True)
    hda_def.setExtraFileOption("OnCreated/IsScript", True)
    hda_def.setExtraFileOption("OnCreated/IsExpr", False)
    hda_def.addSection("PythonModule", PYTHON_MODULE)
    hda_def.addSection("Tools.shelf", TOOLS_SHELF)
    hda_def.addSection("IconSVG", ICON_SVG)
    hda_def.save(HDA_FILE)

    geo.destroy()

    os.makedirs(PKG_OTLS, exist_ok=True)
    shutil.copy2(HDA_FILE, os.path.join(PKG_OTLS, "prokladka_export.hda"))

    print("[OK] HDA saved:", HDA_FILE)
    print("[OK] Package copy:", PKG_OTLS)


build()
