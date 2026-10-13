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
run add_extra_bones --blend "$TMP/animated.blend" --output "$TMP/extra.blend" --mode chain --report "$TMP/r4.json"
run export_for_pixelover --blend "$TMP/extra.blend" --output "$TMP/out.glb" --report "$TMP/r5.json"
python3 - "$TMP" <<'PY'
import json, sys
t = sys.argv[1]
r = json.load(open(f"{t}/r5.json"))
names = sorted(r["glb"]["animations"])
assert names == ["Idle", "Walk"], names
assert all(c["status"] == "ok" for c in json.load(open(f"{t}/r3.json"))["clips"])
print("PIPELINE_TEST_OK", names, "skipped:", r["skipped_actions"])
PY
