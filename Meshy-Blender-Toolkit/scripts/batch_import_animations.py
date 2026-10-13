"""Import Mixamo animation-only FBXs as named Actions on one master armature."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_common import (absolute, action_bone_names, action_fcurves, armatures, default_report,
                             ensure_clip_strip, hips_height_world, import_model, mixamo_prefix, save_report,
                             scale_location_keys, script_args)


def clean_name(path: Path):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("_")[:56] or "clip"


def main():
    args = script_args(
        "Attach a folder of Mixamo FBX clips to the active master rig",
        (("--blend",), {"required": True, "help": "Master .blend from post_mixamo.py"}),
        (("--animations",), {"required": True, "help": "Folder containing animation-only FBX files"}),
        (("--output",), {"required": True}),
        (("--report",), {"default": default_report("batch_animations.json")}),
        (("--unit-only",), {"action": "store_true",
                            "help": "Convert root motion units only; do not fit it to the character's height"}),
    )
    bpy.ops.wm.open_mainfile(filepath=str(absolute(args.blend)))
    master_rigs = armatures()
    if len(master_rigs) != 1:
        raise RuntimeError(f"Expected one master armature, found {len(master_rigs)}")
    master = master_rigs[0]
    master_names = {b.name for b in master.data.bones}
    master_prefix = mixamo_prefix(master_names)
    if master.animation_data and master.animation_data.action:
        # Leftover pose clip from the character FBX; keep it but stop it overriding clips.
        master.animation_data.action.use_fake_user = True
        master.animation_data.action["mbt_leftover"] = True  # the audit leaves it alone
        master.animation_data.action = None
    results = []

    files = sorted(absolute(args.animations).glob("*.fbx"))
    if not files:
        raise RuntimeError("No .fbx animations were found")
    for path in files:
        before_actions = set(bpy.data.actions)
        imported = import_model(path, animations=True)
        imported_rigs = armatures(imported)
        new_actions = [a for a in bpy.data.actions if a not in before_actions]
        if not imported_rigs or not new_actions:
            results.append({"file": str(path), "status": "failed", "reason": "No rig or Action imported"})
        else:
            source_rig = imported_rigs[0]
            source_names = {b.name for b in source_rig.data.bones}
            action = new_actions[0]
            used_names = action_bone_names(action)
            clip_prefix = mixamo_prefix(used_names)
            renamed_prefix = False
            if master_prefix and clip_prefix and clip_prefix != master_prefix:
                # e.g. clip uses "mixamorig1:" while the character uses "mixamorig:"
                for fcurve in action_fcurves(action):
                    fcurve.data_path = fcurve.data_path.replace(f'["{clip_prefix}', f'["{master_prefix}')
                used_names = action_bone_names(action)
                renamed_prefix = True
            # Location keys are in the clip rig's own units (Mixamo: centimetres under a 0.01
            # object scale) and proportions. Convert them to the master's, or root motion
            # flings the character metres away and the feet slide.
            root_scale = 1.0
            master_hips, source_hips = hips_height_world(master), hips_height_world(source_rig)
            if master_hips and source_hips:
                unit = source_rig.matrix_world.to_scale().x / master.matrix_world.to_scale().x
                root_scale = unit if args.unit_only else unit * master_hips / source_hips
                if abs(root_scale - 1.0) > 1e-4:
                    scale_location_keys(action, root_scale)
            action["mbt_root_scale"] = root_scale
            missing = sorted(used_names - master_names)
            extra_master = sorted(master_names - source_names)
            action.name = clean_name(path)
            action.use_fake_user = True
            # A one-strip NLA track makes ownership explicit and exports reliably.
            if not missing:
                action["mbt_clip"] = True  # export_for_pixelover only exports tagged clips
                if master.animation_data is None:
                    master.animation_data_create()
                ensure_clip_strip(action, master)
            results.append({
                "file": str(path), "action": action.name,
                "status": "ok" if not missing else "bone_mismatch",
                "prefix_renamed": renamed_prefix, "root_motion_scale": round(root_scale, 6), "missing_on_master": missing, "master_only_bones": extra_master,
            })
        for obj in imported:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)

    output = absolute(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    save_report(absolute(args.report), {"master": master.name, "output": str(output), "clips": results})
    failed = [r for r in results if r["status"] != "ok"]
    print(f"BATCH_IMPORT_OK clips={len(results)} warnings={len(failed)} output={output}")


if __name__ == "__main__":
    main()
