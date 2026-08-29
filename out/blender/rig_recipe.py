# -*- coding: utf-8 -*-
"""
rig_recipe.py — DCC-agnostic формат переноса рига для PROKLADKA.

Что это:
  Recipe — JSON-описание рига (constraints, control shapes, parent-child
  иерархия). FBX несёт «тело» рига (скелет, weights, controls как geometry),
  recipe — «нервную систему» (логику связей + формы контролов).

Архитектура:
  rig_asset = FBX (geometry/skeleton/weights) + recipe.json (logic/connections)

Совместимость:
  Python 3.7+ (dataclasses). Чистый Python — работает в Maya, Blender,
  MayaPy, и standalone.

Использование:
  from rig_recipe import Recipe, ControlShape, Constraint, Parent

  recipe = Recipe(source_app="maya", asset_name="I-16")
  recipe.constraints.append(Constraint(type="parent", source="ctl_wing_L",
                                       target="jnt_wing_L"))
  recipe.to_json(r"C:\\temp\\I-16_rig_recipe.json")

  loaded = Recipe.from_json(r"C:\\temp\\I-16_rig_recipe.json")
  loaded.validate()
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any


RECIPE_VERSION = "1.0"

# Поддерживаемые типы constraints (recipe canonical names).
# DCC-слой (rig_maya.py / rig_blender.py) преобразует свои нативные
# constraints в эти канонические типы и обратно.
SUPPORTED_CONSTRAINT_TYPES = {
    "parent",      # parentConstraint (Maya) / CHILD_OF (Blender)
    "point",       # pointConstraint / COPY_LOCATION
    "orient",      # orientConstraint / COPY_ROTATION
    "scale",       # scaleConstraint / COPY_SCALE
    "aim",         # aimConstraint (c worldUpObject) / TRACK_TO
    "aim_no_up",   # aimConstraint (worldUpType=none) / DAMPED_TRACK
}


# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ControlShape:
    """
    Геометрия control shape — DCC-agnostic.
    points: CVs в object space (local). color: RGB list [r,g,b] 0..1, или int index (Maya),
            или None (default).
    """
    type: str = "nurbs_curve"     # пока поддерживаем только nurbs_curve
    degree: int = 1               # 1=linear, 3=cubic
    form: int = 0                 # 0=open, 1=closed, 2=periodic
    points: List[List[float]] = field(default_factory=list)  # [[x,y,z], ...]
    color: Optional[Any] = None   # [r,g,b] or int


@dataclass
class Control:
    """Контрол рига: имя + shape + parent relationship."""
    name: str
    shape: Optional[ControlShape] = None
    parent_to: Optional[str] = None   # имя родительского transform


@dataclass
class Constraint:
    """
    Канонический constraint — один из SUPPORTED_CONSTRAINT_TYPES.

    source: объект, который управляет (driver). В Maya это first target.
    target: объект, которым управляют (driven).
    skip_translate/rotate/scale: list из "x"/"y"/"z" — оси которые НЕ следуют.
    extras: дополнительные параметры специфичные для типа (aim_vector, up_vector и т.д.)
    """
    type: str
    source: str
    target: str
    maintain_offset: bool = True
    skip_translate: List[str] = field(default_factory=list)
    skip_rotate: List[str] = field(default_factory=list)
    skip_scale: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.type not in SUPPORTED_CONSTRAINT_TYPES:
            raise ValueError(
                "Unsupported constraint type '{}'. Supported: {}".format(
                    self.type, sorted(SUPPORTED_CONSTRAINT_TYPES)))


@dataclass
class Parent:
    """Parent relationship — child под parent."""
    child: str
    parent: str


@dataclass
class Recipe:
    """
    Полный рецепт рига.

    Мост между FBX (геометрия) и логикой рига (constraints/parents/shapes).
    Сериализуется в JSON, читается любой DCC-стороной.
    """
    version: str = RECIPE_VERSION
    source_app: str = ""                # "maya" | "blender"
    source_scene: str = ""
    asset_name: str = ""
    exported_at: str = ""
    has_animation: bool = False
    controls: List[Control] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    parents: List[Parent] = field(default_factory=list)

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Полный dict для JSON."""
        return {
            "version": self.version,
            "source_app": self.source_app,
            "source_scene": self.source_scene,
            "asset_name": self.asset_name,
            "exported_at": self.exported_at,
            "has_animation": self.has_animation,
            "controls": [asdict(c) for c in self.controls],
            "constraints": [asdict(c) for c in self.constraints],
            "parents": [asdict(p) for p in self.parents],
        }

    def to_json(self, path: str, indent: int = 2) -> None:
        """Записать recipe в JSON-файл."""
        data = self.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)

    def to_json_string(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recipe":
        """Десериализация из dict (после json.load)."""
        # Parsihg с back-compat — если новые поля отсутствуют
        controls_data = data.get("controls", [])
        constraints_data = data.get("constraints", [])
        parents_data = data.get("parents", [])

        controls = []
        for c in controls_data:
            shape_data = c.get("shape")
            shape = None
            if shape_data:
                shape = ControlShape(
                    type=shape_data.get("type", "nurbs_curve"),
                    degree=shape_data.get("degree", 1),
                    form=shape_data.get("form", 0),
                    points=shape_data.get("points", []),
                    color=shape_data.get("color"),
                )
            controls.append(Control(
                name=c["name"],
                shape=shape,
                parent_to=c.get("parent_to"),
            ))

        constraints = []
        for c in constraints_data:
            extras = c.get("extras", {})
            # back-compat: aim_vector/up_vector могут лежать на верхнем уровне
            for legacy_key in ("aim_vector", "up_vector", "world_up_object",
                               "world_up_type", "world_up_vector"):
                if legacy_key in c and legacy_key not in extras:
                    extras[legacy_key] = c[legacy_key]
            constraints.append(Constraint(
                type=c["type"],
                source=c["source"],
                target=c["target"],
                maintain_offset=c.get("maintain_offset", True),
                skip_translate=c.get("skip_translate", []),
                skip_rotate=c.get("skip_rotate", []),
                skip_scale=c.get("skip_scale", []),
                extras=extras,
            ))

        parents = [Parent(child=p["child"], parent=p["parent"]) for p in parents_data]

        return cls(
            version=data.get("version", RECIPE_VERSION),
            source_app=data.get("source_app", ""),
            source_scene=data.get("source_scene", ""),
            asset_name=data.get("asset_name", ""),
            exported_at=data.get("exported_at", ""),
            has_animation=data.get("has_animation", False),
            controls=controls,
            constraints=constraints,
            parents=parents,
        )

    @classmethod
    def from_json(cls, path: str) -> "Recipe":
        """Прочитать recipe из JSON-файла."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # ── Validation ───────────────────────────────────────────────────────

    def validate(self, raise_on_error: bool = False) -> List[str]:
        """
        Проверить целостность recipe.
        Возвращает список ошибок (пустой если всё OK).
        """
        errors = []

        # 1. Пустой
        if not self.controls and not self.constraints and not self.parents:
            errors.append("Recipe is empty (no controls/constraints/parents)")

        # 2. Все имена контролов уникальны
        ctrl_names = [c.name for c in self.controls]
        duplicates = set([n for n in ctrl_names if ctrl_names.count(n) > 1])
        if duplicates:
            errors.append("Duplicate control names: {}".format(sorted(duplicates)))

        # 3. Constraint sources/targets ссылаются на существующие объекты
        known_names = set(ctrl_names)
        # parents добавляют ещё имена
        for p in self.parents:
            known_names.add(p.child)
            known_names.add(p.parent)
        # constraints добавляют свои (могут быть joints, не controls)
        for c in self.constraints:
            known_names.add(c.source)
            known_names.add(c.target)

        # 4. Parent_to ссылки валидны
        for c in self.controls:
            if c.parent_to and c.parent_to not in known_names:
                errors.append(
                    "Control '{}' has parent_to='{}' which is not defined".format(
                        c.name, c.parent_to))

        # 5. Constraint types валидны
        for c in self.constraints:
            if c.type not in SUPPORTED_CONSTRAINT_TYPES:
                errors.append("Constraint {} has unsupported type '{}'".format(
                    c.source + "->" + c.target, c.type))

        # 6. Нет циклов в parents
        cycle = self._find_parent_cycle()
        if cycle:
            errors.append("Parent cycle detected: {}".format(" -> ".join(cycle)))

        if raise_on_error and errors:
            raise ValueError("Recipe validation failed: " + "; ".join(errors))
        return errors

    def _find_parent_cycle(self) -> Optional[List[str]]:
        """Найти цикл в parent-child иерархии. Возвращает chain или None."""
        graph = {p.child: p.parent for p in self.parents}
        for start in list(graph.keys()):
            visited = []
            current = start
            while current in graph:
                if current in visited:
                    return visited + [current]
                visited.append(current)
                current = graph[current]
                if len(visited) > 1000:  # safety limit
                    return visited
        return None

    # ── Utils ────────────────────────────────────────────────────────────

    def summary(self) -> Dict[str, int]:
        """Краткая сводка для логов/UI."""
        return {
            "controls": len(self.controls),
            "constraints": len(self.constraints),
            "parents": len(self.parents),
            "with_shapes": sum(1 for c in self.controls if c.shape),
        }

    def find_control(self, name: str) -> Optional[Control]:
        for c in self.controls:
            if c.name == name:
                return c
        return None

    def find_constraints_for(self, target: str) -> List[Constraint]:
        return [c for c in self.constraints if c.target == target]


# ════════════════════════════════════════════════════════════════════════════
# FACTORY — быстрые конструкторы для типичных случаев
# ════════════════════════════════════════════════════════════════════════════

def make_parent_constraint(source: str, target: str,
                           skip_scale: bool = True,
                           maintain_offset: bool = True) -> Constraint:
    """Удобный конструктор parent constraint."""
    return Constraint(
        type="parent",
        source=source,
        target=target,
        maintain_offset=maintain_offset,
        skip_scale=["x", "y", "z"] if skip_scale else [],
    )


def make_aim_constraint(source: str, target: str,
                        world_up_object: Optional[str] = None,
                        aim_vector=(1, 0, 0),
                        up_vector=(0, 1, 0)) -> Constraint:
    """Удобный конструктор aim constraint."""
    ctype = "aim" if world_up_object else "aim_no_up"
    extras = {
        "aim_vector": list(aim_vector),
        "up_vector": list(up_vector),
    }
    if world_up_object:
        extras["world_up_object"] = world_up_object
        extras["world_up_type"] = "object"
        extras["world_up_vector"] = [0, 1, 0]
    return Constraint(
        type=ctype,
        source=source,
        target=target,
        extras=extras,
    )


def make_box_shape(size: float = 1.0, color=None) -> ControlShape:
    """Стандартный box-control shape (4 угла, closed)."""
    s = size
    return ControlShape(
        type="nurbs_curve",
        degree=1,
        form=1,  # closed
        points=[
            [-s, -s, 0], [s, -s, 0], [s, s, 0], [-s, s, 0],
        ],
        color=color,
    )


def make_circle_shape(radius: float = 1.0, segments: int = 8, color=None) -> ControlShape:
    """Стандартный circle-control shape."""
    import math
    pts = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        pts.append([round(radius * math.cos(a), 4),
                    round(radius * math.sin(a), 4), 0.0])
    return ControlShape(
        type="nurbs_curve",
        degree=1,
        form=1,  # closed
        points=pts,
        color=color,
    )


# ════════════════════════════════════════════════════════════════════════════
# MERGE
# ════════════════════════════════════════════════════════════════════════════

def merge_recipes(a: Recipe, b: Recipe, prefer: str = "b") -> Recipe:
    """
    Слить два recipe. Полезно для инкрементальных обновлений.

    prefer: "a" или "b" — какой источник приоритетнее при конфликтах.
    """
    primary = a if prefer == "a" else b
    secondary = b if prefer == "a" else a

    merged = Recipe(
        version=RECIPE_VERSION,
        source_app=primary.source_app + "+merged",
        source_scene=primary.source_scene,
        asset_name=primary.asset_name,
        exported_at=datetime.now().isoformat(timespec="seconds"),
        has_animation=primary.has_animation or secondary.has_animation,
    )

    # Merge controls (by name, prefer primary)
    seen_controls = {}
    for c in secondary.controls:
        seen_controls[c.name] = c
    for c in primary.controls:
        seen_controls[c.name] = c
    merged.controls = list(seen_controls.values())

    # Merge constraints (by source+target+type)
    seen_constr = {}
    for c in secondary.constraints:
        key = (c.source, c.target, c.type)
        seen_constr[key] = c
    for c in primary.constraints:
        key = (c.source, c.target, c.type)
        seen_constr[key] = c
    merged.constraints = list(seen_constr.values())

    # Merge parents (by child name)
    seen_parents = {}
    for p in secondary.parents:
        seen_parents[p.child] = p
    for p in primary.parents:
        seen_parents[p.child] = p
    merged.parents = list(seen_parents.values())

    return merged


# ════════════════════════════════════════════════════════════════════════════
# SELF-TEST (run as __main__)
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Testing rig_recipe.py...")

    # Build
    recipe = Recipe(
        source_app="maya",
        source_scene="test.mb",
        asset_name="TestAsset",
    )
    recipe.controls.append(Control(
        name="ctl_main",
        shape=make_box_shape(1.0, color=[1.0, 0.5, 0.0]),
        parent_to="grp_main",
    ))
    recipe.controls.append(Control(
        name="ctl_circle",
        shape=make_circle_shape(2.0, segments=8),
    ))
    recipe.constraints.append(make_parent_constraint("ctl_main", "jnt_main"))
    recipe.constraints.append(make_aim_constraint(
        "ctl_aim", "jnt_gun", world_up_object="ctl_main"))
    recipe.parents.append(Parent(child="jnt_main", parent="jnt_root"))
    recipe.parents.append(Parent(child="grp_main", parent="world"))

    # Validate
    errors = recipe.validate()
    assert not errors, "Validation errors: {}".format(errors)
    print("✓ Validation passed")

    # Serialize / deserialize
    json_str = recipe.to_json_string()
    restored = Recipe.from_dict(json.loads(json_str))
    assert len(restored.controls) == 2
    assert len(restored.constraints) == 2
    assert len(restored.parents) == 2
    print("✓ Serialization round-trip OK")

    # Test cycle detection
    cyclic = Recipe()
    cyclic.parents.append(Parent(child="a", parent="b"))
    cyclic.parents.append(Parent(child="b", parent="a"))
    cycle = cyclic._find_parent_cycle()
    assert cycle, "Cycle not detected"
    print("✓ Cycle detection works: {}".format(cycle))

    # Summary
    print("✓ Summary:", restored.summary())

    print("\nAll tests passed.")
