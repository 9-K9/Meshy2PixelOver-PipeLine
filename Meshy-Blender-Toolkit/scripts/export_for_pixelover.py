"""Audit, repair, export and verify: one armature, its meshes and every clip as a PixelOver-ready GLB.

Steps:
  1. audit_animations.audit() repairs clip binding, root-motion units, bone prefixes, weights and
     textures, and (by default) makes every clip In Place. Problems that only a person can fix
     (unweighted vertices, lost textures, clips for another skeleton) stop the export unless
     --allow-manual is given.
  2. Only clips tagged by batch_import_animations / the audit are exported.
  3. The GLB is reopened and checked: one skin, a mesh, a material, embedded textures and at least
     one animation with real keyframes.
The input .blend is never modified; --save-blend writes the audited copy.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_animations import audit
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
    accessors = document.get("accessors", [])
    animations = []
    for item in document.get("animations", []):
        times = [accessors[s["input"]].get("max", [0])[0] for s in item.get("samplers", [])]
        animations.append({"name": item.get("name", ""), "channels": len(item.get("channels", [])),
                           "seconds": round(max(times, default=0.0), 3)})
    images = document.get("images", [])
    return {
        "glb_version": version, "declared_bytes": total, "actual_bytes": len(data),
        "nodes": len(document.get("nodes", [])), "skins": len(document.get("skins", [])),
        "meshes": len(document.get("meshes", [])), "materials": len(document.get("materials", [])),
        "images": len(images), "external_images": [i.get("uri") for i in images if "uri" in i],
        "animations": [a["name"] for a in animations], "animation_details": animations,
    }


def verify_glb(summary, expected_images):
    """Everything PixelOver needs to show a textured, animated character. Returns a list of problems."""
    problems = []
    if summary["declared_bytes"] != summary["actual_bytes"]:
        problems.append("file is truncated")
    if summary["skins"] != 1:
        problems.append(f"expected 1 skin, found {summary['skins']}")
    if not summary["meshes"]:
        problems.append("no mesh")
    if not summary["materials"]:
        problems.append("no material")
    if summary["external_images"]:
        problems.append(f"textures not embedded: {summary['external_images']}")
    if summary["images"] < expected_images:
        problems.append(f"only {summary['images']} of {expected_images} textures were embedded")
    if not summary["animations"]:
        problems.append("no animations")
    for item in summary["animation_details"]:
        if not item["channels"] or item["seconds"] <= 0:
            problems.append(f"animation {item['name']!r} has no keyframes")
    return problems


def main():
    args = script_args(
        "Export a PixelOver-ready animated GLB",
        (("--blend",), {"required": True}),
        (("--output",), {"required": True}),
        (("--report",), {"default": default_report("pixelover_export.json")}),
        (("--sampling-rate",), {"type": int, "default": 1}),
        (("--all-actions",), {"action": "store_true",
                               "help": "Also export untagged actions (e.g. the leftover T-pose clip)"}),
        (("--keep-root-motion",), {"action": "store_true",
                                   "help": "Keep clips travelling; by default they are made In Place for sprites"}),
        (("--allow-manual",), {"action": "store_true",
                               "help": "Export even if the audit found problems that need a person"}),
        (("--save-blend",), {"default": "", "help": "Also save the audited, export-ready .blend here"}),
        (("--audit-report",), {"default": default_report("pixelover_audit.json")}),
    )
    source = absolute(args.blend)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    rigs = armatures()
    if len(rigs) != 1:
        raise RuntimeError(f"PixelOver export expects one armature; found {len(rigs)}")
    rig = rigs[0]
    audit_report = audit(rig, fix=True, in_place=not args.keep_root_motion)
    audit_report["source"] = str(source)
    save_report(absolute(args.audit_report), audit_report)
    for item in audit_report["auto_fixed"]:
        print(f"FIXED  {item['what']}: {item['where']}")
    for item in audit_report["needs_manual"]:
        tag = "BLOCKER" if item.get("blocks_export") else "INFO   " if item.get("severity") == "info" else "WARNING:"
        print(f"{tag} {item['what']}: {item['where']} -> {item.get('fix', '')}")
    if audit_report["export_blockers"] and not args.allow_manual:
        raise RuntimeError(f"{len(audit_report['export_blockers'])} problem(s) need fixing by hand before export; "
                           f"see {absolute(args.audit_report)} (or pass --allow-manual)")
    if args.save_blend:
        saved = absolute(args.save_blend)
        if saved == source:
            raise RuntimeError("--save-blend must differ from --blend; keep the original")
        saved.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(saved), copy=True)
        print(f"SAVED_AUDITED_BLEND {saved}")
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
    expected_images = len({n.image.name for o in character_meshes for slot in o.material_slots if slot.material
                           and slot.material.use_nodes for n in slot.material.node_tree.nodes
                           if n.type == "TEX_IMAGE" and n.image and any(out.links for out in n.outputs)})
    problems = verify_glb(summary, expected_images)
    if problems:
        raise RuntimeError(f"GLB verification failed: {problems}")
    save_report(absolute(args.report), {
        "output": str(output), "armature": rig.name, "bone_count": len(bone_names),
        "source_actions": [a.name for a in bpy.data.actions], "skipped_actions": skipped,
        "action_bone_warnings": action_warnings, "glb": summary,
        "audit": {"auto_fixed": audit_report["auto_fixed"], "needs_manual": audit_report["needs_manual"]},
        "in_place": not args.keep_root_motion,
        "pixelover_status": "Audited and verified (textures embedded, skin, keyed animations); "
                            "check the look in PixelOver",
    })
    warnings = [m for m in audit_report["needs_manual"] if not m.get("blocks_export") and m.get("severity") != "info"]
    print(f"EXPORT_PIXELOVER_OK animations={len(summary['animations'])} textures={summary['images']} "
          f"warnings={len(warnings)} output={output}")


if __name__ == "__main__":
    main()
