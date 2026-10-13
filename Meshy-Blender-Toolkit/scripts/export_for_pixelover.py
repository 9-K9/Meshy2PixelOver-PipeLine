"""Validate and export one armature, its meshes, and all Actions to GLB."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_common import (absolute, action_bone_names, armatures, default_report, meshes, save_report,
                             script_args, select_only)


def glb_summary(path: Path):
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError("Export is not a valid GLB header")
    version, total = struct.unpack_from("<II", data, 4)
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        raise RuntimeError("GLB first chunk is not JSON")
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    return {
        "glb_version": version, "declared_bytes": total, "actual_bytes": len(data),
        "nodes": len(document.get("nodes", [])), "skins": len(document.get("skins", [])),
        "meshes": len(document.get("meshes", [])),
        "animations": [item.get("name", "") for item in document.get("animations", [])],
    }


def main():
    args = script_args(
        "Export a PixelOver-ready animated GLB",
        (("--blend",), {"required": True}),
        (("--output",), {"required": True}),
        (("--report",), {"default": default_report("pixelover_export.json")}),
        (("--sampling-rate",), {"type": int, "default": 1}),
        (("--all-actions",), {"action": "store_true",
                               "help": "Also export untagged actions (e.g. the leftover T-pose clip)"}),
    )
    bpy.ops.wm.open_mainfile(filepath=str(absolute(args.blend)))
    rigs = armatures()
    if len(rigs) != 1:
        raise RuntimeError(f"PixelOver export expects one armature; found {len(rigs)}")
    rig = rigs[0]
    character_meshes = [obj for obj in meshes() if any(m.type == "ARMATURE" and m.object == rig for m in obj.modifiers)]
    if not character_meshes:
        raise RuntimeError("No skinned meshes use the master armature")
    bone_names = {b.name for b in rig.data.bones}
    if rig.animation_data:
        rig.animation_data.action = None
    tagged = [a for a in bpy.data.actions if a.get("mbt_clip")]
    skipped = []
    if tagged and not args.all_actions:
        # Only this in-memory copy is changed; the .blend on disk is never saved here.
        for action in [a for a in bpy.data.actions if not a.get("mbt_clip")]:
            skipped.append(action.name)
            bpy.data.actions.remove(action)
    elif not tagged:
        print("WARNING: no clips tagged by batch_import_animations.py; exporting every action")
    action_warnings = {}
    for action in bpy.data.actions:
        missing = sorted(action_bone_names(action) - bone_names)
        if missing:
            action_warnings[action.name] = missing
    if action_warnings:
        print(f"WARNING: {len(action_warnings)} Actions reference missing bones")

    output = absolute(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    select_only([rig, *character_meshes])
    bpy.ops.export_scene.gltf(
        filepath=str(output), export_format="GLB", use_selection=True,
        export_materials="EXPORT", export_skins=True, export_animations=True,
        export_animation_mode="ACTIONS", export_anim_single_armature=True,
        export_reset_pose_bones=True, export_rest_position_armature=True,
        export_force_sampling=True, export_frame_step=max(1, args.sampling_rate),
        export_anim_slide_to_zero=True, export_negative_frame="SLIDE",
        export_apply=False, export_morph=True, export_morph_animation=True,
        export_influence_nb=4, export_all_influences=False,
    )
    summary = glb_summary(output)
    if not summary["skins"] or not summary["meshes"]:
        raise RuntimeError(f"GLB validation failed: {summary}")
    save_report(absolute(args.report), {
        "output": str(output), "armature": rig.name, "bone_count": len(bone_names),
        "source_actions": [a.name for a in bpy.data.actions], "skipped_actions": skipped,
        "action_bone_warnings": action_warnings, "glb": summary,
        "pixelover_status": "Structural validation passed; visual playback must still be checked in PixelOver",
    })
    print(f"EXPORT_PIXELOVER_OK animations={len(summary['animations'])} output={output}")


if __name__ == "__main__":
    main()
