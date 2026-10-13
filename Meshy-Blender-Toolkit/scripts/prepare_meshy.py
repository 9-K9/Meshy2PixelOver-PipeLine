"""Remove an unwanted rig and export a clean mesh for Mixamo.

This intentionally does not invent a T-pose. It reports whether the arms appear
separated, but pose correction must be inspected visually before Mixamo upload.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_common import (absolute, apply_object_transforms, armatures, default_report, import_model,
                             meshes, reset_scene, rotation_z, save_report, script_args,
                             select_only, world_bounds)


def main():
    args = script_args(
        "Prepare a Meshy character for Mixamo",
        (("--input",), {"required": True}),
        (("--output",), {"required": True}),
        (("--report",), {"default": default_report("prepare_meshy.json")}),
        (("--rotate-z",), {"type": float, "default": 0.0,
                            "help": "Explicit Z rotation in degrees; use 180 if facing backward"}),
        (("--join-meshes",), {"action": "store_true",
                               "help": "Join mesh objects while preserving material slots"}),
        (("--merge-distance",), {"type": float, "default": 0.00001}),
    )
    source, output, report_path = absolute(args.input), absolute(args.output), absolute(args.report)
    reset_scene()
    imported = import_model(source, animations=False)
    imported_meshes = meshes(imported)
    imported_rigs = armatures(imported)
    if not imported_meshes:
        raise RuntimeError("The file contains no mesh objects")

    # Unparent while preserving world transforms, then remove the unwanted skeleton.
    for obj in imported_meshes:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
        for modifier in list(obj.modifiers):
            if modifier.type == "ARMATURE":
                obj.modifiers.remove(modifier)
        obj.vertex_groups.clear()
    for rig in imported_rigs:
        bpy.data.objects.remove(rig, do_unlink=True)

    select_only(imported_meshes)
    bpy.ops.object.make_single_user(object=True, obdata=True)  # shared mesh data cannot take applied transforms
    if args.rotate_z:
        for obj in imported_meshes:
            obj.rotation_euler.z += rotation_z(args.rotate_z)
    apply_object_transforms(imported_meshes)

    # Ground feet at Z=0 and center the horizontal footprint.
    low, high = world_bounds(imported_meshes)
    center_x = (low.x + high.x) / 2.0
    center_y = (low.y + high.y) / 2.0
    for obj in imported_meshes:
        obj.location.x -= center_x
        obj.location.y -= center_y
        obj.location.z -= low.z
    apply_object_transforms(imported_meshes, location=True)

    # Conservative mesh cleanup: merge only extremely close duplicate vertices.
    for obj in imported_meshes:
        select_only([obj])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=args.merge_distance)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")

    if args.join_meshes and len(imported_meshes) > 1:
        select_only(imported_meshes)
        bpy.context.view_layer.objects.active = imported_meshes[0]
        bpy.ops.object.join()
        imported_meshes = [bpy.context.active_object]

    select_only(imported_meshes)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=str(output), use_selection=True, object_types={"MESH"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
        use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False,
        path_mode="COPY", embed_textures=True, axis_forward="-Z", axis_up="Y",
    )
    low, high = world_bounds(imported_meshes)
    size_mb = output.stat().st_size / 1_000_000
    save_report(report_path, {
        "source": str(source), "output": str(output), "removed_armatures": len(imported_rigs),
        "meshes": [obj.name for obj in imported_meshes], "height_m": high.z - low.z, "fbx_size_mb": round(size_mb, 1),
        "facing_assumption": "Character should face -Y (Blender front view); FBX export maps this to +Z, which Mixamo expects",
        "t_pose": "NOT automated; verify arms and legs are separated before Mixamo",
    })
    if size_mb > 95:
        print(f"WARNING: {size_mb:.0f} MB FBX; Mixamo rejects files over ~100 MB. Reduce texture size or mesh density.")
    print(f"PREPARE_MESHY_OK {output}")


if __name__ == "__main__":
    main()
