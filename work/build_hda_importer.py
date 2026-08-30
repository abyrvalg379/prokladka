# -*- coding: utf-8 -*-
"""
build_hda_importer.py — сборка PROKLADKA Import HDA (запускать через hython).

    ".../hython.exe" work/build_hda_importer.py

Создаёт out/houdini/hda/prokladka_import.hda:
  - SOP-нода prokladka::import: генерирует геометрию из мост-файла
  - Параметры: Path (FBX), Scale Fix, кнопки USE LAST EXPORT / CHECK SCALE
  - Внутри: file -> xform(scale) -> output
  - PythonModule self-contained
  - Tools.shelf (авто-кнопка на полке) + IconSVG

Копия в package .../otls/ (авто-установка через HOUDINI_PATH).
"""
import os
import shutil

import hou

ROOT = r"D:\AI\ZCode\Project\prokladka"
HDA_DIR = os.path.join(ROOT, "out", "houdini", "hda")
HDA_FILE = os.path.join(HDA_DIR, "prokladka_import.hda")
PKG_OTLS = os.path.join(ROOT, "out", "houdini", "package", "prokladka", "houdini", "otls")

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect x="15" y="10" width="14" height="14" rx="2" fill="#2b2b2b"/>
<rect x="15" y="10" width="14" height="4" fill="#4d8b46"/>
<polygon points="14,17 8,17 8,13 1,19 8,25 8,21 14,21" fill="#4d8b46"/>
</svg>
"""

PYTHON_MODULE = '''
import os
import json
import hou

RECENT = "C:/temp/bridge_last.json"


def use_last(kwargs):
    """Поставить в Path последний экспорт из bridge_last.json."""
    node = kwargs["node"]
    try:
        data = json.load(open(RECENT))
        if isinstance(data, list) and data:
            node.parm("path").set(data[0])
            try:
                hou.ui.setStatusMessage("PROKLADKA: path <- " + data[0])
            except Exception:
                print("[PROKLADKA] path <- " + data[0])
            return
    except Exception:
        pass
    try:
        hou.ui.setStatusMessage("PROKLADKA: bridge_last.json empty or missing")
    except Exception:
        print("[PROKLADKA] bridge_last.json empty or missing")


def check_scale(kwargs):
    """Замерить габариты; если похоже на см (мелко) - применить x100."""
    node = kwargs["node"]
    try:
        geo = node.geometry()
        size = geo.boundingBox().sizevec()
        dims = (abs(size[0]), abs(size[1]), abs(size[2]))
        mx = max(dims)
    except Exception:
        hou.ui.setStatusMessage("PROKLADKA: no cooked geometry")
        return
    if mx <= 0.001:
        hou.ui.setStatusMessage("PROKLADKA: geometry is empty")
        return
    msg = "PROKLADKA: dims %.3f x %.3f x %.3f m" % dims
    if mx <= 1.0:
        msg += " | looks small: if it should be meters, set Scale Fix to 100"
    hou.ui.setStatusMessage(msg)
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

ON_CREATED = """kwargs["node"].setColor(hou.Color((0.30, 0.55, 0.35)))
try:
    kwargs["node"].hdaModule().use_last(kwargs)
except Exception:
    pass"""


def build():
    os.makedirs(HDA_DIR, exist_ok=True)
    if os.path.isfile(HDA_FILE):
        os.remove(HDA_FILE)

    geo = hou.node("/obj").createNode("geo", "prk_hda_imp_build")
    subnet = geo.createNode("subnet")

    hda = subnet.createDigitalAsset(
        "prokladka::import",
        hda_file_name=HDA_FILE,
        description="PROKLADKA Bridge Import")

    hda_def = hda.type().definition()

    # Параметры на definition (после конвертации — иначе теряются)
    group = hou.ParmTemplateGroup()
    path_t = hou.StringParmTemplate(
        "path", "Bridge File", 1,
        default_value=("C:/temp/$HIPNAME_fbx.fbx",),
        string_type=hou.stringParmType.FileReference)
    group.addParmTemplate(path_t)
    scale_t = hou.FloatParmTemplate(
        "scale", "Scale Fix", 1, default_value=(1.0,))
    scale_t.setMinValue(0.0001)
    scale_t.setMaxValue(10000.0)
    group.addParmTemplate(scale_t)
    group.addParmTemplate(hou.ButtonParmTemplate(
        "use_last", "USE LAST EXPORT",
        script_callback="hou.phm().use_last(kwargs)",
        script_callback_language=hou.scriptLanguage.Python))
    group.addParmTemplate(hou.ButtonParmTemplate(
        "check_scale", "CHECK SCALE",
        script_callback="hou.phm().check_scale(kwargs)",
        script_callback_language=hou.scriptLanguage.Python))
    hda_def.setParmTemplateGroup(group)

    # Внутренняя сеть: file -> xform -> output (генератор, без входов)
    hda.allowEditingOfContents(True)
    fn = hda.createNode("file", "prk_file")
    fn.parm("file").setExpression(
        'hou.text.expandString(hou.pwd().parm("../path").eval())',
        hou.exprLanguage.Python)
    xf = hda.createNode("xform", "prk_xform")
    xf.parm("scale").setExpression('chs("../scale")', hou.exprLanguage.Hscript)
    xf.setInput(0, fn)
    outn = hda.createNode("output", "prk_out")
    outn.setInput(0, xf)
    outn.setDisplayFlag(True)
    outn.setRenderFlag(True)

    hda_def.updateFromNode(hda)  # внутренняя сеть -> definition
    # OnCreated должен исполняться КАК PYTHON (иначе Houdini гонит его как HScript)
    hda_def.setExtraFileOption("OnCreated/IsPython", True)
    hda_def.setExtraFileOption("OnCreated/IsScript", True)
    hda_def.setExtraFileOption("OnCreated/IsExpr", False)
    hda_def.addSection("PythonModule", PYTHON_MODULE)
    hda_def.addSection("Tools.shelf", TOOLS_SHELF)
    hda_def.addSection("IconSVG", ICON_SVG)
    hda_def.addSection("OnCreated", ON_CREATED)
    hda_def.save(HDA_FILE)

    geo.destroy()

    os.makedirs(PKG_OTLS, exist_ok=True)
    shutil.copy2(HDA_FILE, os.path.join(PKG_OTLS, "prokladka_import.hda"))

    print("[OK] HDA saved:", HDA_FILE)
    print("[OK] Package copy:", PKG_OTLS)


build()
