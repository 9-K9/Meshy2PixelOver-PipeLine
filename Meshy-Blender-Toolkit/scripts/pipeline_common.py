"""Shared helpers for the Meshy -> Mixamo -> Blender -> PixelOver pipeline."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def script_args(description: str, *arguments):
    parser = argparse.ArgumentParser(description=description)
    for args, kwargs in arguments:
        parser.add_argument(*args, **kwargs)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def absolute(path: str) -> Path:
    return Path(bpy.path.abspath(path)).expanduser().resolve()


def reset_scene():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.armatures, bpy.data.meshes, bpy.data.materials, bpy.data.actions):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def import_model(path: Path, animations: bool = True):
    suffix = path.suffix.lower()
    before = set(bpy.context.scene.objects)
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), use_anim=animations, use_image_search=True)
    elif suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True)
    else:
        raise ValueError(f"Unsupported input format: {suffix}. Use FBX, GLB, or glTF.")
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def armatures(objects=None):
    source = objects if objects is not None else bpy.context.scene.objects
    return [obj for obj in source if obj.type == "ARMATURE"]


def meshes(objects=None):
    source = objects if objects is not None else bpy.context.scene.objects
    return [obj for obj in source if obj.type == "MESH"]


def world_bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise ValueError("No mesh bounds were found")
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def apply_object_transforms(objects, location=False):
    select_only(objects)
    bpy.ops.object.transform_apply(location=location, rotation=True, scale=True)


def ensure_parent_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def save_report(path: Path, payload):
    ensure_parent_dir(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def rotation_z(degrees: float):
    return math.radians(degrees)


TOOLKIT_ROOT = Path(__file__).resolve().parents[1]


def default_report(name: str) -> str:
    """Reports always go to <toolkit>/reports, independent of the working directory."""
    return str(TOOLKIT_ROOT / "reports" / name)


def action_fcurves(action):
    """Yield F-curves for both legacy actions and Blender 4.4+ layered actions."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        yield from legacy
        return
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                yield from bag.fcurves


def action_bone_names(action):
    names = set()
    marker = 'pose.bones["'
    for fcurve in action_fcurves(action):
        if marker in fcurve.data_path:
            names.add(fcurve.data_path.split(marker, 1)[1].split('"]', 1)[0])
    return names


def mixamo_prefix(names):
    """Return the shared 'mixamorigN:' style prefix of a set of bone names, or None."""
    prefixes = {m.group(0) for n in names if (m := re.match(r"mixamorig\d*:", n))}
    return prefixes.pop() if len(prefixes) == 1 else None


def object_height(objects):
    low, high = world_bounds(objects)
    return high.z - low.z


def hips_bone(rig):
    """The Mixamo root bone ('mixamorig:Hips', 'mixamorig1:Hips', ...) or None."""
    return next((b for b in rig.data.bones if b.name.split(":")[-1] == "Hips"), None)


def hips_height_world(rig):
    """World-space height of the hips at rest; the yardstick for root-motion scale."""
    bone = hips_bone(rig)
    if bone is None:
        return None
    return (rig.matrix_world @ bone.head_local).z - rig.matrix_world.translation.z


def scale_location_keys(action, factor):
    """Scale every pose-bone location key (root motion) by factor."""
    for fcurve in action_fcurves(action):
        if fcurve.data_path.startswith("pose.bones[") and fcurve.data_path.endswith(".location"):
            for key in fcurve.keyframe_points:
                key.co.y *= factor
                key.handle_left.y *= factor
                key.handle_right.y *= factor
            fcurve.update()


def bind_action(action, rig):
    """Blender 4.4+ slotted actions: name the clip's slot after the rig so Blender binds it
    to that rig automatically. Returns the slot (None on pre-4.4 Blender)."""
    slots = getattr(action, "slots", None)
    if not slots:
        return None
    slot = slots[0]
    if slot.name_display != rig.name:
        slot.name_display = rig.name
    return slot


def ensure_clip_strip(action, rig):
    """One muted NLA track per clip, with the clip's slot assigned. Returns a list of fixes made."""
    fixes = []
    if rig.animation_data is None:
        rig.animation_data_create()
    slot = bind_action(action, rig)
    track = next((t for t in rig.animation_data.nla_tracks
                  if any(s.action == action for s in t.strips)), None)
    if track is None:
        track = rig.animation_data.nla_tracks.new()
        track.name = action.name
        strip = track.strips.new(action.name, int(action.frame_range[0]), action)
        strip.action_frame_start, strip.action_frame_end = action.frame_range
        track.mute = True  # Stored, not layered over other clips in Blender playback.
        fixes.append("created NLA track")
    strip = next(s for s in track.strips if s.action == action)
    if slot is not None and getattr(strip, "action_slot", slot) != slot:
        strip.action_slot = slot
        fixes.append("assigned action slot")
    return fixes
