# -*- coding: utf-8 -*-
r"""PROKLADKA - User Guide (EN). Generator on the family template (_docstyle.py).
Run:  python _gen_manual_en.py    Output:  docs\PROKLADKA_Manual_EN.docx
"""

import json

import _docstyle as ds

OUT = r'D:\AI\ZCode\Project\prokladka\docs\PROKLADKA_Manual_EN.docx'


def h1(doc, text):
    return ds.h1(doc, text)


def h2(doc, text):
    return ds.h2(doc, text)


def p(doc, text, bullet=False, italic=False, grey=False):
    return ds.p(doc, text, bullet=bullet, italic=italic, grey=grey)


def kv_note(doc, text):
    return ds.kv(doc, text)


def add_table(doc, rows, widths, sev_col=None):
    return ds.add_table(doc, rows, widths, sev_col=sev_col)


def _save(doc, out):
    ds.footer(doc.sections[1], 'PROKLADKA')
    ds.strip_tail(doc)
    doc.save(out)
    h1s = [t for t in ds.H1_REGISTRY if t.lower() not in ('table of contents', 'contents')]
    json.dump(h1s, open(out.replace('.docx', '.h1.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    print('saved:', out)


doc = ds.new_doc('PROKLADKA', 'User Guide', 'V1.10.0  -  WINDOWS')

p(doc, 'PROKLADKA is an FBX bridge between Blender, Maya, Houdini and Unreal Engine. The '
       'same asset arrives in every application at the right size, with the right naming and '
       'the right UVs - no manual environment variables, no scale dances. Bundled: naming '
       'presets, a Universal UV renamer, Rig Transfer, auto scale adaptation and Unreal '
       'Engine import with static and skeletal meshes.')

kv_note(doc, 'github.com/abyrvalg379/prokladka')

h1(doc, 'Contents')
ds.toc_field(doc, 'Table of contents: open the document in Word/LibreOffice and refresh '
                  'the field (F9) to fill in page numbers.')

h1(doc, '1. Philosophy and the receiver rule')
p(doc, 'The asset adapts to the receiving side, not the other way around. The sending side '
       'exports in a neutral format - meters, Y-up, FBX. The receiver converts the asset to '
       'its own conventions on import.')
add_table(doc, [
    ('Receiving side', 'Units', 'Naming', 'Example'),
    ('Blender', 'meters', 'lowercase + _geo', 'wing_main_geo'),
    ('Maya', 'meters', 'lowercase + _geo', 'wing_main_geo'),
    ('Houdini', 'meters', 'suffix _geo / _vdb', 'wing_main_geo'),
    ('Unreal Engine', 'centimeters (x100)', 'PascalCase + SM_', 'SM_WingMain'),
], [4.4, 3.4, 4.6, 4.6])
p(doc, 'The receiver rule: an imported asset is always a container with zero position, zero '
       'rotation and unit scale. The correct dimensions are baked into the vertices. No '
       'compensating scales on the object: what you see in the properties is zeros and ones, '
       'while the size lives in the geometry. The rule applies to export as well: object '
       'transforms are baked on the way out.')

h1(doc, '2. Features')
for b in (
    'FBX export and import through a shared queue of recent files (export is in beta status);',
    'naming presets: Default, Plain, Unreal, Dots, Rig - editable and idempotent;',
    'recursive naming: Apply Naming covers the selection and the whole child branch;',
    'auto-naming on import in Blender (a switch, on by default);',
    'Universal UV renamer: Maya / Blender / Houdini / Unreal / Custom conventions;',
    'Rig Transfer: move a rig via FBX + recipe.json (constraints, control shapes);',
    'Houdini: multi-format FBX / VDB / Alembic / USD, automatic bbox scale check;',
    'Unreal: Static/Skeletal Mesh import, Material Instance from PBR textures, a dockable panel;',
    'Legacy scale: a manual escape hatch for foreign assets with unusual sizes;',
    'Maya: PBR Texture Assigner - automatic slot recognition, UDIM, ACES colorSpace;',
    'hierarchy: Collection and Empty, MayaRotate, Loc -> Grp.',
):
    p(doc, b, bullet=True)

h1(doc, '3. Installation')
p(doc, 'Download the repository (Code - Download ZIP) and unpack it, then follow your '
       'application.')
h2(doc, '3.1 Blender 4.5+')
for b in (
    'Edit - Preferences - Get Extensions - the top-right menu - Install from Disk;',
    'pick out/blender/prokladka.zip and enable PROKLADKA;',
    'the panel lives in the viewport N-panel, PROKLADKA tab.',
):
    p(doc, b, bullet=True)
h2(doc, '3.2 Maya 2022+')
for b in (
    'drag out/maya/install_prokladka.py straight into the Maya viewport;',
    'confirm the installation and restart Maya;',
    'a PROKLADKA button appears on the Custom shelf. The installer is self-contained - '
    'everything it needs is embedded in the file, drag-and-drop works from any location; '
    'changes are picked up every time the panel starts.',
):
    p(doc, b, bullet=True)
h2(doc, '3.3 Houdini 20.5+')
for b in (
    'way 1: double-click out/houdini/install_PROKLADKA.bat - it installs the files and the '
    'package itself;',
    'way 2: copy out/houdini/package/prokladka/houdini/ into '
    'Documents/houdini20.5/prokladka/houdini/ and create packages/prokladka.json following '
    'the sample in the repository README;',
    'no PROKLADKA tab on the shelves? The plus sign in the shelf tab bar - tick PROKLADKA '
    '(once).',
):
    p(doc, b, bullet=True)
h2(doc, '3.4 Unreal Engine 5.6+')
for b in (
    'copy out/unreal/prokladka/ into the project Content/Python/;',
    'copy out/unreal/init_unreal.py into Content/Python/;',
    'enable the Python Editor Script Plugin and restart UE;',
    'a PROKLADKA toolbar button, or Window - PROKLADKA - Open Panel.',
):
    p(doc, b, bullet=True)

h1(doc, '4. Quick start: an asset from Blender to Maya')
for b in (
    'Blender: select the asset, press Export on the PROKLADKA panel - the file lands in the '
    'export queue.',
    'Maya: open the PROKLADKA panel from the Custom shelf, press Import Bridge - the latest '
    'export arrives as a container at zero with the correct scale.',
    'Naming: the auto-naming switch in Blender applies the suffixes on import; in Maya use '
    'the Apply Naming button on the selection with the child branch.',
    'Done: meters for size, convention names, pivots in place - the asset is ready for the '
    'validator.',
):
    p(doc, b, bullet=True)

h1(doc, '5. Blender: the panel')
p(doc, 'The PROKLADKA panel in the viewport N-panel:')
for b in (
    'Import Bridge FBX - imports the latest file from the export queue; the active naming '
    'preset runs over the result (the auto-naming switch);',
    'Recent FBX - the list of recent files with size and time; the panel header shows which '
    'file will be imported;',
    'Clear History - empty the export queue (with confirmation);',
    'Apply Naming - apply the active preset to the selection and the whole child branch, '
    'idempotently: repeated runs never stack double suffixes;',
    'Legacy scale - a manual scale multiplier for foreign assets with unusual sizes '
    '(off by default).',
):
    p(doc, b, bullet=True)

h1(doc, '6. Maya: panel and shelf')
p(doc, 'The PROKLADKA button on the Custom shelf opens the Qt panel:')
for b in (
    'Export - export the selection to FBX with neutral settings (meters, Y-up);',
    'Import Bridge - import the latest file from the queue;',
    'Apply Naming - the naming preset over the selection with recursion into children, plus '
    'cleanup of service sequences in names after an FBX import;',
    'PBR Texture Assigner - automatic PBR texture layout onto material slots, UDIM and ACES '
    'colorSpace;',
    'hierarchy: Collection and Empty, MayaRotate, Loc -> Grp (a switch that turns imported '
    'EMPTYs into locators - enable it only when locators are actually needed);',
    'History - the export journal with size and time; Clear - queue cleanup.',
):
    p(doc, b, bullet=True)

h1(doc, '7. Houdini: shelf and panel')
p(doc, 'The PROKLADKA shelf - seven buttons with icons (panel, format exports, Import '
       'Bridge, naming, journal, cleanup):')
for b in (
    'Export FBX - export from the selection or smart search of the active geometry; the file '
    'is always binary, units are meters, object transforms are baked on the way out;',
    'VDB / Alembic / USD - same-click exports for volumes, caches and scenes;',
    'Import Bridge - import the latest file from the queue; several files - pick from a '
    'list. Imports land in /obj/prokladka_imports: importing the same file again updates '
    'the node instead of stacking a copy; giant files are flagged and rescaled automatically '
    '(auto-scaled /100);',
    'Apply Naming - the naming preset over the selection;',
    'History and Clear - journal and queue cleanup.',
):
    p(doc, b, bullet=True)

h1(doc, '8. Houdini: HDA nodes')
p(doc, 'Besides the shelf, Houdini offers two generator nodes: prokladka::export and '
       'prokladka::import (the TAB menu inside geometry).')
h2(doc, '8.1 prokladka::export')
p(doc, 'A wrapper node over the export: point SOP to Export at a node (drag it into the '
       'field or type the path), set Output FBX - the file path, a frame range if needed - '
       'and EXPORT. The node is reference-driven: no wires are needed - the same idiom as '
       'ROP drivers. /obj-level object transforms are baked on export.')
h2(doc, '8.2 prokladka::import')
p(doc, 'An import generator node: the path is set automatically (USE LAST EXPORT takes the '
       'latest export from the queue). No wires into the node - the output continues down '
       'the network, and a fresh node points at the latest export right away. CHECK SCALE is '
       'the scale diagnostic; giant FBX files are flagged and converted to meters '
       'automatically.')

h1(doc, '9. Unreal Engine')
for b in (
    'Window - PROKLADKA - Import Bridge FBX, or the toolbar button;',
    'Static and Skeletal Mesh import with meters-to-centimeters conversion (x100) - objects '
    'arrive at the right size;',
    'Unreal naming convention: the SM_ prefix for static meshes;',
    'a Material Instance is assembled from PBR textures when present;',
    'a dockable panel: Open Panel on the same menu tab.',
):
    p(doc, b, bullet=True)

h1(doc, '10. Naming and UV')
h2(doc, '10.1 Naming presets')
p(doc, 'Five built-in presets, all editable and idempotent:')
add_table(doc, [
    ('Preset', 'Suffixes and style'),
    ('Default', 'lowercase, _geo / _grp / _skel'),
    ('Plain lowercase', 'lowercase without suffixes'),
    ('Unreal', '_Mesh / _SkelMesh'),
    ('Dots only', 'dots instead of underscores'),
    ('Rig', '_jnt / _ctl'),
], [4.4, 12.6])
p(doc, 'Apply Naming is always recursive: the selection plus the whole child branch. '
       'Idempotency protects against double suffixes on repeated runs. Blender also offers '
       'the auto-naming switch on import (on by default).')
h2(doc, '10.2 Universal UV renamer')
p(doc, 'Renaming UV sets to the receiving side convention: Maya (map1), Blender (UVMap), '
       'Houdini (uv), Unreal (LightmassUV), Custom - your own name.')

h1(doc, '11. Rig Transfer')
p(doc, 'A rig move splits into two carriers: FBX carries the geometry, skeleton and weights; '
       'recipe.json carries the connection logic (constraints, control shapes, parenting). '
       'The recipe format is DCC-agnostic and maps onto the native constraints of both '
       'sides:')
add_table(doc, [
    ('Recipe', 'Maya', 'Blender'),
    ('parent', 'parentConstraint', 'CHILD_OF'),
    ('point', 'pointConstraint', 'COPY_LOCATION'),
    ('orient', 'orientConstraint', 'COPY_ROTATION'),
    ('scale', 'scaleConstraint', 'COPY_SCALE'),
    ('aim', 'aimConstraint (+ up)', 'TRACK_TO'),
    ('aim_no_up', 'aimConstraint (no up)', 'DAMPED_TRACK'),
], [3.6, 6.6, 6.8])
p(doc, 'Custom control shapes travel as curve points - independent of the package.')

h1(doc, '12. The export queue')
p(doc, 'All exports land in a shared queue (a file in C:\\temp, named <scene>_bridge.fbx) - '
       'its head is what Import Bridge brings in on any side. The working rules:')
for b in (
    'exported from one application - run Import Bridge in the other right away;',
    'several files in the queue: Houdini offers a picker, Blender and Maya take the head;',
    'Clear History empties the queue when you do not want to import something foreign;',
    'save the scene before exporting: an unsaved file produces untitled_* names;',
    'Blender shows in its panel which file the import will take - check before pressing.',
):
    p(doc, b, bullet=True)

h1(doc, '13. Workflows')
for t in (
    ('Accepting an asset from Maya in Blender',
     'Maya: the hierarchy is built with locators, Export the selection. Blender: Import '
     'Bridge - the hierarchy arrives 1:1 as empties, auto-naming spreads _grp across the '
     'branch. The asset is ready for validation: zero suffix errors.'),
    ('Blender - Houdini',
     'Export in Blender, then Import Bridge in Houdini - or the prokladka::import node with '
     'USE LAST EXPORT. A binary FBX in meters arrives as a container at zero; a giant file '
     'gets the auto-scaled flag on its own.'),
    ('Handing off to Unreal',
     'Export as usual - on the UE side the import applies x100 and the SM_ prefixes. '
     'Materials assemble into instances from PBR textures.'),
    ('Moving a rig',
     'Export the rig and the recipe: FBX carries the geometry and weights, recipe.json '
     'carries the constraints and control shapes. On the receiving side the connections are '
     'restored as native constraints.'),
):
    h2(doc, t[0])
    p(doc, t[1])

h1(doc, '14. Troubleshooting')
add_table(doc, [
    ('Symptom', 'Cause', 'What to do'),
    ('The import arrives as a giant (x100)', 'an export in centimeters without the unit factor',
     'check the auto-scaled flag on the import; manually - Legacy scale or a 0.01 scale'),
    ('Tiny objects in UE', 'meters versus UE centimeters',
     'make sure the import goes through PROKLADKA: the x100 multiplier is set automatically'),
    ('The wrong file arrived', 'the head of the shared queue is someone else\'s latest export',
     'Clear History; in Houdini pick the file from the list; check the panel hint'),
    ('Names like untitled_*', 'the scene was not saved before the export',
     'save the scene and export again'),
    ('Blender EMPTYs became locators in Maya', 'stock FBX import behavior in Maya',
     'enable the Loc -> Grp switch on the Maya panel before the next import'),
    ('Names without suffixes after import', 'auto-naming is off',
     'enable the auto-naming switch or press Apply Naming - it is recursive and idempotent'),
    ('Houdini: no PROKLADKA shelf on the tabs', 'the shelf is installed but not enabled',
     'the plus sign in the shelf tab bar - tick PROKLADKA'),
    ('Houdini: wires will not connect to the Import node', 'the node is a generator, reference-driven',
     'wires are not needed: set the path or USE LAST EXPORT, the output continues down the network'),
    ('Blender crashes on a light from FBX', 'a known incompatibility of certain Blender builds',
     'update the build or remove the light from the FBX file before import'),
    ('A Houdini export will not open in Blender', 'ASCII FBX format',
     'PROKLADKA always writes binary FBX - make sure the export ran through the shelf or the node'),
], [4.4, 4.6, 8.0])

_save(doc, OUT)
