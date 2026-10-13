"""Find the Without Skin copy of Mixamo clips in the local Mixamo library.

With Skin downloads carry a whole character mesh (~12 MB each) on top of the motion.
The pipeline only needs the motion, so for every clip you hand it, this tool looks in
assets/animations/Mixamo/ (loose FBX in any sub-folder AND the FBX inside the
Animation_Packs_ZIP/*.zip packs) for the skinless clip with the same motion.

Matching is by motion, not by file name: Mixamo numbers variants ("Great Sword Slash (2)")
and the library was de-duplicated by name, so a name can point at the wrong variant.
Every library clip is fingerprinted once (bone directions over time, cached in
cache/mixamo_index.*) and each query is aligned against it with a time warp that allows
trimmed, sped-up/slowed-down and mirrored downloads. The same-name clip wins ties.

Typical use (headless):
  ./run-headless.sh --python scripts/find_skinless_clips.py -- \\
      --query assets/animations/KatanaKitsune-AnimationsFBX --collect work/katanakitsune_clips

  --index-only            just (re)build the fingerprint cache
  --catalog PATH          write a Markdown list of every clip in the library
  --names TSV             "query stem<TAB>output name" to rename collected clips
  --threshold DEG         mean bone-direction error accepted as the same motion (default 8)
  --jobs N                parallel Blender processes for indexing (default 4)
Queries with no skinless match are copied as-is only with --fallback-skinned, and are
always listed in the report under "redownload" so they can be fetched Without Skin.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_common import absolute, save_report, script_args

TOOLKIT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY = TOOLKIT / "assets" / "animations" / "Mixamo"
DEFAULT_CACHE = TOOLKIT / "cache" / "mixamo_index"
INDEX_VERSION = 1
MAX_SAMPLES = 150
BONES = ["Hips", "Spine", "Spine2", "Neck", "Head",
         "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
         "RightShoulder", "RightArm", "RightForeArm", "RightHand",
         "LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]
MIRROR = [BONES.index(b.replace("Left", "#").replace("Right", "Left").replace("#", "Right")) for b in BONES]
NUMBERED = re.compile(r"\s*\(\d+\)\s*$")


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", NUMBERED.sub("", Path(name).stem).lower())


# --------------------------------------------------------------------- library listing

def library_entries(library: Path):
    """Every FBX in the library: loose files and members of the pack zips."""
    entries = []
    for path in sorted(library.rglob("*")):
        if path.suffix.lower() == ".fbx" and path.is_file():
            st = path.stat()
            rel = path.relative_to(library).as_posix()
            entries.append({"id": rel, "kind": "file", "name": path.stem, "group": path.parent.relative_to(library).as_posix(),
                            "stamp": f"{st.st_size}:{int(st.st_mtime)}"})
        elif path.suffix.lower() == ".zip" and path.is_file():
            try:
                with zipfile.ZipFile(path) as archive:
                    for info in archive.infolist():
                        if info.filename.lower().endswith(".fbx") and not info.is_dir():
                            rel = path.relative_to(library).as_posix()
                            entries.append({"id": f"{rel}::{info.filename}", "kind": "zip", "name": Path(info.filename).stem,
                                            "group": f"{path.stem} (zip)", "stamp": f"{info.file_size}:{info.CRC}"})
            except zipfile.BadZipFile:
                print(f"WARNING: unreadable zip {path}")
    return entries


def materialize(library: Path, entry, folder: Path) -> Path:
    """A real FBX path for an entry (zip members are extracted into folder)."""
    if entry["kind"] == "file":
        return library / entry["id"]
    zip_rel, member = entry["id"].split("::", 1)
    with zipfile.ZipFile(library / zip_rel) as archive:
        target = folder / hashlib.sha1(entry["id"].encode()).hexdigest()[:12] / Path(member).name
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return target


# --------------------------------------------------------------------- fingerprints

def _clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions, bpy.data.materials,
                 bpy.data.images, bpy.data.textures):
        for block in list(coll):
            coll.remove(block)


def fingerprint(path: Path):
    """(meta, directions[F, len(BONES), 3]) for one FBX, or (meta with error, None)."""
    _clear()
    try:
        bpy.ops.import_scene.fbx(filepath=str(path), use_anim=True, use_image_search=False)
    except Exception as exc:  # noqa: BLE001 - a broken file must not stop indexing
        return {"error": f"import failed: {exc}"}, None
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    meta = {"meshes": len(meshes), "skinned": bool(meshes)}
    rig = next((r for r in rigs if r.animation_data and r.animation_data.action), None)
    if rig is None:
        meta["error"] = "no animation"
        return meta, None
    by_suffix = {b.name.split(":")[-1]: b for b in rig.pose.bones}
    if "Hips" not in by_suffix:
        meta["error"] = "not a Mixamo skeleton"
        return meta, None
    action = rig.animation_data.action
    start, end = (int(round(v)) for v in action.frame_range)
    frames = max(end - start, 1)
    count = min(frames + 1, MAX_SAMPLES)
    scene = bpy.context.scene
    world = rig.matrix_world
    hips = by_suffix["Hips"]
    rest_height = max((world @ hips.bone.head_local).z, 1e-6)
    data = np.full((count, len(BONES), 3), np.nan, dtype=np.float32)
    heights, xy = [], []
    for i in range(count):
        frame = start + frames * i / max(count - 1, 1)
        scene.frame_set(int(frame), subframe=frame - int(frame))
        for b, name in enumerate(BONES):
            bone = by_suffix.get(name)
            if bone is not None:
                axis = (world.to_3x3() @ bone.matrix.col[1].xyz).normalized()
                data[i, b] = axis
        head = world @ hips.head
        heights.append(head.z / rest_height)
        xy.append((head.x / rest_height, head.y / rest_height))
    xy = np.array(xy)
    meta.update(frames=frames, fps=scene.render.fps, step=frames / max(count - 1, 1),
                travel=round(float(np.max(np.linalg.norm(xy - xy[0], axis=1))), 3),
                hips_min=round(min(heights), 3), hips_max=round(max(heights), 3))
    return meta, data


def _key(entry):
    return hashlib.sha1(f"{entry['id']}|{entry['stamp']}|{INDEX_VERSION}".encode()).hexdigest()


def _load_index(cache: Path):
    meta_path, data_path = cache.with_suffix(".json"), cache.with_suffix(".npz")
    if not meta_path.exists() or not data_path.exists():
        return {}, {}
    meta = json.loads(meta_path.read_text())
    with np.load(data_path) as npz:
        arrays = {k: npz[k] for k in npz.files}
    return meta, arrays


def _save_index(cache: Path, meta, arrays):
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    np.savez_compressed(cache.with_suffix(".npz"), **arrays)


def _index_worker(library: Path, worklist: Path, out: Path):
    entries = json.loads(worklist.read_text())
    meta, arrays = {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        for n, entry in enumerate(entries, 1):
            path = materialize(library, entry, Path(tmp))
            info, data = fingerprint(path)
            if entry["kind"] == "zip":
                path.unlink(missing_ok=True)
            key = _key(entry)
            meta[key] = info
            if data is not None:
                arrays[key] = data
            if n % 50 == 0:
                print(f"  indexed {n}/{len(entries)}", flush=True)
    _save_index(out, meta, arrays)


def build_index(library: Path, cache: Path, jobs: int):
    entries = library_entries(library)
    meta, arrays = _load_index(cache)
    todo = [e for e in entries if _key(e) not in meta]
    print(f"Mixamo library: {len(entries)} clips, {len(todo)} to fingerprint")
    if todo:
        jobs = max(1, min(jobs, len(todo)))
        with tempfile.TemporaryDirectory() as tmp:
            procs, outs = [], []
            for j in range(jobs):
                work = Path(tmp) / f"work{j}.json"
                work.write_text(json.dumps(todo[j::jobs]))
                out = Path(tmp) / f"part{j}"
                outs.append(out)
                procs.append(subprocess.Popen([bpy.app.binary_path, "--background", "--factory-startup",
                                               "--python", __file__, "--", "--worker", str(work),
                                               "--library", str(library), "--cache", str(out)],
                                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
            for j, proc in enumerate(procs):
                for line in proc.stdout:
                    if line.startswith("  indexed") or "Traceback" in line or "Error" in line:
                        print(f"[job {j}]{line.rstrip()}", flush=True)
                proc.wait()
            for out in outs:
                part_meta, part_arrays = _load_index(out)
                meta.update(part_meta)
                arrays.update(part_arrays)
    live = {_key(e) for e in entries}
    meta = {k: v for k, v in meta.items() if k in live}
    arrays = {k: v for k, v in arrays.items() if k in live}
    _save_index(cache, meta, arrays)
    for entry in entries:
        entry.update(meta.get(_key(entry), {"error": "not indexed"}))
    return entries, {e["id"]: arrays.get(_key(e)) for e in entries}


# --------------------------------------------------------------------- matching

def _cost_matrix(q, lib):
    """Mean angle (radians) between bone directions of every query/library frame pair."""
    valid = ~(np.isnan(q).any(-1)[:, None, :] | np.isnan(lib).any(-1)[None, :, :])
    dots = np.einsum("ibk,jbk->ijb", np.nan_to_num(q), np.nan_to_num(lib))
    angles = np.arccos(np.clip(dots, -1.0, 1.0)) * valid
    return angles.sum(-1) / np.maximum(valid.sum(-1), 1)


MIN_OVERLAP = 0.75  # share of the shorter clip that must line up
PROBABLE_MARGIN = 2.0  # degrees over --threshold still accepted for a same-name, whole-clip match


def align(q, lib, q_step, lib_step):
    """Best linear time alignment lib_frame = offset + speed * query_frame.

    Mixamo's only timing options are Trim (an offset) and Overdrive/Speed (a constant
    scale), so a straight line is the honest model; a free time warp would let a still
    pose match one frame of anything. Speeds 0.5x..2x are searched.
    Returns (mean degrees, first lib sample, last lib sample)."""
    cost = _cost_matrix(q, lib)
    n, m = cost.shape
    base = q_step / lib_step  # query sample -> library sample at equal speed
    best = (math.inf, 0, 0)
    i = np.arange(n)
    for speed in base * np.geomspace(0.5, 2.0, 41):
        span = speed * (n - 1)
        offsets = np.arange(-math.floor(span), m)
        j = np.rint(offsets[:, None] + speed * i[None, :]).astype(int)
        valid = (j >= 0) & (j < m)
        used = valid.sum(1)
        need = MIN_OVERLAP * min(n, (m - 1) / speed + 1)
        values = np.where(valid, cost[i[None, :], np.clip(j, 0, m - 1)], 0.0).sum(1) / np.maximum(used, 1)
        values[used < need] = math.inf
        k = int(np.argmin(values))
        if values[k] < best[0]:
            hit = j[k][valid[k]]
            best = (float(values[k]), int(hit.min()), int(hit.max()))
    return math.degrees(best[0]), best[1], best[2]


def _summary(data):
    return np.nan_to_num(np.concatenate([np.nanmean(data, 0), np.nanstd(data, 0)], -1)).ravel()


def match(q_meta, q, entries, arrays, threshold, shortlist=60):
    variants = {"normal": q}
    mirrored = q[:, MIRROR].copy()
    mirrored[..., 0] *= -1
    variants["mirrored"] = mirrored
    candidates = [e for e in entries if arrays.get(e["id"]) is not None and not e.get("skinned")]
    want = norm_name(q_meta["name"])
    results = []
    for label, query in variants.items():
        qs = _summary(query)
        ranked = sorted(candidates, key=lambda e: float(np.linalg.norm(_summary(arrays[e["id"]]) - qs)))
        pool = {e["id"]: e for e in ranked[:shortlist]}
        pool.update({e["id"]: e for e in candidates if norm_name(e["name"]) == want})
        for entry in pool.values():
            lib = arrays[entry["id"]]
            score, s, t = align(query, lib, q_meta["step"], entry["step"])
            results.append({"id": entry["id"], "name": entry["name"], "group": entry["group"], "kind": entry["kind"],
                            "deg": round(score, 2), "mirrored": label == "mirrored",
                            "lib_frames": entry["frames"], "lib_range": [round(s * entry["step"]), round(t * entry["step"])],
                            "same_name": norm_name(entry["name"]) == want})
    results.sort(key=lambda r: r["deg"])
    best = results[0] if results else None
    if best:
        named = [r for r in results if r["same_name"] and r["deg"] <= threshold and r["deg"] <= best["deg"] + 1.0]
        if named:
            best = named[0]
    return best, results[:5]


def query_entries(folder: Path):
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".fbx") if folder.is_dir() else [folder]
    return files


# --------------------------------------------------------------------- catalog

def write_catalog(path: Path, entries):
    groups = {}
    for e in entries:
        groups.setdefault(e["group"], []).append(e)
    skinless = sum(1 for e in entries if not e.get("skinned") and not e.get("error"))
    lines = ["# Mixamo library catalog", "",
             f"Generated by `scripts/find_skinless_clips.py --catalog` from `assets/animations/Mixamo/`.",
             f"{len(entries)} FBX: {skinless} usable Without Skin clips. Names are exactly as downloaded from Mixamo;",
             "\"(n)\" suffixes are Mixamo variants of the same animation name.", "",
             "Flags: **skin** = With Skin download (has a mesh), **err** = could not be read.", ""]
    for group in sorted(groups):
        items = sorted(groups[group], key=lambda e: e["name"].lower())
        lines += [f"## {group} ({len(items)})", "", "| Animation | Frames | Flags |", "|---|---|---|"]
        for e in items:
            flags = "skin" if e.get("skinned") else ("err" if e.get("error") else "")
            lines.append(f"| {e['name']} | {e.get('frames', '')} | {flags} |")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    print(f"CATALOG {path} ({len(entries)} entries)")


# --------------------------------------------------------------------- main

def main():
    args = script_args(
        __doc__.splitlines()[0],
        (("--library",), {"default": str(DEFAULT_LIBRARY)}),
        (("--cache",), {"default": str(DEFAULT_CACHE)}),
        (("--query",), {"default": ""}),
        (("--collect",), {"default": ""}),
        (("--names",), {"default": ""}),
        (("--report",), {"default": ""}),
        (("--catalog",), {"default": ""}),
        (("--threshold",), {"type": float, "default": 8.0}),
        (("--jobs",), {"type": int, "default": 4}),
        (("--index-only",), {"action": "store_true"}),
        (("--fallback-skinned",), {"action": "store_true"}),
        (("--worker",), {"default": ""}),
    )
    library, cache = absolute(args.library), absolute(args.cache)
    if args.worker:
        _index_worker(library, Path(args.worker), cache)
        return
    if not library.is_dir():
        raise SystemExit(f"Mixamo library not found: {library}")
    entries, arrays = build_index(library, cache, args.jobs)
    if args.catalog:
        write_catalog(absolute(args.catalog), entries)
    if args.index_only or not args.query:
        print("FIND_SKINLESS_OK index_only")
        return

    renames = {}
    if args.names:
        for line in absolute(args.names).read_text().splitlines():
            if "\t" in line and not line.startswith("#"):
                src, dst = line.split("\t", 1)
                renames[src.strip()] = dst.strip()
    collect = absolute(args.collect) if args.collect else None
    if collect:
        collect.mkdir(parents=True, exist_ok=True)
    report = {"library": str(library), "threshold_deg": args.threshold, "clips": [], "redownload": []}
    for path in query_entries(absolute(args.query)):
        q_meta, q = fingerprint(path)
        q_meta["name"] = path.stem
        row = {"query": path.name, "query_frames": q_meta.get("frames"), "query_skinned": q_meta.get("skinned"),
               "query_travel": q_meta.get("travel")}
        if q is None:
            row.update(status="error", error=q_meta.get("error"))
            report["clips"].append(row)
            continue
        best, top = match(q_meta, q, entries, arrays, args.threshold)
        row["candidates"] = top
        out_name = renames.get(path.stem, path.stem) + ".fbx"
        if best and best["deg"] <= args.threshold and not best["mirrored"]:
            row.update(status="matched", source=best)
        elif best and best["mirrored"] and best["deg"] <= args.threshold:
            row.update(status="mirrored", source=best,
                       note="same motion mirrored: re-download it Without Skin with Mirror ticked")
        else:
            probable = next((r for r in top if r["same_name"] and not r["mirrored"]
                             and r["deg"] <= args.threshold + PROBABLE_MARGIN
                             and (r["lib_range"][1] - r["lib_range"][0]) >= 0.9 * r["lib_frames"]), None)
            if probable:
                row.update(status="probable", source=probable,
                           note="same name, whole clip lines up at a constant speed, but the pose differs a little more than usual")
            else:
                row.update(status="no_skinless_match")
        if row["status"] in ("matched", "probable"):
            if collect:
                entry = next(e for e in entries if e["id"] == row["source"]["id"])
                with tempfile.TemporaryDirectory() as tmp:
                    shutil.copy2(materialize(library, entry, Path(tmp)), collect / out_name)
        else:
            report["redownload"].append({"query": path.stem, "frames": q_meta.get("frames"),
                                         "mirror": row["status"] == "mirrored",
                                         "closest": top[0] if top else None})
            if collect and args.fallback_skinned:
                shutil.copy2(path, collect / out_name)
                row["copied_skinned"] = True
        row["output"] = out_name
        report["clips"].append(row)
        src = row.get("source", {})
        print(f"{row['status']:>18}  {path.stem:<32} -> {src.get('id', '-')}  ({src.get('deg', top[0]['deg'] if top else '-')}°)",
              flush=True)

    print_status = {"matched": "matched", "probable": "probable", "mirrored": "mirrored"}
    if collect and any(r["status"] == "mirrored" for r in report["clips"]):
        print("NOTE: mirrored matches were not collected; download those Without Skin with Mirror ticked.")
    report_path = absolute(args.report) if args.report else TOOLKIT / "reports" / "find_skinless_clips.json"
    save_report(report_path, report)
    counts = {k: sum(r["status"] == k for r in report["clips"]) for k in print_status}
    print(f"FIND_SKINLESS_OK matched={counts['matched']} probable={counts['probable']} mirrored={counts['mirrored']} "
          f"redownload={len(report['redownload'])} report={report_path}")


if __name__ == "__main__":
    main()
