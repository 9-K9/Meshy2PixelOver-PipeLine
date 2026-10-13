import datetime
import json
from pathlib import Path

import bpy


def scene_report():
    objects = []
    totals = {"objects": 0, "meshes": 0, "armatures": 0, "vertices": 0, "triangles": 0}
    for obj in bpy.context.scene.objects:
        item = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale": list(obj.scale),
        }
        totals["objects"] += 1
        if obj.type == "MESH":
            totals["meshes"] += 1
            item["vertices"] = len(obj.data.vertices)
            item["polygons"] = len(obj.data.polygons)
            item["materials"] = [slot.material.name if slot.material else None for slot in obj.material_slots]
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            item["triangles"] = len(mesh.loop_triangles)
            evaluated.to_mesh_clear()
            totals["vertices"] += item["vertices"]
            totals["triangles"] += item["triangles"]
        elif obj.type == "ARMATURE":
            totals["armatures"] += 1
            item["bones"] = len(obj.data.bones)
            item["actions"] = [action.name for action in bpy.data.actions]
        objects.append(item)
    return {
        "schema": 1,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "blender": bpy.app.version_string,
        "blend_file": bpy.data.filepath,
        "totals": totals,
        "objects": objects,
    }


class MBT_OT_inspect_scene(bpy.types.Operator):
    bl_idname = "mbt.inspect_scene"
    bl_label = "Inspect Scene"
    bl_description = "Inspect the scene without modifying it"
    bl_options = {"REGISTER"}

    def execute(self, context):
        report = scene_report()
        context.scene["mbt_report_json"] = json.dumps(report)
        totals = report["totals"]
        context.scene.mbt.last_summary = (
            f"{totals['meshes']} mesh(es), {totals['armatures']} armature(s), "
            f"{totals['triangles']:,} triangles"
        )
        self.report({"INFO"}, context.scene.mbt.last_summary)
        return {"FINISHED"}


class MBT_OT_export_report(bpy.types.Operator):
    bl_idname = "mbt.export_report"
    bl_label = "Export Report"
    bl_description = "Write the latest inspection as JSON"

    def execute(self, context):
        report = scene_report()
        target = Path(bpy.path.abspath(context.scene.mbt.report_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.report({"INFO"}, f"Report saved: {target}")
        return {"FINISHED"}


class MBT_OT_backup_blend(bpy.types.Operator):
    bl_idname = "mbt.backup_blend"
    bl_label = "Create Backup"
    bl_description = "Save a timestamped copy without changing the current working filename"

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend file once before creating a backup")
            return {"CANCELLED"}
        source = Path(bpy.data.filepath)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = source.parent / "backups" / f"{source.stem}-{stamp}.blend"
        backup.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(backup), copy=True)
        self.report({"INFO"}, f"Backup saved: {backup}")
        return {"FINISHED"}


CLASSES = (MBT_OT_inspect_scene, MBT_OT_export_report, MBT_OT_backup_blend)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
