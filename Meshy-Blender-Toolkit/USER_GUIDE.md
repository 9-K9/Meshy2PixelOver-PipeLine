# Beginner guide: Meshy → Mixamo → Blender → PixelOver

Target: **Blender 4.5.13 LTS**. The supplied scripts were executed against that
exact installation on this computer.

## Four words to know

- **Mesh:** the visible surface, like the character's rubber outer shell.
- **Armature / rig:** the invisible skeleton inside the mesh.
- **Skin weights:** numbers telling each vertex which bone should move it.
- **Rest pose:** the skeleton's neutral reference pose. Animations are measured
  from it, so mismatched rest poses cause twisted limbs.
- **Action:** Blender's container for one animation clip, such as `Walk`.

## How to run a script from Blender

1. Open **Blender 4.5 — Meshy Toolkit** from the application menu.
2. Click the **Scripting** workspace at the top.
3. In the Text Editor click **Open**.
4. Open `run_from_scripting.py` from this toolkit folder.
5. Edit only `TASK`, `INPUT`, `OUTPUT`, and the other values above the
   `Do not edit` line. Keep quotation marks around paths.
6. Click the triangular **Run Script** button.
7. Click **Window → Toggle System Console** if available, or open the Scripting
   workspace's Console panel, to read warnings and the final `..._OK` line.

Always write to a new output filename. Never overwrite the original download.

## Stage 1 — Prepare the bare Meshy mesh

1. Copy the untouched Meshy GLB/FBX into `assets/source/`.
2. Set `TASK = "prepare_meshy"`.
3. Set `INPUT` to the Meshy file and `OUTPUT` to a new `.fbx` in `work/`.
4. Leave `ROTATE_Z_DEGREES = 0`. Run the script.
5. Import or open the result and inspect it from the front and side.
6. Confirm: upright, feet on the ground, arms clear of the torso, legs separated,
   and the face points toward Blender **−Y** (the front view, numpad 1). If it faces backward, rerun from the
   original with `ROTATE_Z_DEGREES = 180`.

The script removes armatures, armature modifiers, and vertex groups; centers and
grounds the mesh; applies rotation and scale; merges only nearly identical
vertices; fixes normals; and embeds/copies textures into the FBX where Blender's
FBX support permits it. It does **not** guess or manufacture a T-pose.

## Stage 2 — Auto-rig in Mixamo

The current Adobe workflow accepts FBX, OBJ, or ZIP custom characters. Use FBX.

1. Sign in at Mixamo and click **Upload Character**.
2. Upload the prepared FBX.
3. If the preview faces backward, cancel and correct the Blender rotation first.
4. Place the chin, wrist, elbow, knee, and groin markers exactly where Mixamo asks.
5. Choose fingers only when the mesh has usable separated fingers.
6. Finish auto-rigging, select a neutral **T-Pose**, and inspect elbows, knees,
   shoulders, hair, and clothing.
7. Download the master character with these settings when shown:
   - Format: **FBX Binary**
   - Skin: **With Skin**
   - Frames per second: **30**
   - Keyframe Reduction: **None**
8. For each reusable animation:
   - Format: **FBX Binary**
   - Skin: **Without Skin**
   - Frames per second: **30**
   - Keyframe Reduction: **None**
   - **In Place: On** for walking/running intended to stay centered

Mixamo's exact download controls are service UI, not a stable file-format
standard, so labels may move. The important invariant is one **With Skin** master
and animation-only downloads made from the same Mixamo skeleton.

## Shortcut — Mixamo files to PixelOver GLB in one step

After Stage 2 you can skip Stages 3, 4, 4b and 6:

1. Set `TASK = "build_pixelover_glb"`.
2. `INPUT` = the rigged **With Skin** FBX from Mixamo (in `assets/rigged/`).
3. `ANIMATIONS_FOLDER` = a folder holding only the clips you want in the GLB.
4. `OUTPUT` = `output/<Name>.glb`.
5. Run it. It ends with `BUILD_PIXELOVER_OK`.

Headless: `./run-headless.sh --python scripts/build_pixelover_glb.py -- --rigged
assets/rigged/Hero.fbx --animations assets/animations/Hero --output output/Hero.glb`

It writes `work/<Name>_master.blend`, `_animated.blend` and `_ready.blend` (the
exact scene that was exported, for touch-ups) plus `reports/<Name>_*.json`. It stops
with a clear message if something needs your hands (see Stage 4b). Use Stage 5
(extra hair/cloth bones) on `_ready.blend`, then re-export with Stage 6.

## Stage 3 — Create the Blender master

1. Set `TASK = "post_mixamo"`.
2. `INPUT` is the Mixamo **With Skin** FBX.
3. `OUTPUT` is a new `.blend` in `work/`, for example `Hero_master.blend`.
4. Keep `TARGET_HEIGHT_METRES = 0.0` for the first test.
5. Run the script and open the resulting `.blend`.
6. Check that the Outliner contains one armature and that hair, skin, and clothes
   still have separate material slots.

Do not apply a visible pose as the rest pose merely because an animation looks
wrong. That changes the skeleton's ruler. The command-line-only
`--apply-current-pose-as-rest` switch is intentionally opt-in; when used it bakes
the visible pose into the meshes first, then makes it the new rest pose.

`--target-height` scales the character without applying the scale, so Mixamo clip
units stay compatible. All JSON reports are written to this toolkit's `reports/`
folder regardless of where Blender was launched.

## Stage 4 — Add Mixamo animations

**Always use Without Skin clips.** A With Skin download carries a whole extra
character (~12 MB) and is only accepted as a last resort. The local library
`assets/animations/Mixamo/` (archived on Dropbox; restore it to that exact folder,
unchanged) already holds ~2,500 skinless clips, loose and inside
`Animation_Packs_ZIP/*.zip`. To find the skinless copy of clips you have:

1. Set `TASK = "find_skinless_clips"`, `INPUT` = the clip or folder you have,
   `OUTPUT` = a new folder such as `work/my_clips`.
2. Optional: `CLIP_NAMES = "assets/animations/My_clip_names.tsv"`, lines of
   `Mixamo name<TAB>game name`, to name the collected files (and so the clips).
3. Run it. Clips are matched **by motion**, not name, so numbered variants such as
   `Great Sword Slash (2)` find the right pack file even when the names disagree.
   The first run fingerprints the library (~2 min, cached in `cache/`).
4. Read `reports/find_skinless_clips.json`. `matched` and `probable` were copied
   skinless. Clips under `redownload` exist in no skinless form: they were copied
   With Skin so the build still works, but re-download them from Mixamo
   **Without Skin** (and with **Mirror** ticked when the status is `mirrored`),
   add them to the library, and run again.

`--catalog assets/animations/Mixamo_Catalog.md` writes the full list of library
clip names, grouped by folder and pack.


1. Put only the animation-only FBX files in `assets/animations/`.
2. Set `TASK = "batch_import_animations"`.
3. `INPUT` is the master `.blend`; `ANIMATIONS_FOLDER` is that folder.
4. `OUTPUT` is a new file such as `Hero_animated.blend`.
5. Run it. Each filename becomes an Action name. A clip using `mixamorig1:`-style
   bone names is automatically renamed to match the master.
6. Read the JSON report in `reports/`. A `bone_mismatch` means the clip names bones
   absent from the master skeleton; do not export until that is resolved.

The import also does two things Mixamo files need on Blender 4.4+:

- **Binds each clip to your rig.** Every clip carries an "action slot" named after
  the temporary rig it was imported on. Left alone, the clip plays on nothing and
  the character stays in T-pose. The slot is renamed to your rig and set on the
  clip's NLA strip, so picking the clip in the Action editor just works.
- **Converts root motion to metres.** Mixamo hips movement is in centimetres;
  on a metre-sized master it would fling the character tens of metres away. The
  factor used is in the report as `root_motion_scale` (about `0.009`).

## Stage 4b — Audit & fix the animations

Run this after every animation import, and again after any weight painting.

**In Blender:** press **N** → **MESHY TOOLKIT** → **Animation Audit** →
**Audit & Fix Animations**. Use **Audit + Make In Place** to strip walking travel,
or **Report Only** to change nothing. Ctrl+Z undoes it. The result line shows
how many things were fixed and how many need you; the full list is in
`reports/animation_audit.json` and in the system console.

**Or from the launcher:** `TASK = "audit_animations"`, `INPUT` = the animated
`.blend`, `OUTPUT` = a new name such as `Hero_audited.blend`. Set
`IN_PLACE = True` to strip travel. The input file is never overwritten.

The audit also runs automatically inside every PixelOver export (Stage 6), and its
texture repair runs inside `post_mixamo` (Stage 3).

Fixed automatically:

| Problem | Fix |
|---|---|
| Clip not bound to the rig (T-pose) | slot renamed and assigned on the NLA strip |
| Clip has no NLA track | track created (muted, so clips don't stack) |
| `mixamorig1:` vs `mixamorig:` bone names | renamed to match the rig |
| Hips root motion in centimetres | scaled to metres |
| Clip not tagged for export | tagged |
| Weights that don't add up to 1 | normalised |
| An active action overriding every clip | cleared, kept as `mbt_leftover`, never exported |
| Root travel (only with In Place) | horizontal hips motion removed, hips centred |
| Texture not packed | packed into the `.blend` |
| Texture linked to a path that no longer exists (e.g. another PC) | found by name in `assets/` (loose image or inside the source `.glb`), copied to `work/textures/` and packed |
| Normal map read as colour | set to Non-Color |

Reported for you to fix (the vertices are put into `MBT_*` vertex groups; in Edit
Mode open **Object Data → Vertex Groups**, pick the group, click **Select**):

| Report | Vertex group | What to do |
|---|---|---|
| Unweighted vertices | `MBT_Unweighted` | Weight Paint them to the nearest bone; they stay frozen while the body moves |
| Weights far from their bone | `MBT_FarWeights` | Usually hair or cloth riding a body bone. Repaint to the closer bone or add bones (Stage 5) |
| Mesh stretches during clip | `MBT_Stretch` | The report lists the bone and the worst frame. Scrub to it and smooth the weights there. Some stretch at armpits and hips is normal |
| Clip animates bones the rig lacks | — | Re-download the clip, or rename the bones |
| Clip travels (not In Place) | — | Re-download with **In Place** or use **Audit + Make In Place** |
| More than 4 bone influences | — | Info only; the exporter keeps the strongest 4 |
| Missing texture | — | Put the original image (same name) or the Meshy `.glb` into `assets/`, or relink it in the Image Texture node |

Rows marked missing texture, unweighted vertices, bones the rig lacks, or no skinned
mesh **block the PixelOver export**; the rest are warnings.

The `MBT_*` groups are rebuilt on every audit and are not bones, so they do not
affect deformation or export.

## Stage 5 — Optional VRoid hair or clothes

Mixamo replaces the skeleton, so VRoid spring/hair bones do not survive that
round-trip automatically.

Simplest method—rigid hair chunks:

1. Keep hair strands as separate mesh objects.
2. Set `TASK = "add_extra_bones"`, `MODE = "rigid"` and list their Blender object
   names in `OBJECT_NAMES`, for example `["Hair_Back", "Hair_Tail"]`.
3. The script weights every vertex in each named object to `mixamorig:Head`.
   It follows the head without secondary swaying.

Advanced method—bone chain:

1. Set `MODE = "chain"` and leave `OBJECT_NAMES = []`.
2. Run the script to add a short chain under the head.
3. You must manually Weight Paint the relevant hair vertices to the new bones.
   The script cannot safely infer which hair vertices belong to which segment.

## Stage 6 — Export for PixelOver

**In Blender:** **MESHY TOOLKIT → PixelOver Export**, set **GLB** (default
`//output/character.glb`, next to the `.blend`), keep **In Place** ticked for
sprites, click **Export PixelOver GLB**. It works on a copy in a background
Blender, so your open scene is not changed. A `<name>_ready.blend` is saved beside
the GLB.

**Or from the launcher:**

1. Set `TASK = "export_for_pixelover"`.
2. `INPUT` is the animated `.blend`; `OUTPUT` ends in `.glb` inside `output/`.
3. Run it. A successful export ends with `EXPORT_PIXELOVER_OK`.

Every export first runs the Stage 4b audit (all its auto-fixes, plus In Place
unless `IN_PLACE = False` / `--keep-root-motion`). If the audit finds a problem
that would break the GLB — a texture that can't be found, unweighted vertices, a
clip for another skeleton, no skinned mesh — the export stops and lists it. Fix it
and export again, or set `ALLOW_MANUAL = True` / `--allow-manual` to export anyway.
Stretching and far weights are only warnings: judge them by eye.

Only clips tagged by the import or audit are exported (leftover pose clips are
skipped; use `--all-actions` to include everything).

After writing, the GLB is read back and must contain one skin, a mesh, a material,
**embedded** textures (no external files), and at least one animation with real
keyframes, or the export fails. The report (`reports/pixelover_export.json`) lists
each animation's length. The look of each pose still needs a check in PixelOver.

The exporter uses one armature, skinning, materials, Actions as separate glTF
animations, one-frame sampling, rest-pose joints, four weight influences, and
animation starts shifted to frame zero.

Equivalent Blender 4.5 UI settings are:

1. **File → Export → glTF 2.0**.
2. Format: **glTF Binary (.glb)**.
3. Include: **Selected Objects** if only the character is selected.
4. Data: Materials and Skinning enabled; Bone Influences = 4.
5. Animation: enabled; Mode = **Actions**; Sampling Rate = **1**; Always Sample
   Animations enabled; Reset Pose Bones enabled; All Armature Actions enabled.
6. Use Rest Position Armature enabled. Apply Modifiers is left off because it can
   prevent shape-key export.

## Stage 7 — PixelOver

1. Open PixelOver and choose **File → Open…**, then select the `.glb`.
2. It should appear as a packed **3D Scene**, not as a single Mesh.
3. Select the imported scene. Open the **Animations** tree and click the eye beside
   `Idle`, `Walk`, or another imported animation.
4. Switch to **Pose** mode to expose the Animation panel and press Play.
5. To save a reusable animation, open the three-dot menu beside its name and choose
   **Save**. PixelOver writes a `.poanimation` file.
6. To reuse one, open the `.poanimation`. In **Import animations**, select the clips;
   use the right-hand track list to rebind each track to the matching object/bone.

For identical sprite cropping:

1. Build one `.pixelover` template and duplicate it per character.
2. Select **Canvas** and set one fixed Size for the whole project.
3. Under **Exported Area**, turn off Auto and set one fixed blue rectangle.
4. Use an **Orthographic** camera, then keep the same camera angle, layer transform,
   model scale, palette, FPS, lighting, and shader settings.
5. Choose **Project → Export**, use that fixed Canvas area, and enable 3D
   **Auto rotation** for eight directions.
6. Do not recalculate the exported area per animation; that causes visible jitter.

## Quick validation test

Use one simple humanoid and only two clips before processing your library:

1. Prepare one Meshy character with `prepare_meshy.py`.
2. Rig it once in Mixamo and download the T-pose master **With Skin**.
3. Download `Idle` and an in-place `Walking` clip **Without Skin**, both at 30 FPS.
4. Run `post_mixamo.py`, then `batch_import_animations.py`, then `audit_animations.py`.
5. In Blender, play both Actions and inspect shoulders, knees, hands, feet, scale,
   and facing direction.
6. Export the GLB and open it in PixelOver.
7. Confirm both names appear and play, then export one 8-direction sprite sheet.
8. Only after this passes should you batch the rest of the animation library.
