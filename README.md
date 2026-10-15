# Meshy2PixelOver Pipeline

**Primary source repository:** [9-K9/Meshy2PixelOver-PipeLine](https://github.com/9-K9/Meshy2PixelOver-PipeLine).
All ongoing development and updates belong here. The legacy
`rpg2k3/Meshy2Mixamo-Blender-4.5-Pipeline` repository is archived.

Tools for taking a Meshy (or VRoid) character through
**Meshy → Blender → Mixamo → Blender → PixelOver**, fixing rest-pose mismatches
and lost bones along the way.

## Related repository

The game using characters from this pipeline is
[KatanaKitsune](https://github.com/9-K9/KatanaKitsune).

- Toolkit, scripts, tests and guides: [`Meshy-Blender-Toolkit/`](Meshy-Blender-Toolkit/README.md)
- Start with [`USER_GUIDE.md`](Meshy-Blender-Toolkit/USER_GUIDE.md)

## Mixamo animations download

[Download all Mixamo animations (Mixamo.zip)](https://www.dropbox.com/scl/fi/u10dpk34rfgmscs9hzp5p/Mixamo.zip?rlkey=msu06h5fqinfp92jeg8mizjtu&st=4438hcmh&dl=0)

## Setup

1. Download the portable **Blender 4.5.13 LTS** (Linux x64) from blender.org and
   extract it next to `Meshy-Blender-Toolkit/` so the folder is
   `blender-4.5.13-linux-x64/`. It is git-ignored; the launcher scripts expect it there.
2. Optional: symlink `Meshy-Blender-Toolkit/meshy_blender_toolkit` into
   `~/.config/blender/4.5/scripts/addons/` and enable it in Blender.
3. Verify: `Meshy-Blender-Toolkit/tests/run_pipeline_test.sh`
