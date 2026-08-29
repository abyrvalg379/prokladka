# -*- coding: utf-8 -*-
"""
build_maya_installer.py — собирает самоустанавливающийся install_prokladka.py.

Встраивает bridge_qt.py / rig_maya.py / rig_recipe.py в инсталлятор (base64),
чтобы drag&drop в Maya viewport работал из ЛЮБОГО расположения (Maya копирует
drag&drop-файл во временную папку — внешние ссылки там теряются).

Запуск (из корня проекта):
    python work/build_maya_installer.py

Перезапускать после каждого изменения maya-файлов.
"""
import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'out', 'maya')
OUT = os.path.join(SRC, 'install_prokladka.py')

FILES = ('bridge_qt.py', 'rig_maya.py', 'rig_recipe.py')

TEMPLATE = '''# -*- coding: utf-8 -*-
"""
PROKLADKA Maya Installer — self-contained drag & drop installer.

Usage:
  Drag&drop this file into Maya viewport, or run in Script Editor:
    exec(open(r"C:/path/to/install_prokladka.py").read())

Installs to: <maya scripts dir>/prokladka/ + shelf button on Custom shelf.
Built by build_maya_installer.py — do not edit payload by hand.
"""
import os
import sys
import base64
import shutil

import maya.cmds as cmds

_PAYLOAD = {{
{payload}
}}

_SCRIPTS_DIR = cmds.internalVar(userScriptDir=True).rstrip("/").rstrip("\\\\")
_DST = os.path.join(_SCRIPTS_DIR, "prokladka")
_ICONS_DIR = os.path.join(os.path.dirname(_SCRIPTS_DIR), "prefs", "icons")
_ICON_NAME = "prokladka_shelf_logo.png"
_ICON_B64 = _PAYLOAD.get("_icon", "")


def install():
    results = []

    # 1. Scripts
    os.makedirs(_DST, exist_ok=True)
    for name, b64 in _PAYLOAD.items():
        if name.startswith("_"):
            continue
        path = os.path.join(_DST, name)
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        results.append((name, "-> " + path))

    # 2. Icon (optional)
    if _ICON_B64:
        try:
            os.makedirs(_ICONS_DIR, exist_ok=True)
            with open(os.path.join(_ICONS_DIR, _ICON_NAME), "wb") as f:
                f.write(base64.b64decode(_ICON_B64))
            results.append(("icon", "-> " + os.path.join(_ICONS_DIR, _ICON_NAME)))
        except Exception:
            pass

    # 3. Shelf button (Custom shelf, replace old)
    custom = "Custom"
    if not cmds.shelfLayout(custom, exists=True):
        try:
            cmds.shelfLayout(custom, parent="ShelfLayout")
        except Exception:
            pass
    try:
        for btn in (cmds.shelfLayout(custom, query=True, childArray=True) or []):
            if (cmds.shelfButton(btn, exists=True)
                    and cmds.shelfButton(btn, query=True, label=True) == "PROKLADKA"):
                cmds.deleteUI(btn)
    except Exception:
        pass

    scripts_path = _DST.replace("\\\\", "/")
    cmd = (
        "import sys, importlib; "
        "sys.path.insert(0, '{{scripts}}'); "
        "[sys.modules.pop(k, None) for k in list(sys.modules) "
        "if k in ('bridge_qt', 'rig_maya', 'rig_recipe')]; "
        "import bridge_qt; importlib.reload(bridge_qt); bridge_qt.launch()"
    ).format(scripts=scripts_path)
    icon = _ICON_NAME if os.path.exists(os.path.join(_ICONS_DIR, _ICON_NAME)) else "commandButton.png"
    cmds.shelfButton(
        parent=custom, label="PROKLADKA",
        annotation="PROKLADKA - FBX bridge Blender<->Maya + Rig Transfer",
        image=icon, image1=icon, command=cmd, sourceType="python")
    results.append(("shelf button", "Custom shelf (restart Maya to see it)"))

    msg = "PROKLADKA installed!\\n\\n" + "\\n".join(
        "  {{}}: {{}}".format(k, v) for k, v in results)
    cmds.confirmDialog(title="PROKLADKA Installer", message=msg, button=["OK"])
    print("[PROKLADKA] " + msg.replace("\\n", " | "))


install()
'''


def main():
    payload_parts = []
    for f in FILES:
        raw = open(os.path.join(SRC, f), 'rb').read()
        b64 = base64.b64encode(raw).decode('ascii')
        lines = '\n'.join('    "%s"' % b64[i:i + 96] for i in range(0, len(b64), 96))
        payload_parts.append('    "%s": (\n%s\n    ),' % (f, lines))
    icon_path = os.path.join(ROOT, 'work', 'logo', 'prokladka_shelf_logo.png')
    if os.path.isfile(icon_path):
        b64 = base64.b64encode(open(icon_path, 'rb').read()).decode('ascii')
        lines = '\n'.join('    "%s"' % b64[i:i + 96] for i in range(0, len(b64), 96))
        payload_parts.append('    "_icon": (\n%s\n    ),' % lines)

    body = TEMPLATE.format(payload='\n'.join(payload_parts))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(body)
    size = os.path.getsize(OUT)
    print("OK: {} ({:.0f} KB)".format(OUT, size / 1024))


if __name__ == '__main__':
    main()
