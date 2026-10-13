#!/usr/bin/env bash
# End-to-end regression test using the synthetic fixtures. Writes only to a temp folder.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
run() { "$ROOT/run-headless.sh" --python "$ROOT/scripts/$1.py" -- "${@:2}" 2>&1 | tee "$TMP/last.log" | grep -E "_OK|WARNING|Error|Traceback" || true; grep -q "_OK" "$TMP/last.log" || { echo "FAILED: $1"; cat "$TMP/last.log"; exit 1; }; }
F="$ROOT/tests/fixtures"
run prepare_meshy --input "$F/meshy_source.glb" --output "$TMP/prepared.fbx" --report "$TMP/r1.json"
run post_mixamo --input "$F/character.fbx" --output "$TMP/master.blend" --report "$TMP/r2.json"
run post_mixamo --input "$F/character.fbx" --output "$TMP/master_scaled.blend" --report "$TMP/r2b.json" --target-height 1.7
run post_mixamo --input "$F/character.fbx" --output "$TMP/master_rest.blend" --report "$TMP/r2c.json" --apply-current-pose-as-rest
run batch_import_animations --blend "$TMP/master.blend" --animations "$F/anims" --output "$TMP/animated.blend" --report "$TMP/r3.json"
run audit_animations --blend "$TMP/animated.blend" --output "$TMP/audited.blend" --report "$TMP/r3a.json"
# Regression: unbind the clip slots and add centimetre root motion, then let the audit repair it.
cat > "$TMP/break.py" <<'BPY'
import bpy
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
for track in rig.animation_data.nla_tracks:
    for strip in track.strips:
        strip.action.slots[0].name_display = "SomeOtherRig"
        strip.action_slot = None
        bag = strip.action.layers[0].strips[0].channelbags[0]
        height = rig.data.bones["mixamorig:Hips"].head_local.length
        for i in range(3):
            path = 'pose.bones["mixamorig:Hips"].location'
            fc = bag.fcurves.find(path, index=i) or bag.fcurves.new(path, index=i)
            fc.keyframe_points.clear()
            fc.keyframe_points.insert(1, 0.0)
            fc.keyframe_points.insert(12, height * 100 if i == 0 else 0.0)
        strip.action.pop("mbt_root_scale", None)
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath.replace("animated", "broken"))
print("BREAK_OK")
BPY
"$ROOT/run-headless.sh" "$TMP/animated.blend" --python "$TMP/break.py" 2>&1 | grep -q BREAK_OK || { echo "FAILED: break"; exit 1; }
run audit_animations --blend "$TMP/broken.blend" --output "$TMP/repaired.blend" --report "$TMP/r3b.json"
run add_extra_bones --blend "$TMP/animated.blend" --output "$TMP/extra.blend" --mode chain --report "$TMP/r4.json"
run export_for_pixelover --blend "$TMP/extra.blend" --output "$TMP/out.glb" --report "$TMP/r5.json"
run build_pixelover_glb --rigged "$F/character.fbx" --animations "$F/anims" --output "$TMP/built.glb" --name built --work-dir "$TMP/work" --report-dir "$TMP"
# Negative check: a texture that cannot be found anywhere must stop the export.
cat > "$TMP/lose.py" <<'BPY'
import bpy
for image in bpy.data.images:
    if image.packed_file:
        image.unpack(method="REMOVE")
    image.filepath = "/nonexistent/lost_texture.png"
    image.name = "lost_texture"
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath.replace("animated", "lost"))
print("LOSE_OK")
BPY
"$ROOT/run-headless.sh" "$TMP/animated.blend" --python "$TMP/lose.py" 2>&1 | grep -q LOSE_OK || { echo "FAILED: lose"; exit 1; }
if "$ROOT/run-headless.sh" --python "$ROOT/scripts/export_for_pixelover.py" -- --blend "$TMP/lost.blend" --output "$TMP/lost.glb" --report "$TMP/r6.json" --audit-report "$TMP/r6a.json" 2>&1 | grep -q EXPORT_PIXELOVER_OK; then
    echo "FAILED: export accepted a lost texture"; exit 1
fi
echo "BLOCKED_LOST_TEXTURE_OK"
python3 - "$TMP" <<'PY'
import json, sys
t = sys.argv[1]
r = json.load(open(f"{t}/r5.json"))
names = sorted(r["glb"]["animations"])
assert names == ["Idle", "Walk"], names
assert all(c["status"] == "ok" for c in json.load(open(f"{t}/r3.json"))["clips"])
glb = r["glb"]
assert glb["images"] >= 1 and not glb["external_images"], glb
assert all(a["channels"] and a["seconds"] > 0 for a in glb["animation_details"]), glb
assert r["in_place"]
assert "missing texture" in {m["what"] for m in json.load(open(f"{t}/r6a.json"))["export_blockers"]}
audit = json.load(open(f"{t}/r3a.json"))
assert not audit["auto_fixed"], audit["auto_fixed"]  # batch import already did everything
# The fixture is a cube skinned to one bone, so it legitimately has far weights.
assert {m["what"] for m in audit["needs_manual"]} <= {"weights far from their bone"}, audit["needs_manual"]
repaired = json.load(open(f"{t}/r3b.json"))
fixed = {f["what"] for f in repaired["auto_fixed"]}
assert "assigned action slot" in fixed, fixed
assert "root motion converted cm -> m" in fixed, fixed
print("PIPELINE_TEST_OK", names, "skipped:", r["skipped_actions"])
PY
