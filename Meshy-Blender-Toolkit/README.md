# Meshy Blender Toolkit (MBT)

Local Blender 4.5 pipeline for preparing Meshy characters for Mixamo, auditing
rigged characters, collecting Mixamo actions, and exporting animation-ready GLB
files for PixelOver.

Start with [USER_GUIDE.md](USER_GUIDE.md). Common failures are listed in
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Installed and verified tooling

- Blender 4.5.13 LTS, portable Linux build in the parent folder. Blender 4.5.14
  is the newest 4.5 patch as of 2026-10-13; this project remains pinned to the
  locally tested 4.5.13 build until it is deliberately upgraded and retested.
- Meshy Blender Toolkit add-on, enabled in Blender's user preferences.
- Official **VRM format** Blender extension, installed for VRoid imports.
- Adobe Mixamo web service (free with an Adobe ID; no Creative Cloud
  subscription required).
- PixelOver for final 3D-to-sprite rendering. PixelOver's demo can edit and save
  projects, but image/GIF/sprite-sheet/Aseprite export requires its paid version.

No Auto-Rig Pro-style paid Blender add-on is required for the basic pipeline.

## Pipeline

1. Put untouched Meshy exports in `assets/source/`.
2. Open Blender with `launch-blender.sh`.
3. In the 3D Viewport press **N** and open **MESHY TOOLKIT**.
4. Use **Inspect Scene**, then **Export Report**.
5. Prepare a clean copy for Mixamo and put the returned rig in `assets/rigged/`.
6. Put Mixamo animation-only FBX files in `assets/animations/`.
7. Keep editable `.blend` masters in `work/` and PixelOver GLBs in `output/`.

The sidebar add-on currently implements the safe Phase 1 foundation: scene
inspection, JSON reporting, and timestamped `.blend` backups. The production
scripts are in `scripts/`; use `run_from_scripting.py` as the beginner launcher.
Automated repair operators are deliberately not enabled until their validation
and undo behavior are implemented.

## Headless verification

```bash
./run-headless.sh --python tests/smoke_test.py
```

The end-to-end synthetic test was run with a skinned test character and two
Mixamo-style FBX clips. It exercised all five scripts and structurally reopened
the final GLB.

Full pipeline regression test (all five scripts on the synthetic fixtures):

```bash
tests/run_pipeline_test.sh
```

## Folder policy

Originals in `assets/source/` are never modified. Work on `.blend` copies in
`work/`. Export final files to `output/`.
