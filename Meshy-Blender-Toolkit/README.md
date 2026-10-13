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
6. Put Mixamo animation-only (Without Skin) FBX files in `assets/animations/`.
   `scripts/find_skinless_clips.py` finds the skinless copy of any clip in the local
   Mixamo library (loose files and pack zips, matched by motion); see USER_GUIDE Stage 4.
7. Keep editable `.blend` masters in `work/` and PixelOver GLBs in `output/`.
8. Build the GLB in one step: `TASK = "build_pixelover_glb"` (or
   `scripts/build_pixelover_glb.py --rigged ... --animations ... --output output/Name.glb`).
   It runs post_mixamo → batch_import_animations → audit → export → GLB verification.

The sidebar add-on provides scene inspection, JSON reporting, timestamped
`.blend` backups, **Audit & Fix Animations** (undoable; see USER_GUIDE Stage 4b)
and **Export PixelOver GLB** (audit + export + verification on a background copy).
The production scripts are in `scripts/`; use `run_from_scripting.py` as the
beginner launcher. `scripts/audit_animations.py` repairs clip binding, root-motion
units, bone prefixes, weight normalisation and lost/unpacked textures, and reports what needs a human
(unweighted, far-weighted and stretching vertices) as `MBT_*` vertex groups.

## Headless verification

```bash
./run-headless.sh --python tests/smoke_test.py
```

The end-to-end synthetic test was run with a skinned test character and two
Mixamo-style FBX clips. It exercised all five scripts and structurally reopened
the final GLB.

Full pipeline regression test (all six scripts on the synthetic fixtures, plus a
broken-slot / centimetre root-motion repair check):

```bash
tests/run_pipeline_test.sh
```

## Folder policy

Originals in `assets/source/` are never modified. Work on `.blend` copies in
`work/`. Export final files to `output/`.

Everything here is tracked in git, including the Crimson Kitsune test character
(source GLB, Mixamo rig, work `.blend`s, the PixelOver GLB and their reports), except
the Mixamo clip library in `assets/animations/Mixamo/` (about 1 GB) and Blender's
`.blend1` autosave copies. The library is archived on Dropbox and is restored to
that folder exactly as it is; `assets/animations/Mixamo_Catalog.md` lists every clip in it. Copy a clip you need into a small folder such as
`work/anim_test/` and commit that instead.
