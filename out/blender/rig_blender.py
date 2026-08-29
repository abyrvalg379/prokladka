# -*- coding: utf-8 -*-
"""
rig_blender.py — Blender side rig extract/reconstruct для PROKLADKA.

Extract:   собирает Recipe из armature Blender (constraints, custom shapes, parents).
Reconstruct: восстанавливает риг из Recipe на принимающей стороне.

Симметрично с rig_maya.py. Общий формат — rig_recipe.Recipe.
"""

from __future__ import annotations

import os
import sys
import datetime
from typing import Optional

import bpy

# Импорт общего формата — relative import для package
from .rig_recipe import Recipe, Control, ControlShape, Constraint, Parent


# ════════════════════════════════════════════════════════════════════════════
# BLENDER CONSTRAINT TYPE → RECIPE TYPE MAPPING
# ════════════════════════════════════════════════════════════════════════════

# Mapping для bone constraints. Обратный mapping — в RECIPE_TO_BLENDER.
BLENDER_TO_RECIPE = {
    "COPY_LOCATION":  "point",
    "COPY_ROTATION":  "orient",
    "COPY_SCALE":     "scale",
    "CHILD_OF":       "parent",
    "TRACK_TO":       "aim",
    "DAMPED_TRACK":   "aim_no_up",
    "LOCKED_TRACK":   "aim_no_up",
}

# Mapping для reconstruction: recipe type → Blender constraint type.
# parent → CHILD_OF (с inverse matrix из extras)
RECIPE_TO_BLENDER = {
    "parent":     "CHILD_OF",
    "point":      "COPY_LOCATION",
    "orient":     "COPY_ROTATION",
    "scale":      "COPY_SCALE",
    "aim":        "TRACK_TO",
    "aim_no_up":  "DAMPED_TRACK",
}


# ════════════════════════════════════════════════════════════════════════════
# CONTROL SHAPE EXTRACTION / RECONSTRUCTION
# ════════════════════════════════════════════════════════════════════════════

def _extract_custom_shape(pose_bone) -> Optional[ControlShape]:
    """Прочитать custom shape из pose_bone. Возвращает ControlShape или None."""
    sh = pose_bone.custom_shape
    if not sh:
        return None

    try:
        points = []
        degree = 1
        form = 0

        if sh.type == 'CURVE' and sh.data and sh.data.splines:
            spline = sh.data.splines[0]
            if spline.type == 'POLY':
                points = [[p.co[0], p.co[1], p.co[2]] for p in spline.points]
                degree = 1
                form = 1 if spline.use_cyclic_u else 0
            elif spline.type == 'BEZIER':
                points = [[b.co[0], b.co[1], b.co[2]] for b in spline.bezier_points]
                degree = 3
                form = 1 if spline.use_cyclic_u else 0
        elif sh.type == 'MESH' and sh.data:
            # Mesh как shape — берём vertices (упрощённо)
            points = [[v.co[0], v.co[1], v.co[2]] for v in sh.data.vertices[:64]]
            degree = 1
            form = 0

        if not points:
            return None

        # Color из custom_shape (если есть color-атрибут — в новых Blender)
        # В большинстве версий color берётся из bone color или коллекции.
        # Храним None — пусть принимающая сторона использует дефолт.
        color = None

        return ControlShape(
            type="nurbs_curve",
            degree=degree,
            form=form,
            points=points,
            color=color,
        )
    except Exception as e:
        print("Shape extract failed for {}: {}".format(pose_bone.name, e))
        return None


def _create_custom_shape(shape: ControlShape):
    """
    Создать Blender Object (curve) из ControlShape. Возвращает Object или None.
    Object будет использоваться как bone.custom_shape.
    """
    if not shape or not shape.points:
        return None

    try:
        cu = bpy.data.curves.new(name="rig_shape", type='CURVE')
        cu.dimensions = '3D'
        sp = cu.splines.new('POLY')
        sp.points.add(len(shape.points) - 1)
        for i, p in enumerate(shape.points):
            sp.points[i].co = (float(p[0]), float(p[1]), float(p[2]), 1.0)
        sp.use_cyclic_u = (shape.form == 1)

        obj = bpy.data.objects.new("rig_shape", cu)
        bpy.context.collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_viewport = True  # shape-объекты не должны мешать в outliner
        return obj
    except Exception as e:
        print("Create custom shape failed: {}".format(e))
        return None


# ════════════════════════════════════════════════════════════════════════════
# CONSTRAINT EXTRACT
# ════════════════════════════════════════════════════════════════════════════

def _extract_constraint(blender_constraint, owner_name: str) -> Optional[Constraint]:
    """
    Прочитать Blender constraint → канонический Constraint.
    owner_name — имя bone/object которому принадлежит constraint (= target в recipe).
    """
    ctype = blender_constraint.type
    recipe_type = BLENDER_TO_RECIPE.get(ctype)
    if not recipe_type:
        return None  # неподдерживаемый тип

    # Source: target object/bone constraint'а
    target_obj = blender_constraint.target
    if not target_obj:
        return None

    # subtarget = bone name если target — armature
    subtarget = ""
    if hasattr(blender_constraint, "subtarget"):
        subtarget = blender_constraint.subtarget or ""

    # Формируем имя source. Если subtarget есть — source это bone.
    if subtarget:
        source = subtarget
    else:
        source = target_obj.name

    extras = {}

    # Aim: track_axis + up
    if recipe_type in ("aim", "aim_no_up"):
        if ctype == "TRACK_TO":
            try:
                extras["track_axis"] = str(blender_constraint.track_axis)
                extras["up_axis"] = str(blender_constraint.up_axis)
                # Если есть up_target — это armature, можно извлечь subtarget
                if blender_constraint.target and hasattr(blender_constraint, "subtarget"):
                    if blender_constraint.subtarget:
                        extras["world_up_object"] = blender_constraint.subtarget
                        recipe_type = "aim"
            except Exception:
                pass
        elif ctype == "DAMPED_TRACK":
            try:
                extras["track_axis"] = str(blender_constraint.track_axis)
            except Exception:
                pass
            recipe_type = "aim_no_up"

    # Parent: CHILD_OF — сохранить inverse_matrix
    if recipe_type == "parent" and ctype == "CHILD_OF":
        try:
            # inverse_matrix — 4x4, для восстановления без set_inverse оператора
            inv = [list(blender_constraint.inverse_matrix[i]) for i in range(4)]
            extras["inverse_matrix"] = inv
            # channel toggles (Loc/Rot/Scale по XYZ)
            for axis_attr in ("use_location_x", "use_location_y", "use_location_z"):
                if hasattr(blender_constraint, axis_attr):
                    extras[axis_attr] = getattr(blender_constraint, axis_attr)
            for axis_attr in ("use_rotation_x", "use_rotation_y", "use_rotation_z"):
                if hasattr(blender_constraint, axis_attr):
                    extras[axis_attr] = getattr(blender_constraint, axis_attr)
            for axis_attr in ("use_scale_x", "use_scale_y", "use_scale_z"):
                if hasattr(blender_constraint, axis_attr):
                    extras[axis_attr] = getattr(blender_constraint, axis_attr)
        except Exception:
            pass

    # skip axes для COPY_LOCATION/ROTATION/SCALE
    skip_translate = []
    skip_rotate = []
    skip_scale = []
    if recipe_type == "point" and hasattr(blender_constraint, "use_x"):
        if not blender_constraint.use_x: skip_translate.append("x")
        if not blender_constraint.use_y: skip_translate.append("y")
        if not blender_constraint.use_z: skip_translate.append("z")
    elif recipe_type == "orient" and hasattr(blender_constraint, "use_x"):
        if not blender_constraint.use_x: skip_rotate.append("x")
        if not blender_constraint.use_y: skip_rotate.append("y")
        if not blender_constraint.use_z: skip_rotate.append("z")
    elif recipe_type == "scale" and hasattr(blender_constraint, "use_x"):
        if not blender_constraint.use_x: skip_scale.append("x")
        if not blender_constraint.use_y: skip_scale.append("y")
        if not blender_constraint.use_z: skip_scale.append("z")

    try:
        influence = float(blender_constraint.influence)
    except Exception:
        influence = 1.0
    extras["influence"] = influence

    return Constraint(
        type=recipe_type,
        source=source,
        target=owner_name,
        maintain_offset=False,  # у Blender нет прямого аналога; использовать use_offset
        skip_translate=skip_translate,
        skip_rotate=skip_rotate,
        skip_scale=skip_scale,
        extras=extras,
    )


# ════════════════════════════════════════════════════════════════════════════
# EXTRACT RECIPE
# ════════════════════════════════════════════════════════════════════════════

def extract_recipe(armature_obj=None,
                   selection_only: bool = True,
                   asset_name: str = "",
                   has_animation: bool = False) -> Recipe:
    """
    Собрать Recipe из armature Blender.

    armature_obj: объект-арматура (если None — активная арматура).
    selection_only: в Blender нет точного аналога selection для bones,
                    игнорируется — берём всю арматуру.
    """
    if armature_obj is None:
        armature_obj = bpy.context.active_object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            # найти любую armature в сцене
            arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
            if not arms:
                raise RuntimeError("No armature in scene")
            armature_obj = arms[0]

    recipe = Recipe(
        version="1.0",
        source_app="blender",
        source_scene=bpy.data.filepath or "",
        asset_name=asset_name or os.path.splitext(os.path.basename(bpy.data.filepath or "untitled.blend"))[0],
        exported_at=datetime.datetime.now().isoformat(timespec="seconds"),
        has_animation=has_animation,
    )

    # ── 1. Controls (bones с custom_shape) ───────────────────────────────
    for pb in armature_obj.pose.bones:
        if pb.custom_shape:
            shape = _extract_custom_shape(pb)
            parent_name = pb.parent.name if pb.parent else None
            recipe.controls.append(Control(
                name=pb.name,
                shape=shape,
                parent_to=parent_name,
            ))

    # ── 2. Constraints ───────────────────────────────────────────────────
    for pb in armature_obj.pose.bones:
        for c in pb.constraints:
            constraint = _extract_constraint(c, pb.name)
            if constraint:
                recipe.constraints.append(constraint)

    # Constraints на object (если armature сама имеет constraint)
    for c in armature_obj.constraints:
        constraint = _extract_constraint(c, armature_obj.name)
        if constraint:
            recipe.constraints.append(constraint)

    # ── 3. Parents (bone hierarchy) ──────────────────────────────────────
    for pb in armature_obj.pose.bones:
        if pb.parent:
            recipe.parents.append(Parent(child=pb.name, parent=pb.parent.name))

    return recipe


# ════════════════════════════════════════════════════════════════════════════
# RECONSTRUCT RIG
# ════════════════════════════════════════════════════════════════════════════

def _resolve_pose_bone(armature_obj, name: str):
    """Найти pose_bone по имени."""
    return armature_obj.pose.bones.get(name)


def _create_constraint(armature_obj, constraint: Constraint) -> bool:
    """Создать Blender constraint по recipe на pose_bone.target."""
    target_pb = _resolve_pose_bone(armature_obj, constraint.target)
    if not target_pb:
        print("Target bone '{}' not found".format(constraint.target))
        return False

    blender_type = RECIPE_TO_BLENDER.get(constraint.type)
    if not blender_type:
        print("Unsupported recipe type '{}'".format(constraint.type))
        return False

    try:
        bc = target_pb.constraints.new(type=blender_type)
        bc.target = armature_obj
        bc.subtarget = constraint.source

        # Apply extras
        extras = constraint.extras or {}

        if blender_type == "CHILD_OF":
            # Восстановить inverse matrix
            inv = extras.get("inverse_matrix")
            if inv and len(inv) == 4:
                for i in range(4):
                    for j in range(4):
                        bc.inverse_matrix[i][j] = float(inv[i][j])
            # Channel toggles
            for axis_attr in ("use_location_x", "use_location_y", "use_location_z",
                              "use_rotation_x", "use_rotation_y", "use_rotation_z",
                              "use_scale_x", "use_scale_y", "use_scale_z"):
                if axis_attr in extras and hasattr(bc, axis_attr):
                    setattr(bc, axis_attr, bool(extras[axis_attr]))

        elif blender_type in ("COPY_LOCATION", "COPY_ROTATION", "COPY_SCALE"):
            # use_x/y/z based on skip lists
            if blender_type == "COPY_LOCATION":
                bc.use_x = "x" not in constraint.skip_translate
                bc.use_y = "y" not in constraint.skip_translate
                bc.use_z = "z" not in constraint.skip_translate
            elif blender_type == "COPY_ROTATION":
                bc.use_x = "x" not in constraint.skip_rotate
                bc.use_y = "y" not in constraint.skip_rotate
                bc.use_z = "z" not in constraint.skip_rotate
            elif blender_type == "COPY_SCALE":
                bc.use_x = "x" not in constraint.skip_scale
                bc.use_y = "y" not in constraint.skip_scale
                bc.use_z = "z" not in constraint.skip_scale

        elif blender_type in ("TRACK_TO", "DAMPED_TRACK"):
            if "track_axis" in extras and hasattr(bc, "track_axis"):
                try:
                    bc.track_axis = extras["track_axis"]
                except Exception:
                    pass
            if blender_type == "TRACK_TO" and "up_axis" in extras and hasattr(bc, "up_axis"):
                try:
                    bc.up_axis = extras["up_axis"]
                except Exception:
                    pass

        if "influence" in extras:
            try:
                bc.influence = float(extras["influence"])
            except Exception:
                pass

        return True
    except Exception as e:
        print("Failed to create {} constraint on {}: {}".format(
            blender_type, constraint.target, e))
        return False


def _apply_control(armature_obj, control: Control) -> bool:
    """Применить custom_shape к bone."""
    pb = _resolve_pose_bone(armature_obj, control.name)
    if not pb:
        print("Control bone '{}' not found".format(control.name))
        return False

    if control.shape:
        sh_obj = _create_custom_shape(control.shape)
        if sh_obj:
            pb.custom_shape = sh_obj
            try:
                pb.custom_shape_scale = 1.0
            except Exception:
                pass
    return True


def _apply_parents(armature_obj, parents: list) -> int:
    """
    Применить parent-child отношения на bones.
    ВАЖНО: parent в Blender меняется в EDIT MODE.
    """
    applied = 0
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')

        for p in parents:
            child_bone = armature_obj.data.edit_bones.get(p.child)
            parent_bone = armature_obj.data.edit_bones.get(p.parent)
            if child_bone and parent_bone:
                child_bone.parent = parent_bone
                applied += 1

        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception as e:
        print("Parent apply failed: {}".format(e))
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    return applied


def reconstruct_rig(recipe: Recipe, armature_obj=None) -> dict:
    """
    Восстановить риг из Recipe в текущей сцене Blender.

    armature_obj: целевая арматура (если None — активная).
    """
    if armature_obj is None:
        armature_obj = bpy.context.active_object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
            if not arms:
                raise RuntimeError("No armature in scene")
            armature_obj = arms[0]

    stats = {
        "controls_applied": 0,
        "controls_missing": 0,
        "constraints_created": 0,
        "constraints_failed": 0,
        "parents_applied": 0,
        "missing_names": set(),
    }

    # 1. Parents — сначала (иерархия должна быть до constraints)
    stats["parents_applied"] = _apply_parents(armature_obj, recipe.parents)

    # 2. Controls (custom shapes)
    for c in recipe.controls:
        if armature_obj.pose.bones.get(c.name):
            if _apply_control(armature_obj, c):
                stats["controls_applied"] += 1
        else:
            stats["controls_missing"] += 1
            stats["missing_names"].add(c.name)

    # 3. Constraints
    for c in recipe.constraints:
        if _create_constraint(armature_obj, c):
            stats["constraints_created"] += 1
        else:
            stats["constraints_failed"] += 1
            if not armature_obj.pose.bones.get(c.source):
                stats["missing_names"].add(c.source)
            if not armature_obj.pose.bones.get(c.target):
                stats["missing_names"].add(c.target)

    stats["missing_names"] = sorted(stats["missing_names"])
    return stats


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINTS (для UI)
# ════════════════════════════════════════════════════════════════════════════

def export_rig(fbx_path: str, recipe_path: str,
               bake_animation: bool = False,
               selection_only: bool = True,
               asset_name: str = "",
               armature_obj=None) -> dict:
    """
    Полный экспорт рига из Blender: FBX + recipe.json.
    """
    result = {"fbx": None, "recipe": None, "error": None}

    try:
        if armature_obj is None:
            armature_obj = bpy.context.active_object
            if not armature_obj or armature_obj.type != 'ARMATURE':
                arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
                if not arms:
                    raise RuntimeError("No armature in scene")
                armature_obj = arms[0]

        # 1. Apply transform (если не legacy)
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        except Exception as e:
            print("transform_apply skipped: {}".format(e))

        # 2. Export FBX (скелет + меши)
        folder = os.path.dirname(fbx_path)
        if not os.path.exists(folder):
            os.makedirs(folder)

        bpy.ops.export_scene.fbx(
            filepath=fbx_path,
            use_selection=False,
            apply_unit_scale=True,
            bake_anim=bake_animation,
            global_scale=1.0,
            axis_forward='-Z',
            axis_up='Y',
            object_types={'MESH', 'EMPTY', 'ARMATURE'},
            use_visible=False,
            use_active_collection=False,
        )
        result["fbx"] = fbx_path

        # 3. Extract recipe
        recipe = extract_recipe(
            armature_obj=armature_obj,
            selection_only=selection_only,
            asset_name=asset_name,
            has_animation=bake_animation,
        )
        recipe.to_json(recipe_path)
        result["recipe"] = recipe_path

    except Exception as e:
        result["error"] = str(e)
        print("Rig export failed: {}".format(e))

    return result


def import_rig_with_recipe(recipe_path: str, armature_obj=None) -> dict:
    """Восстановить риг после FBX-import."""
    try:
        recipe = Recipe.from_json(recipe_path)
    except Exception as e:
        print("Failed to read recipe: {}".format(e))
        return {"error": str(e)}

    errors = recipe.validate()
    if errors:
        print("Recipe validation: {}".format("; ".join(errors)))

    return reconstruct_rig(recipe, armature_obj=armature_obj)
