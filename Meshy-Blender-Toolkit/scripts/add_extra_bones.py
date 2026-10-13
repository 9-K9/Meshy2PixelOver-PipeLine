"""Optional helpers for VRoid hair/clothing after a Mixamo re-rig.

Rigid mode weights selected mesh objects entirely to the head bone. Chain mode
adds a short deform-bone chain, but weighting the vertices remains a manual art step.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_common import absolute, armatures, default_report, save_report, script_args, select_only


def find_head(rig, requested):
    candidates = [requested, "mixamorig:Head", "Head", "head"]
    return next((name for name in candidates if name and name in rig.data.bones), None)


def main():
    args = script_args(
        "Attach rigid hair pieces or create a simple hair bone chain",
        (("--blend",), {"required": True}),
        (("--output",), {"required": True}),
        (("--mode",), {"choices": ("rigid", "chain"), "default": "rigid"}),
        (("--objects",), {"nargs": "*", "default": [], "help": "Hair/clothing mesh object names"}),
        (("--head-bone",), {"default": "mixamorig:Head"}),
        (("--chain-name",), {"default": "HairExtra"}),
        (("--chain-count",), {"type": int, "default": 3}),
        (("--report",), {"default": default_report("extra_bones.json")}),
    )
    bpy.ops.wm.open_mainfile(filepath=str(absolute(args.blend)))
    rigs = armatures()
    if len(rigs) != 1:
        raise RuntimeError(f"Expected one armature, found {len(rigs)}")
    rig = rigs[0]
    head_name = find_head(rig, args.head_bone)
    if not head_name:
        raise RuntimeError("Could not find the head bone")
    changed = []

    if args.mode == "rigid":
        if not args.objects:
            print("WARNING: rigid mode needs --objects (mesh names); nothing was attached")
        for name in args.objects:
            obj = bpy.data.objects.get(name)
            if not obj or obj.type != "MESH":
                print(f"WARNING: mesh object not found: {name}")
                continue
            for group in list(obj.vertex_groups):
                obj.vertex_groups.remove(group)
            group = obj.vertex_groups.new(name=head_name)
            group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
            modifier = next((m for m in obj.modifiers if m.type == "ARMATURE"), None)
            if modifier is None:
                modifier = obj.modifiers.new("Armature", "ARMATURE")
            modifier.object = rig
            if obj.parent != rig:
                obj.parent = rig
                obj.matrix_parent_inverse = rig.matrix_world.inverted()
            changed.append(name)
    else:
        select_only([rig])
        bpy.ops.object.mode_set(mode="EDIT")
        parent = rig.data.edit_bones.get(head_name)
        start = parent.tail.copy()
        length = max(parent.length * 0.35, 0.03)
        for index in range(max(1, args.chain_count)):
            bone = rig.data.edit_bones.new(f"{args.chain_name}.{index + 1:03d}")
            bone.head = start
            bone.tail = start + Vector((0.0, -length, -length * 0.4))
            bone.parent = parent
            bone.use_connect = False
            parent = bone
            start = bone.tail.copy()
            changed.append(bone.name)
        bpy.ops.object.mode_set(mode="OBJECT")
        print("WARNING: chain created, but vertex weights must be painted manually")

    output = absolute(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    save_report(absolute(args.report), {
        "mode": args.mode, "head_bone": head_name, "changed": changed,
        "manual_weighting_required": args.mode == "chain", "output": str(output),
    })
    print(f"ADD_EXTRA_BONES_OK mode={args.mode} changed={len(changed)} output={output}")


if __name__ == "__main__":
    main()
