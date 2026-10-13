"""Audit a rigged, animated character; repair what is safe to repair; report the rest.

Auto-fixed (safe, reversible from the backup / original file):
  - clips not bound to the rig (Blender 4.4+ action slots) and missing NLA tracks
  - clip bone names using another Mixamo prefix ("mixamorig1:" vs "mixamorig:")
  - root motion in the wrong units (Mixamo centimetres on a metre rig)
  - untagged clips (export_for_pixelover only exports tagged clips)
  - vertex weights that do not add up to 1
  - textures not packed, or linked to a path that no longer exists (recovered by name from
    loose images or source .glb files under assets/), normal maps not set to Non-Color
  - an active action left on the rig, overriding every clip (kept, marked mbt_leftover, never exported)
  - optional (--in-place): horizontal root travel removed

Needs a human (reported, and the vertices are collected into MBT_* vertex groups
so they can be selected in Edit Mode or painted in Weight Paint mode):
  - unweighted vertices (they stay frozen while the body moves)
  - textures that cannot be found anywhere
Items marked blocks_export stop export_for_pixelover; the rest are warnings.
  - weights far from their bone (bad auto-weights, or hair/cloth that needs bones)
  - mesh stretching during a clip (reweighting or rig fixes)
  - clips that animate bones the rig does not have
  - clips that travel (not downloaded "In Place")
"""

from __future__ import annotations

import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import intersect_point_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_common import (absolute, action_bone_names, action_fcurves, armatures, default_report,
                             ensure_clip_strip, hips_bone, meshes, mixamo_prefix, save_report,
                             scale_location_keys, script_args)

GROUP_PREFIX = "MBT_"
LEFTOVER_MAX_FRAMES = 2  # the T-pose "clip" Mixamo leaves on a With Skin download


def _skinned(rig):
    return [o for o in meshes() if any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]


def _is_clip(action, bone_names):
    span = action.frame_range[1] - action.frame_range[0]
    return bool(action_bone_names(action) & bone_names) and span > LEFTOVER_MAX_FRAMES - 1 + 1e-3


def _mark(obj, name, indices):
    """(Re)build an MBT_* vertex group holding indices; removes it when empty."""
    full = GROUP_PREFIX + name
    old = obj.vertex_groups.get(full)
    if old:
        obj.vertex_groups.remove(old)
    if indices:
        obj.vertex_groups.new(name=full).add(sorted(indices), 1.0, "REPLACE")


def _weights(obj, bone_names):
    """Per vertex: [(bone, weight)] for deforming groups only."""
    names = {g.index: g.name for g in obj.vertex_groups}
    return [[(names[g.group], g.weight) for g in v.groups
             if g.weight > 1e-4 and names.get(g.group) in bone_names] for v in obj.data.vertices]


def _up_axis_local(rig):
    return (rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))).normalized()


# ---------------------------------------------------------------- auto fixes

def fix_clips(rig, fixes, manual, in_place):
    bone_names = {b.name for b in rig.data.bones}
    rig_prefix = mixamo_prefix(bone_names)
    hips = hips_bone(rig)
    rig_scale = rig.matrix_world.to_scale().x
    clips = []
    if rig.animation_data and rig.animation_data.action:
        leftover = rig.animation_data.action
        leftover.use_fake_user = True
        if not leftover.get("mbt_clip"):
            leftover["mbt_leftover"] = True
        rig.animation_data.action = None
        fixes.append({"what": "active action cleared", "where": leftover.name,
                      "why": "an active action overrides every clip during playback and export"})
    for action in bpy.data.actions:
        used = action_bone_names(action)
        prefix = mixamo_prefix(used)
        if rig_prefix and prefix and prefix != rig_prefix:
            for fcurve in action_fcurves(action):
                fcurve.data_path = fcurve.data_path.replace(f'["{prefix}', f'["{rig_prefix}')
            fixes.append({"what": "bone prefix renamed", "where": action.name, "detail": f"{prefix} -> {rig_prefix}"})
            used = action_bone_names(action)
        if action.get("mbt_leftover") or not _is_clip(action, bone_names):
            continue
        clips.append(action)
        missing = sorted(used - bone_names)
        if missing:
            manual.append({"what": "clip animates bones the rig lacks", "where": action.name, "bones": missing,
                           "blocks_export": True,
                           "fix": "re-download the clip for this character from Mixamo, or rename the bones"})
            continue
        if not action.get("mbt_clip"):
            action["mbt_clip"] = True
            action.use_fake_user = True
            fixes.append({"what": "clip tagged for export", "where": action.name})
        for done in ensure_clip_strip(action, rig):
            fixes.append({"what": done, "where": action.name,
                          "why": "without it the clip does not drive the rig (Blender 4.4+ action slots)"})
        if hips is not None and "mbt_root_scale" not in action:
            # Rest hips height in rig-local units vs the largest root offset the clip asks for.
            height = hips.head_local.length
            peak = max((abs(k.co.y) for f in action_fcurves(action)
                        if f.data_path == f'pose.bones["{hips.name}"].location' for k in f.keyframe_points),
                       default=0.0)
            factor = 1.0
            if height > 0 and peak > 10 * height:
                factor = 0.01  # centimetre keys on a metre rig
                scale_location_keys(action, factor)
                fixes.append({"what": "root motion converted cm -> m", "where": action.name,
                              "detail": f"hips moved up to {peak * rig_scale:.1f} m; now {peak * factor * rig_scale:.2f} m"})
            action["mbt_root_scale"] = factor
        if hips is not None:
            _root_travel(rig, hips, action, fixes, manual, in_place)
    return clips


def _root_travel(rig, hips, action, fixes, manual, in_place):
    curves = {f.array_index: f for f in action_fcurves(action)
              if f.data_path == f'pose.bones["{hips.name}"].location'}
    if len(curves) < 3:
        return
    start, end = (int(round(x)) for x in action.frame_range)
    to_rig = hips.matrix_local.to_3x3()  # bone-local offset -> rig-local offset
    up = _up_axis_local(rig)
    samples = []
    for frame in range(start, end + 1):
        local = Vector(curves[i].evaluate(frame) for i in range(3))
        rig_offset = to_rig @ local
        samples.append((frame, local, rig_offset - up * rig_offset.dot(up)))
    scale = rig.matrix_world.to_scale().x
    travel = max((s[2] - samples[0][2]).length for s in samples) * scale
    if travel < 0.25:
        return
    if not in_place:
        manual.append({"what": "clip travels (not In Place)", "where": action.name, "metres": round(travel, 2),
                       "fix": "re-download with In Place ticked, or rerun this audit with --in-place"})
        return
    # Pin the hips over the rig origin (their rest spot) so a fixed camera stays centred.
    back = to_rig.inverted()
    for i, curve in curves.items():
        curve.keyframe_points.clear()
    for frame, local, horizontal in samples:
        fixed = local - back @ horizontal
        for i, curve in curves.items():
            curve.keyframe_points.insert(frame, fixed[i], options={"FAST"})
    for curve in curves.values():
        curve.update()
    fixes.append({"what": "root travel removed (in place)", "where": action.name, "metres": round(travel, 2)})


def fix_weights(obj, bone_names, fixes):
    names = {g.index: g.name for g in obj.vertex_groups}
    count = 0
    for v in obj.data.vertices:
        groups = [g for g in v.groups if names.get(g.group) in bone_names and g.weight > 0]
        total = sum(g.weight for g in groups)
        if groups and abs(total - 1.0) > 0.01:
            for g in groups:
                g.weight /= total
            count += 1
    if count:
        fixes.append({"what": "vertex weights normalised", "where": obj.name, "vertices": count})


# ---------------------------------------------------------------- textures

TOOLKIT = Path(__file__).resolve().parent.parent
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tga", ".webp", ".bmp")


def _glb_images(path):
    """{image name: bytes} for every image embedded in a GLB."""
    data = path.read_bytes()
    if data[:4] != b"glTF":
        return {}
    length = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + length])
    binary_start = 20 + length + 8
    views = doc.get("bufferViews", [])
    found = {}
    for index, image in enumerate(doc.get("images", [])):
        if "bufferView" not in image:
            continue
        view = views[image["bufferView"]]
        start = binary_start + view.get("byteOffset", 0)
        name = image.get("name") or f"image_{index}"
        found[name] = data[start:start + view["byteLength"]]
    return found


def _texture_sources(dirs):
    """Loose image files and GLB-embedded images that a lost texture can be recovered from."""
    files, glbs = {}, []
    for folder in dirs:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if "animations" in path.parts:
                continue  # thousands of clip FBXs, no textures
            if path.suffix.lower() in IMAGE_SUFFIXES:
                files.setdefault(path.stem.lower(), path)
            elif path.suffix.lower() == ".glb":
                glbs.append(path)
    return files, glbs


def _usable(image):
    if image.packed_file:
        return True
    path = Path(bpy.path.abspath(image.filepath, library=image.library)) if image.filepath else None
    return bool(path and path.is_file())


def _feeds_normal_map(node):
    return any(link.to_node.type == "NORMAL_MAP" or link.to_socket.name == "Normal"
               for out in node.outputs for link in out.links)


def fix_textures(objects, fixes, manual, search_dirs=None, fix=True):
    """Pack every texture into the .blend; recover lost ones from the source files. A GLB with a
    missing texture renders pink/grey in PixelOver."""
    dirs = [Path(d) for d in (search_dirs or [])]
    if bpy.data.filepath:
        dirs.append(Path(bpy.data.filepath).parent)
    dirs.append(TOOLKIT / "assets")
    nodes = []
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material and slot.material.use_nodes:
                nodes += [(slot.material, n) for n in slot.material.node_tree.nodes
                          if n.type == "TEX_IMAGE" and n.image]
        if not any(slot.material for slot in obj.material_slots):
            manual.append({"what": "mesh has no material", "where": obj.name, "blocks_export": True,
                           "fix": "re-import the textured source, or assign the original material"})
    if objects and not nodes:
        manual.append({"what": "no textures on the character", "where": ", ".join(o.name for o in objects),
                       "blocks_export": True, "fix": "the material lost its Image Texture nodes; rebuild them"})
    sources = None
    for material, node in nodes:
        image = node.image
        if fix and _feeds_normal_map(node) and image.colorspace_settings.name != "Non-Color":
            image.colorspace_settings.name = "Non-Color"
            fixes.append({"what": "normal map set to Non-Color", "where": image.name})
        if image.packed_file:
            continue
        if not fix:
            if not _usable(image):
                manual.append({"what": "missing texture", "where": f"{material.name} / {image.name}",
                               "blocks_export": True, "fix": "run the audit with fixes on, or relink the image"})
            continue
        recovered = None
        if _usable(image):
            image.pack()
            recovered = "packed from " + bpy.path.abspath(image.filepath)
        else:
            if sources is None:
                sources = _texture_sources(dirs)
            loose, glbs = sources
            key = image.name.lower().rsplit(".", 1)[0]
            if key in loose:
                image.filepath = str(loose[key])
                image.reload()
                image.pack()
                recovered = f"relinked to {loose[key]}"
            else:
                for glb in glbs:
                    data = _glb_images(glb).get(image.name) or _glb_images(glb).get(key)
                    if data:
                        saved = TOOLKIT / "work" / "textures" / f"{key}.png"
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        saved.write_bytes(data)
                        image.source = "FILE"
                        image.filepath = str(saved)
                        image.reload()
                        image.pack()
                        recovered = f"recovered from {glb.name} (copy saved to {saved})"
                        break
        if recovered and image.size[0] > 0:
            fixes.append({"what": "texture packed", "where": image.name, "detail": recovered})
        else:
            manual.append({"what": "missing texture", "where": f"{material.name} / {image.name}",
                           "blocks_export": True, "searched": [str(d) for d in dirs],
                           "fix": "put the original image (same name) or the source .glb into assets/, "
                                  "or relink it in the Image Texture node"})


# ---------------------------------------------------------------- manual checks

def check_weights(rig, obj, bone_names, manual, far_ratio, mark):
    weights = _weights(obj, bone_names)
    unweighted = [i for i, w in enumerate(weights) if not w]
    if unweighted:
        manual.append({"what": "unweighted vertices", "where": obj.name, "vertices": len(unweighted),
                       "blocks_export": True,
                       "group": GROUP_PREFIX + "Unweighted",
                       "fix": "Weight Paint them to the nearest bone; they stay frozen while the body moves"})
    to_rig = rig.matrix_world.inverted() @ obj.matrix_world
    coords = [to_rig @ v.co for v in obj.data.vertices]
    up = _up_axis_local(rig)
    heights = [c.dot(up) for c in coords]
    limit = (max(heights) - min(heights)) * far_ratio
    bones = rig.data.bones
    far, per_bone = [], Counter()
    for i, influences in enumerate(weights):
        for bone, weight in influences:
            if weight < 0.3:
                continue
            b = bones[bone]
            point, t = intersect_point_line(coords[i], b.head_local, b.tail_local)
            t = min(max(t, 0.0), 1.0)
            if (coords[i] - b.head_local.lerp(b.tail_local, t)).length > limit:
                far.append(i)
                per_bone[bone] += 1
                break
    if far:
        manual.append({"what": "weights far from their bone", "where": obj.name, "vertices": len(far),
                       "bones": dict(per_bone.most_common(8)), "group": GROUP_PREFIX + "FarWeights",
                       "fix": "usually hair or cloth riding on a body bone; if it swings wrongly, give it its own "
                              "bones (add_extra_bones) or repaint it to the closer bone"})
    many = sum(1 for w in weights if len(w) > 4)
    if many:
        manual.append({"what": "more than 4 bone influences", "where": obj.name, "vertices": many,
                       "severity": "info",
                       "fix": "the GLB exporter keeps the strongest 4; only matters if those vertices look wrong"})
    if mark:
        _mark(obj, "Unweighted", unweighted)
        _mark(obj, "FarWeights", far)


def check_stretch(rig, obj, clips, bone_names, manual, samples, stretch, mark):
    me = obj.data
    edges = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    rest = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", rest)
    rest = rest.reshape(-1, 3)
    rest_len = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    valid = rest_len > 1e-6
    weights = _weights(obj, bone_names)
    dominant = [max(w, key=lambda x: x[1])[0] if w else None for w in weights]
    scene = bpy.context.scene
    ad = rig.animation_data
    saved = (ad.action, scene.frame_current)
    flagged_all = set()
    try:
        for action in clips:
            ad.action = action
            if getattr(action, "slots", None):
                ad.action_slot = action.slots[0]
            start, end = action.frame_range
            frames = sorted({int(round(start + (end - start) * k / max(samples - 1, 1))) for k in range(samples)})
            worst = defaultdict(lambda: [0, 0.0, 0])  # bone -> [vertices, worst ratio, frame]
            clip_verts = set()
            for frame in frames:
                scene.frame_set(frame)
                evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
                mesh = evaluated.to_mesh()
                posed = np.empty(len(mesh.vertices) * 3)
                mesh.vertices.foreach_get("co", posed)
                evaluated.to_mesh_clear()
                posed = posed.reshape(-1, 3)
                ratio = np.ones_like(rest_len)
                ratio[valid] = np.linalg.norm(posed[edges[valid, 0]] - posed[edges[valid, 1]], axis=1) / rest_len[valid]
                for e in np.nonzero(ratio > stretch)[0]:
                    for vi in edges[e]:
                        bone = dominant[vi] or "(unweighted)"
                        clip_verts.add(int(vi))
                        entry = worst[bone]
                        if ratio[e] > entry[1]:
                            entry[1], entry[2] = float(ratio[e]), frame
            if clip_verts:
                per_bone = Counter(dominant[v] or "(unweighted)" for v in clip_verts)
                manual.append({
                    "what": "mesh stretches during clip", "where": f"{obj.name} / {action.name}",
                    "vertices": len(clip_verts), "group": GROUP_PREFIX + "Stretch",
                    "bones": {b: {"vertices": n, "worst_stretch": round(worst[b][1], 2), "frame": worst[b][2]}
                              for b, n in per_bone.most_common(6)},
                    "fix": "scrub to the frame and Weight Paint the listed bone's area smoother; "
                           "small stretch at armpits/hips is normal",
                })
                flagged_all |= clip_verts
    finally:
        ad.action = saved[0]
        scene.frame_set(saved[1])
    if mark:
        _mark(obj, "Stretch", flagged_all)


# ---------------------------------------------------------------- entry points

def audit(rig, fix=True, in_place=False, samples=12, stretch=1.8, far_ratio=0.25, mark=True, texture_dirs=None):
    """Run on the open file. Returns the report dict; callers decide whether to save."""
    fixes, manual = [], []
    bone_names = {b.name for b in rig.data.bones if b.use_deform}
    skinned = _skinned(rig)
    if fix:
        clips = fix_clips(rig, fixes, manual, in_place)
        for obj in skinned:
            fix_weights(obj, bone_names, fixes)
    else:
        clips = [a for a in bpy.data.actions
                 if not a.get("mbt_leftover") and _is_clip(a, {b.name for b in rig.data.bones})]
    if not skinned:
        manual.append({"what": "no mesh is skinned to the rig", "where": rig.name, "blocks_export": True,
                       "fix": "parent the mesh to the armature With Automatic Weights"})
    fix_textures(skinned, fixes, manual, texture_dirs, fix=fix)
    for obj in skinned:
        check_weights(rig, obj, bone_names, manual, far_ratio, mark)
        check_stretch(rig, obj, clips, bone_names, manual, samples, stretch, mark)
    if rig.animation_data:
        rig.animation_data.action = None
    blocking = [m for m in manual if m.get("severity") != "info"]
    return {"rig": rig.name, "meshes": [o.name for o in skinned], "clips": [a.name for a in clips],
            "auto_fixed": fixes, "needs_manual": manual, "clean": not blocking,
            "export_blockers": [m for m in manual if m.get("blocks_export")]}


def main():
    args = script_args(
        "Audit and repair a rigged, animated character",
        (("--blend",), {"required": True}),
        (("--output",), {"required": True, "help": "Repaired copy; the input file is never overwritten"}),
        (("--report",), {"default": default_report("animation_audit.json")}),
        (("--in-place",), {"action": "store_true", "help": "Remove horizontal root travel from every clip"}),
        (("--samples",), {"type": int, "default": 12, "help": "Frames sampled per clip for stretch checks"}),
        (("--stretch",), {"type": float, "default": 1.8, "help": "Edge stretch ratio reported as a problem"}),
        (("--report-only",), {"action": "store_true", "help": "Change nothing except the MBT_* marker groups"}),
    )
    source, output = absolute(args.blend), absolute(args.output)
    if source == output:
        raise RuntimeError("--output must differ from --blend; keep the original")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    rigs = armatures()
    if len(rigs) != 1:
        raise RuntimeError(f"Expected one armature, found {len(rigs)}")
    report = audit(rigs[0], fix=not args.report_only, in_place=args.in_place,
                   samples=args.samples, stretch=args.stretch)
    report.update({"source": str(source), "output": str(output)})
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    save_report(absolute(args.report), report)
    for item in report["auto_fixed"]:
        print(f"FIXED  {item['what']}: {item['where']}")
    for item in report["needs_manual"]:
        tag = "INFO  " if item.get("severity") == "info" else "MANUAL"
        print(f"{tag} {item['what']}: {item['where']} -> {item.get('fix', '')}")
    for item in report["export_blockers"]:
        print(f"BLOCKER {item['what']}: {item['where']}")
    print(f"AUDIT_OK fixed={len(report['auto_fixed'])} manual={len(report['needs_manual'])} "
          f"clean={report['clean']} output={output}")


if __name__ == "__main__":
    main()
