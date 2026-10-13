"""Import a Mixamo-rigged FBX, normalize scale, and save a master .blend."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_common import (absolute, armatures, default_report, import_model, meshes, object_height,
                             reset_scene, save_report, script_args, select_only)
from audit_animations import fix_textures


def main():
    args = script_args(
        "Create a clean Blender master from a Mixamo character",
        (("--input",), {"required": True}),
        (("--output",), {"required": True, "help": "Output .blend file"}),
        (("--report",), {"default": default_report("post_mixamo.json")}),
        (("--target-height",), {"type": float, "default": 0.0,
                                "help": "Optional character height in metres; 0 preserves imported size"}),
        (("--apply-current-pose-as-rest",), {"action": "store_true",
                                              "help": "Bake the visible pose into the meshes and make it the new rest pose (use only for a deliberate T-pose fix)"}),
    )
    source, output = absolute(args.input), absolute(args.output)
    reset_scene()
    imported = import_model(source, animations=True)
    rigs, character_meshes = armatures(imported), meshes(imported)
    if len(rigs) != 1:
        raise RuntimeError(f"Expected one Mixamo armature, found {len(rigs)}")
    rig = rigs[0]
    names = {bone.name for bone in rig.data.bones}
    prefixed = sum(name.startswith("mixamorig:") for name in names)
    if prefixed == 0:
        print("WARNING: no mixamorig: bone prefix found; animation matching needs inspection")

    original_height = object_height(character_meshes)
    if args.target_height > 0:
        if original_height <= 0:
            raise RuntimeError("Cannot calculate character height")
        factor = args.target_height / original_height
        # Scale the root objects but do NOT apply: animation location keys are stored in
        # the armature's original units, so applying scale would make every clip 100x off.
        for obj in (obj for obj in imported if obj.parent is None):
            obj.scale *= factor

    if args.apply_current_pose_as_rest:
        # Bake the pose into each skinned mesh first, otherwise the mesh would not follow the new rest pose.
        skinned = [(obj, [m.name for m in obj.modifiers if m.type == "ARMATURE" and m.object == rig])
                   for obj in character_meshes]
        for obj, modifier_names in skinned:
            for name in modifier_names:
                select_only([obj])
                try:
                    bpy.ops.object.modifier_apply(modifier=name)
                except RuntimeError as error:
                    raise RuntimeError(f"Cannot bake pose into {obj.name} ({error}); remove its shape keys first") from error
        select_only([rig])
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.armature_apply(selected=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        for obj, modifier_names in skinned:
            for name in modifier_names:
                modifier = obj.modifiers.new(name, "ARMATURE")
                modifier.object = rig
        rig.animation_data_clear()

    # Pack textures; ones Mixamo linked to another machine's path are recovered from assets/ by name.
    texture_fixes, texture_problems = [], []
    fix_textures(character_meshes, texture_fixes, texture_problems, [source.parent])
    for item in texture_fixes:
        print(f"FIXED  {item['what']}: {item['where']} ({item.get('detail', '')})")
    for item in texture_problems:
        print(f"WARNING: {item['what']}: {item['where']} -> {item['fix']}")

    # Material slots remain untouched so skin/hair/clothing can be recoloured independently.
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    save_report(absolute(args.report), {
        "source": str(source), "output": str(output), "armature": rig.name,
        "bones": len(names), "mixamorig_prefixed_bones": prefixed,
        "original_height": original_height, "target_height": args.target_height or None,
        "materials": {obj.name: [slot.name for slot in obj.material_slots] for obj in character_meshes},
        "rest_pose_changed": args.apply_current_pose_as_rest,
        "textures_fixed": texture_fixes, "texture_problems": texture_problems,
    })
    print(f"POST_MIXAMO_OK {output}")


if __name__ == "__main__":
    main()
