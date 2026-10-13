"""One command from Mixamo files to a clean, animation-ready GLB for PixelOver.

  rigged FBX from Mixamo (or an existing master .blend)
    -> post_mixamo              work/<name>_master.blend
    -> batch_import_animations  work/<name>_animated.blend   (clips bound to the rig, root motion in metres)
    -> export_for_pixelover     work/<name>_ready.blend + the GLB
         (audits and repairs clips, weights and textures, makes clips In Place, then verifies the GLB)

Every stage writes a report to reports/<name>_*.json. The build stops at the first stage that fails,
or if the audit finds something only a person can fix (see reports/<name>_audit.json).
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from pipeline_common import absolute, script_args


def stage(name, *arguments):
    print(f"BUILD_STAGE {name}")
    saved = sys.argv
    sys.argv = [name, "--", *[str(a) for a in arguments]]
    try:
        runpy.run_path(str(SCRIPTS / f"{name}.py"), run_name="__main__")
    finally:
        sys.argv = saved


def main():
    args = script_args(
        "Build a PixelOver-ready GLB from a Mixamo-rigged character and a folder of Mixamo clips",
        (("--rigged",), {"required": True, "help": "Mixamo rigged FBX (With Skin, T-pose), or a master .blend"}),
        (("--animations",), {"required": True, "help": "Folder of animation FBX files (Without Skin)"}),
        (("--output",), {"required": True, "help": "GLB to write, e.g. output/Hero.glb"}),
        (("--name",), {"default": "", "help": "Prefix for work files and reports; default: the GLB name"}),
        (("--work-dir",), {"default": str(SCRIPTS.parent / "work")}),
        (("--report-dir",), {"default": str(SCRIPTS.parent / "reports")}),
        (("--target-height",), {"type": float, "default": 0.0, "help": "post_mixamo only; 0 keeps size"}),
        (("--keep-root-motion",), {"action": "store_true", "help": "Do not make clips In Place"}),
        (("--allow-manual",), {"action": "store_true", "help": "Export despite problems that need a person"}),
    )
    rigged, output = absolute(args.rigged), absolute(args.output)
    animations, work = absolute(args.animations), absolute(args.work_dir)
    name = args.name or output.stem
    if not rigged.is_file():
        raise RuntimeError(f"Rigged file not found: {rigged}")
    if not animations.is_dir() or not any(animations.rglob("*.fbx")):
        raise RuntimeError(f"No .fbx clips in {animations}")
    work.mkdir(parents=True, exist_ok=True)
    reports = absolute(args.report_dir)
    report = lambda stage_name: str(reports / f"{name}_{stage_name}.json")

    master = work / f"{name}_master.blend"
    if rigged.suffix.lower() == ".blend":
        master = rigged
    else:
        stage("post_mixamo", "--input", rigged, "--output", master, "--report", report("master"),
              "--target-height", args.target_height)
    animated = work / f"{name}_animated.blend"
    stage("batch_import_animations", "--blend", master, "--animations", animations, "--output", animated,
          "--report", report("animations"))
    export = ["--blend", animated, "--output", output, "--report", report("export"),
              "--audit-report", report("audit"), "--save-blend", work / f"{name}_ready.blend"]
    if args.keep_root_motion:
        export.append("--keep-root-motion")
    if args.allow_manual:
        export.append("--allow-manual")
    stage("export_for_pixelover", *export)
    print(f"BUILD_PIXELOVER_OK output={output} ready_blend={work / f'{name}_ready.blend'}")


if __name__ == "__main__":
    main()
