"""Beginner launcher: edit only this block, then click Run Script in Blender."""

TASK = "prepare_meshy"  # prepare_meshy, post_mixamo, batch_import_animations, add_extra_bones, export_for_pixelover

# Paths may be absolute or relative to this toolkit folder.
INPUT = "assets/source/character.glb"
OUTPUT = "work/character_for_mixamo.fbx"
ANIMATIONS_FOLDER = "assets/animations"
MODE = "rigid"             # add_extra_bones only: rigid or chain
OBJECT_NAMES = []           # example: ["Hair", "Jacket"]
ROTATE_Z_DEGREES = 0        # use 180 only if the character faces backward
TARGET_HEIGHT_METRES = 0.0  # 0 keeps imported size

# Do not edit below this line.
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
scripts = root / "scripts"
INPUT, OUTPUT, ANIMATIONS_FOLDER = (
    str(p if (p := Path(v).expanduser()).is_absolute() else root / p)
    for v in (INPUT, OUTPUT, ANIMATIONS_FOLDER)
)
commands = {
    "prepare_meshy": ["--input", INPUT, "--output", OUTPUT, "--rotate-z", str(ROTATE_Z_DEGREES)],
    "post_mixamo": ["--input", INPUT, "--output", OUTPUT, "--target-height", str(TARGET_HEIGHT_METRES)],
    "batch_import_animations": ["--blend", INPUT, "--animations", ANIMATIONS_FOLDER, "--output", OUTPUT],
    "add_extra_bones": ["--blend", INPUT, "--output", OUTPUT, "--mode", MODE, "--objects", *OBJECT_NAMES],
    "export_for_pixelover": ["--blend", INPUT, "--output", OUTPUT],
}
if TASK not in commands:
    raise ValueError(f"Unknown TASK: {TASK}")
sys.argv = [TASK, "--", *commands[TASK]]
runpy.run_path(str(scripts / f"{TASK}.py"), run_name="__main__")
