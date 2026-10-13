from pathlib import Path

import bpy

root = Path(__file__).resolve().parent / "fixtures"
root.mkdir(parents=True, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

bpy.ops.mesh.primitive_cube_add(location=(0, 0, 1))
mesh = bpy.context.object
mesh.name = "TestBody"
mesh.scale = (0.3, 0.2, 1.0)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

bpy.ops.object.armature_add(location=(0, 0, 0))
rig = bpy.context.object
rig.name = "MixamoRig"
bpy.ops.object.mode_set(mode="EDIT")
hips = rig.data.edit_bones[0]
hips.name = "mixamorig:Hips"
hips.head = (0, 0, 0.5)
hips.tail = (0, 0, 1.2)
head = rig.data.edit_bones.new("mixamorig:Head")
head.head = hips.tail
head.tail = (0, 0, 2.0)
head.parent = hips
bpy.ops.object.mode_set(mode="OBJECT")

group = mesh.vertex_groups.new(name="mixamorig:Hips")
group.add(range(len(mesh.data.vertices)), 1.0, "REPLACE")
modifier = mesh.modifiers.new("Armature", "ARMATURE")
modifier.object = rig
mesh.parent = rig

for name, angle in (("Idle", 0.05), ("Walk", 0.25)):
    rig.animation_data_clear()
    rig.animation_data_create()
    bone = rig.pose.bones["mixamorig:Hips"]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler.z = 0
    bone.keyframe_insert("rotation_euler", frame=1, group="mixamorig:Hips")
    bone.rotation_euler.z = angle
    bone.keyframe_insert("rotation_euler", frame=12, group="mixamorig:Hips")
    action = rig.animation_data.action
    action.name = name
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 12
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(
        filepath=str(root / f"{name}.fbx"), use_selection=True,
        object_types={"ARMATURE"}, add_leaf_bones=False, bake_anim=True,
        bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
    )

# Character FBX with mesh, rig, and the last action.
bpy.ops.object.select_all(action="DESELECT")
for obj in (rig, mesh):
    obj.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.fbx(
    filepath=str(root / "character.fbx"), use_selection=True,
    object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
    bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
    path_mode="COPY", embed_textures=True,
)

# A deliberately rigged GLB used to verify that prepare_meshy removes the rig.
bpy.ops.export_scene.gltf(
    filepath=str(root / "meshy_source.glb"), export_format="GLB", use_selection=True,
    export_animations=False, export_skins=True,
)
print("FIXTURES_OK", root)
