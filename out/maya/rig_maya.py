# -*- coding: utf-8 -*-
"""
rig_maya.py — Maya side rig extract/reconstruct для PROKLADKA.

Extract:   собирает Recipe из текущей сцены Maya (constraints, control shapes, parents).
Reconstruct: восстанавливает риг из Recipe на принимающей стороне.

Симметрично с rig_blender.py. Общий формат — rig_recipe.Recipe.
"""

from __future__ import annotations

import os
import datetime
from typing import Optional

import maya.cmds as cmds
import maya.mel as mel

# Импорт общего формата (rig_recipe.py рядом)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
import sys
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from rig_recipe import (Recipe, Control, ControlShape, Constraint, Parent,
                        SUPPORTED_CONSTRAINT_TYPES)


# ════════════════════════════════════════════════════════════════════════════
# CONSTRAINT MAYA-TYPE → RECIPE TYPE MAPPING
# ════════════════════════════════════════════════════════════════════════════

_MAYA_CONSTRAINT_TYPES = {
    "parentConstraint": "parent",
    "pointConstraint":  "point",
    "orientConstraint": "orient",
    "scaleConstraint":  "scale",
    "aimConstraint":    "aim",   # уточняется позже: aim_no_up если worldUpType=none
}


def _constraint_driven(constraint_node: str) -> Optional[str]:
    """Driven transform = parent constraint_node."""
    try:
        parent = cmds.listRelatives(constraint_node, parent=True) or []
        return parent[0] if parent else None
    except Exception:
        return None


def _query_constraint(node: str, maya_type: str) -> Optional[Constraint]:
    """Прочитать Maya constraint → канонический Constraint."""
    driven = _constraint_driven(node)
    if not driven:
        return None

    try:
        targets = cmds.ls(cmds.listConnections(node + ".target", source=True, destination=False) or [],
                          type="transform") or []
        # targetList если доступен
        try:
            targets = cmds.cmds if False else cmds.listConnections(node + ".target", s=True, d=False) or []
        except Exception:
            pass
    except Exception:
        targets = []

    # Более надёжный путь через query-флаги конкретной команды
    try:
        if maya_type == "parentConstraint":
            sources = cmds.parentConstraint(node, q=True, targetList=True) or []
            skip_t = cmds.parentConstraint(node, q=True, skipTranslate=True) or []
            skip_r = cmds.parentConstraint(node, q=True, skipRotate=True) or []
            mo = cmds.parentConstraint(node, q=True, maintainOffset=True)
        elif maya_type == "pointConstraint":
            sources = cmds.pointConstraint(node, q=True, targetList=True) or []
            skip_t = cmds.pointConstraint(node, q=True, skipTranslate=True) or []
            skip_r, mo = [], cmds.pointConstraint(node, q=True, maintainOffset=True)
        elif maya_type == "orientConstraint":
            sources = cmds.orientConstraint(node, q=True, targetList=True) or []
            skip_r = cmds.orientConstraint(node, q=True, skipRotate=True) or []
            skip_t, mo = [], cmds.orientConstraint(node, q=True, maintainOffset=True)
        elif maya_type == "scaleConstraint":
            sources = cmds.scaleConstraint(node, q=True, targetList=True) or []
            # scaleConstraint имеет skip (один multiuse для всех осей)
            skip_s = cmds.scaleConstraint(node, q=True, skip=True) or []
            skip_t, skip_r, mo = [], [], cmds.scaleConstraint(node, q=True, maintainOffset=True)
        elif maya_type == "aimConstraint":
            sources = cmds.aimConstraint(node, q=True, targetList=True) or []
            aim = cmds.aimConstraint(node, q=True, aimVector=True) or [1, 0, 0]
            up = cmds.aimConstraint(node, q=True, upVector=True) or [0, 1, 0]
            wut = cmds.aimConstraint(node, q=True, worldUpType=True) or "vector"
            wuv = cmds.aimConstraint(node, q=True, worldUpVector=True) or [0, 1, 0]
            wuo = None
            try:
                wuo = cmds.aimConstraint(node, q=True, worldUpObject=True)
            except Exception:
                pass
            skip_t, skip_r, skip_s, mo = [], [], [], cmds.aimConstraint(node, q=True, maintainOffset=True)
        else:
            return None
    except Exception as e:
        cmds.warning("Failed to query constraint {}: {}".format(node, e))
        return None

    if not sources:
        return None

    # Берём первый source (recipe — single-source модель; multi-source можно расширить через extras)
    source = sources[0]

    # Normalize skip-axes в list of "x"/"y"/"z"
    def _normalize_skip(val):
        if not val or val == "none":
            return []
        # val может быть строкой "xyz" или list ["x","y"]
        if isinstance(val, str):
            return [c for c in val.lower() if c in "xyz"]
        return [str(v).lower() for v in val if str(v).lower() in ("x", "y", "z")]

    skip_t_list = _normalize_skip(skip_t)
    skip_r_list = _normalize_skip(skip_r)

    # Determine recipe type
    recipe_type = _MAYA_CONSTRAINT_TYPES[maya_type]
    extras = {}
    if maya_type == "aimConstraint":
        if wut in ("none", "scene", "vector"):
            recipe_type = "aim_no_up"
        else:
            recipe_type = "aim"
        extras = {
            "aim_vector": list(aim),
            "up_vector": list(up),
            "world_up_type": wut,
            "world_up_vector": list(wuv),
        }
        if wuo:
            extras["world_up_object"] = wuo

    # Build skip_scale
    skip_s_list = _normalize_skip(skip_s) if maya_type == "scaleConstraint" else []

    return Constraint(
        type=recipe_type,
        source=source,
        target=driven,
        maintain_offset=bool(mo),
        skip_translate=skip_t_list,
        skip_rotate=skip_r_list,
        skip_scale=skip_s_list,
        extras=extras,
    )


# ════════════════════════════════════════════════════════════════════════════
# CONTROL SHAPE EXTRACTION / RECONSTRUCTION
# ════════════════════════════════════════════════════════════════════════════

def _extract_control_shape(transform: str) -> Optional[ControlShape]:
    """Прочитать NURBS curve shape из transform (controller)."""
    try:
        shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
        curve_shapes = [s for s in shapes if cmds.nodeType(s) == "nurbsCurve"]
        if not curve_shapes:
            return None
        shape = curve_shapes[0]

        degree = cmds.getAttr(shape + ".degree") or 1
        form = cmds.getAttr(shape + ".form") or 0

        # CVs в object space
        cvs = cmds.getAttr(shape + ".cv[*]") or []
        if not cvs:
            # fallback через xform
            cvs_raw = cmds.xform(shape + ".cv[*]", q=True, os=True, translation=True) or []
            cvs = [cvs_raw[i:i + 3] for i in range(0, len(cvs_raw), 3)]
        pts = [[float(p[0]), float(p[1]), float(p[2])] for p in cvs]

        # Color
        color = None
        try:
            if cmds.getAttr(shape + ".overrideEnabled"):
                if cmds.getAttr(shape + ".overrideRGBColors"):
                    rgb = cmds.getAttr(shape + ".overrideColorRGB")
                    if rgb and len(rgb[0]) == 3:
                        color = [float(rgb[0][0]), float(rgb[0][1]), float(rgb[0][2])]
                else:
                    color = int(cmds.getAttr(shape + ".overrideColor"))
        except Exception:
            pass

        return ControlShape(
            type="nurbs_curve",
            degree=int(degree),
            form=int(form),
            points=pts,
            color=color,
        )
    except Exception as e:
        cmds.warning("Failed to extract shape from {}: {}".format(transform, e))
        return None


def _create_curve_from_shape(transform: str, shape: ControlShape) -> bool:
    """Создать NURBS curve в transform по shape-описанию. Возвращает True при успехе."""
    if not shape or not shape.points:
        return False

    try:
        # periodic: повторить первые degree CVs
        pts = [list(p) for p in shape.points]
        periodic = (shape.form == 2)
        if periodic and shape.degree > 0:
            pts = pts + pts[:shape.degree]

        # Создать временную кривую, затем перенести shape под transform
        tmp = cmds.curve(degree=shape.degree, p=pts, per=periodic)
        tmp_shape = cmds.listRelatives(tmp, shapes=True, fullPath=True)
        if not tmp_shape:
            cmds.delete(tmp)
            return False

        # Удалить старые curve shapes на transform, добавить новый
        old_shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
        old_curves = [s for s in old_shapes if cmds.nodeType(s) == "nurbsCurve"]
        new_shape = cmds.rename(tmp_shape[0], transform + "Shape_rec")
        cmds.parent(new_shape, transform, r=True, s=True)

        for s in old_curves:
            try:
                cmds.delete(s)
            except Exception:
                pass

        cmds.delete(tmp)

        # Color
        if shape.color is not None:
            cmds.setAttr(new_shape + ".overrideEnabled", 1)
            if isinstance(shape.color, int):
                cmds.setAttr(new_shape + ".overrideColor", shape.color)
            elif isinstance(shape.color, list) and len(shape.color) == 3:
                cmds.setAttr(new_shape + ".overrideRGBColors", 1)
                cmds.setAttr(new_shape + ".overrideColorRGB",
                             float(shape.color[0]), float(shape.color[1]), float(shape.color[2]))

        return True
    except Exception as e:
        cmds.warning("Failed to create curve on {}: {}".format(transform, e))
        return False


# ════════════════════════════════════════════════════════════════════════════
# EXTRACT RECIPE
# ════════════════════════════════════════════════════════════════════════════

def extract_recipe(selection_only: bool = True,
                   asset_name: str = "",
                   has_animation: bool = False) -> Recipe:
    """
    Собрать Recipe из текущей сцены Maya.

    selection_only: True — только выделение; False — вся сцена.
    """
    recipe = Recipe(
        version="1.0",
        source_app="maya",
        source_scene=cmds.file(query=True, sceneName=True) or "",
        asset_name=asset_name or (cmds.file(query=True, sceneName=True) or "untitled").split("/")[-1].split(".")[0],
        exported_at=datetime.datetime.now().isoformat(timespec="seconds"),
        has_animation=has_animation,
    )

    # Scope: выделенные transforms (или вся сцена)
    if selection_only:
        sel = cmds.ls(selection=True, long=True) or []
        transforms = cmds.ls(sel, long=True, dag=True, type="transform") or []
        # + joints
        transforms += cmds.ls(sel, long=True, dag=True, type="joint") or []
        scope_set = set(cmds.ls(sel, long=True, dag=True, type="transform") or [])
    else:
        transforms = cmds.ls(long=True, type="transform") or []
        scope_set = set(transforms)

    # ── 1. Controls (transforms с nurbsCurve shape) ──────────────────────
    for t in transforms:
        try:
            shapes = cmds.listRelatives(t, shapes=True, fullPath=True) or []
            if any(cmds.nodeType(s) == "nurbsCurve" for s in shapes):
                short = t.split("|")[-1]
                shape_data = _extract_control_shape(t)
                parent_node = cmds.listRelatives(t, parent=True, fullPath=True) or [None]
                parent_name = parent_node[0].split("|")[-1] if parent_node[0] else None
                recipe.controls.append(Control(
                    name=short,
                    shape=shape_data,
                    parent_to=parent_name,
                ))
        except Exception:
            pass

    # ── 2. Constraints (5 типов) ─────────────────────────────────────────
    for maya_type, recipe_type in _MAYA_CONSTRAINT_TYPES.items():
        try:
            constraints = cmds.ls(type=maya_type) or []
        except Exception:
            constraints = []
        for c in constraints:
            try:
                if selection_only:
                    driven = _constraint_driven(c)
                    if not driven or driven not in scope_set:
                        continue
                constraint = _query_constraint(c, maya_type)
                if constraint:
                    # Короткие имена для recipe (FBX не несёт fullPath)
                    constraint.source = constraint.source.split("|")[-1] if "|" in constraint.source else constraint.source
                    constraint.target = constraint.target.split("|")[-1] if "|" in constraint.target else constraint.target
                    recipe.constraints.append(constraint)
            except Exception as e:
                cmds.warning("Constraint {} iteration failed: {}".format(c, e))

    # ── 3. Parents ───────────────────────────────────────────────────────
    for t in transforms:
        try:
            parents = cmds.listRelatives(t, parent=True, fullPath=True) or []
            if parents:
                child_short = t.split("|")[-1]
                parent_short = parents[0].split("|")[-1]
                recipe.parents.append(Parent(child=child_short, parent=parent_short))
        except Exception:
            pass

    return recipe


# ════════════════════════════════════════════════════════════════════════════
# RECONSTRUCT RIG
# ════════════════════════════════════════════════════════════════════════════

def _node_exists(name: str) -> bool:
    """Существует ли объект по короткому имени. Если нет — попробуем fullPath."""
    if not name:
        return False
    if cmds.objExists(name):
        return True
    # поиск по короткому имени (может быть дубль)
    matches = cmds.ls(".*" + name) or []
    return bool(matches)


def _resolve_node(name: str) -> Optional[str]:
    """Найти node по имени. Возвращает полный path или None."""
    if not name:
        return None
    if cmds.objExists(name):
        return name
    matches = cmds.ls("|*" + name, r=True) or []
    matches += cmds.ls("*|" + name) or []
    return matches[0] if matches else None


def _create_constraint(constraint: Constraint) -> bool:
    """Создать Maya constraint по recipe."""
    source = _resolve_node(constraint.source)
    target = _resolve_node(constraint.target)
    if not source or not target:
        cmds.warning("Constraint {}: source/target not found ({} → {})".format(
            constraint.type, constraint.source, constraint.target))
        return False

    try:
        if constraint.type == "parent":
            cmds.parentConstraint(source, target,
                                  mo=constraint.maintain_offset,
                                  skipTranslate=constraint.skip_translate or None,
                                  skipRotate=constraint.skip_rotate or None)
        elif constraint.type == "point":
            cmds.pointConstraint(source, target,
                                 mo=constraint.maintain_offset,
                                 skipTranslate=constraint.skip_translate or None)
        elif constraint.type == "orient":
            cmds.orientConstraint(source, target,
                                  mo=constraint.maintain_offset,
                                  skipRotate=constraint.skip_rotate or None)
        elif constraint.type == "scale":
            cmds.scaleConstraint(source, target,
                                 mo=constraint.maintain_offset,
                                 skip=constraint.skip_scale or None)
        elif constraint.type in ("aim", "aim_no_up"):
            extras = constraint.extras or {}
            aim = extras.get("aim_vector", [1, 0, 0])
            up = extras.get("up_vector", [0, 1, 0])
            wuo = None
            if constraint.type == "aim":
                wut = extras.get("world_up_type", "object")
                wuo_name = extras.get("world_up_object")
                if wuo_name:
                    wuo = _resolve_node(wuo_name)
            else:
                wut = "none"

            kwargs = dict(
                mo=constraint.maintain_offset,
                aimVector=aim,
                upVector=up,
                worldUpType=wut,
            )
            if wuo:
                kwargs["worldUpObject"] = wuo
            if "world_up_vector" in extras:
                kwargs["worldUpVector"] = extras["world_up_vector"]

            cmds.aimConstraint(source, target, **kwargs)
        return True
    except Exception as e:
        cmds.warning("Failed to create {} constraint {} → {}: {}".format(
            constraint.type, constraint.source, constraint.target, e))
        return False


def _apply_control(control: Control) -> bool:
    """Применить control shape и parent_to к существующему transform."""
    transform = _resolve_node(control.name)
    if not transform:
        cmds.warning("Control '{}' not found in scene".format(control.name))
        return False

    # Shape
    if control.shape:
        _create_curve_from_shape(transform, control.shape)

    # Parent_to — НЕ перепарентиваем автоматически (рисково). Только если control
    # НЕ имеет родителя или родитель != parent_to.
    if control.parent_to:
        current_parent = cmds.listRelatives(transform, parent=True, fullPath=True) or [None]
        current_parent_short = current_parent[0].split("|")[-1] if current_parent[0] else None
        if current_parent_short != control.parent_to:
            new_parent = _resolve_node(control.parent_to)
            if new_parent and new_parent != current_parent[0]:
                try:
                    cmds.parent(transform, new_parent)
                except Exception as e:
                    cmds.warning("Failed to parent {} → {}: {}".format(
                        control.name, control.parent_to, e))
    return True


def reconstruct_rig(recipe: Recipe) -> dict:
    """
    Восстановить риг из Recipe в текущей сцене Maya.

    Возвращает dict со статистикой.
    """
    stats = {
        "controls_applied": 0,
        "controls_missing": 0,
        "constraints_created": 0,
        "constraints_failed": 0,
        "missing_names": set(),
    }

    # 1. Apply controls (shapes)
    for c in recipe.controls:
        if _resolve_node(c.name):
            if _apply_control(c):
                stats["controls_applied"] += 1
        else:
            stats["controls_missing"] += 1
            stats["missing_names"].add(c.name)

    # 2. Create constraints
    for c in recipe.constraints:
        if _create_constraint(c):
            stats["constraints_created"] += 1
        else:
            stats["constraints_failed"] += 1
            if not _resolve_node(c.source):
                stats["missing_names"].add(c.source)
            if not _resolve_node(c.target):
                stats["missing_names"].add(c.target)

    stats["missing_names"] = sorted(stats["missing_names"])
    return stats


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINTS (для UI)
# ════════════════════════════════════════════════════════════════════════════

def export_rig(fbx_path: str, recipe_path: str,
               bake_animation: bool = False,
               selection_only: bool = True,
               asset_name: str = "") -> dict:
    """
    Полный экспорт рига из Maya: FBX + recipe.json.
    Возвращает dict с результатом.
    """
    result = {"fbx": None, "recipe": None, "error": None}

    try:
        # 1. Bake animation (опционально)
        if bake_animation:
            try:
                start = int(mel.eval("playbackOptions -q - animationStartTime"))
                end = int(mel.eval("playbackOptions -q - animationEndTime"))
                sel = cmds.ls(selection=True) or []
                if sel:
                    cmds.bakeResults(sel, t=(start, end), sb=1,
                                     pok=True, sac=False, mr=False)
            except Exception as e:
                cmds.warning("Bake animation skipped: {}".format(e))

        # 2. Export FBX (скелет + меши + кривые контролов)
        if not cmds.pluginInfo('fbxmaya', query=True, loaded=True):
            cmds.loadPlugin('fbxmaya')

        folder = os.path.dirname(fbx_path)
        if not os.path.exists(folder):
            os.makedirs(folder)

        try:
            mel.eval("FBXResetExport;")
        except Exception:
            pass

        mel.eval('FBXExport -f "{}" -s;'.format(fbx_path.replace("\\", "/")))
        result["fbx"] = fbx_path

        # 3. Extract recipe
        recipe = extract_recipe(
            selection_only=selection_only,
            asset_name=asset_name,
            has_animation=bake_animation,
        )
        recipe.to_json(recipe_path)
        result["recipe"] = recipe_path

        cmds.inViewMessage(
            amg="<hl>Rig exported:</hl> {} + {}".format(
                os.path.basename(fbx_path), os.path.basename(recipe_path)),
            pos="botLeft", fade=True)

    except Exception as e:
        result["error"] = str(e)
        cmds.warning("Rig export failed: {}".format(e))

    return result


def import_rig_with_recipe(recipe_path: str) -> dict:
    """
    Восстановить риг после FBX-import.
    Предполагается что FBX уже импортирован (скелет + меши в сцене).
    """
    try:
        recipe = Recipe.from_json(recipe_path)
    except Exception as e:
        cmds.warning("Failed to read recipe: {}".format(e))
        return {"error": str(e)}

    errors = recipe.validate()
    if errors:
        cmds.warning("Recipe validation: {}".format("; ".join(errors)))

    stats = reconstruct_rig(recipe)

    cmds.inViewMessage(
        amg="<hl>Rig reconstructed:</hl> {} controls, {} constraints".format(
            stats["controls_applied"], stats["constraints_created"]),
        pos="botLeft", fade=True)

    return stats
