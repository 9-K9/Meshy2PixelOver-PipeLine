import datetime
import importlib
import json
import subprocess
import sys
import tempfile
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


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _audit_module():
    if not (SCRIPTS / "audit_animations.py").exists():
        raise RuntimeError(f"Toolkit scripts folder not found: {SCRIPTS}")
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import audit_animations
    return importlib.reload(audit_animations)


class MBT_OT_audit_animations(bpy.types.Operator):
    bl_idname = "mbt.audit_animations"
    bl_label = "Audit & Fix Animations"
    bl_description = ("Bind clips to the rig, fix root-motion units and weights, then report what needs "
                      "a human (reweighting, skinning). Problem vertices go into MBT_* vertex groups")
    bl_options = {"REGISTER", "UNDO"}

    in_place: bpy.props.BoolProperty(name="Make clips In Place", default=False,
                                     description="Remove horizontal root travel from every clip")
    report_only: bpy.props.BoolProperty(name="Report only", default=False,
                                        description="Change nothing except the MBT_* marker groups")

    def execute(self, context):
        rigs = [o for o in context.scene.objects if o.type == "ARMATURE"]
        if len(rigs) != 1:
            self.report({"ERROR"}, f"Expected one armature in the scene, found {len(rigs)}")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            module = _audit_module()
            result = module.audit(rigs[0], fix=not self.report_only, in_place=self.in_place)
        except Exception as exc:
            self.report({"ERROR"}, f"Audit failed: {exc}")
            return {"CANCELLED"}
        target = Path(bpy.path.abspath(context.scene.mbt.audit_report_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        for item in result["auto_fixed"]:
            print(f"FIXED  {item['what']}: {item['where']}")
        for item in result["needs_manual"]:
            print(f"MANUAL {item['what']}: {item['where']} -> {item.get('fix', '')}")
        blocking = [m for m in result["needs_manual"] if m.get("severity") != "info"]
        context.scene.mbt.audit_summary = (
            f"Fixed {len(result['auto_fixed'])}, needs you {len(blocking)}"
            + (" - clean" if result["clean"] else "")
        )
        self.report({"WARNING"} if blocking else {"INFO"},
                    f"{context.scene.mbt.audit_summary}. Report: {target}")
        return {"FINISHED"}


class MBT_OT_export_pixelover(bpy.types.Operator):
    bl_idname = "mbt.export_pixelover"
    bl_label = "Export PixelOver GLB"
    bl_description = ("Audit, repair and export this character as a verified, textured, animated GLB. "
                      "Runs on a copy in a background Blender, so this scene is not changed")

    def execute(self, context):
        props = context.scene.mbt
        output = Path(bpy.path.abspath(props.glb_path))
        if props.glb_path.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend first, or set an absolute GLB path")
            return {"CANCELLED"}
        script = SCRIPTS / "export_for_pixelover.py"
        if not script.exists():
            self.report({"ERROR"}, f"Toolkit scripts folder not found: {SCRIPTS}")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "export_copy.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(copy), copy=True)
            command = [bpy.app.binary_path, "--background", "--factory-startup", str(copy),
                       "--python", str(script), "--", "--blend", str(copy), "--output", str(output),
                       "--save-blend", str(output.with_name(output.stem + "_ready.blend"))]
            if not props.glb_in_place:
                command.append("--keep-root-motion")
            result = subprocess.run(command, capture_output=True, text=True)
        log = result.stdout + result.stderr
        print(log)
        interesting = [line for line in log.splitlines()
                       if line.startswith(("FIXED", "WARNING:", "BLOCKER", "EXPORT_PIXELOVER_OK", "RuntimeError"))]
        ok = next((line for line in interesting if line.startswith("EXPORT_PIXELOVER_OK")), None)
        if not ok:
            reason = next((line for line in reversed(log.splitlines()) if "Error" in line), "see the system console")
            props.export_summary = "Export failed"
            self.report({"ERROR"}, f"Export failed: {reason}")
            return {"CANCELLED"}
        warnings = sum(1 for line in interesting if line.startswith("WARNING:"))
        props.export_summary = f"Exported {output.name}" + (f" ({warnings} warning(s))" if warnings else "")
        self.report({"WARNING"} if warnings else {"INFO"}, f"{props.export_summary}: {output}")
        return {"FINISHED"}


CLASSES = (MBT_OT_inspect_scene, MBT_OT_export_report, MBT_OT_backup_blend, MBT_OT_audit_animations,
           MBT_OT_export_pixelover)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
