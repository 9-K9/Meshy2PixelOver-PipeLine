# Troubleshooting

| Symptom | Plain-language cause | What to do |
|---|---|---|
| Twisted limbs | The animation and character use different bone names or different rest poses. It is like measuring with two differently shaped rulers. | Stop. Confirm the master and clips came from Mixamo, inspect the batch report for missing bones, and do not apply an arbitrary animated frame as rest pose. Re-rig the bare mesh in Mixamo if the master still contains Meshy bones. |
| Too big or too small | Centimetres and metres were interpreted differently. | First keep `TARGET_HEIGHT_METRES = 0`. If all clips work but overall size is wrong, rerun `post_mixamo.py` with a measured target such as `1.7`; do not scale only the mesh or only the armature. |
| Floating or sinking | The character origin, root motion, or feet do not meet ground level. | Prepare the bare mesh again so its lowest point is Z=0. Use Mixamo **In Place** for locomotion. In PixelOver, move the whole packed scene, not individual bones. |
| Wrong facing direction | Source forward axes disagree. | Rerun preparation from the original with `ROTATE_Z_DEGREES = 180`. Never fix each exported direction separately. |
| Missing textures | Images were not embedded/copied, or material nodes are too complex for interchange. | Keep textures beside the source; use FBX Binary with embedded media when available; prefer GLB for the final handoff. In Blender, use Principled BSDF with Image Texture nodes and pack resources before export. |
| Animations absent in PixelOver | Actions were not retained/exported, the GLB has no animation chunks, or only one current action was exported. | Read `reports/pixelover_export.json`. Confirm its `animations` list is non-empty. Re-export with Actions mode and one armature. |
| Hair/clothes bones disappeared | Mixamo generated a new humanoid skeleton and ignored VRoid secondary bones. | Use rigid head attachment for simple chunks, or add chains after Mixamo and weight-paint them manually. Do not expect Mixamo to preserve the VRoid spring-bone system. |
| Body deforms but hair stays behind | Hair has no armature modifier or useful weights. | Run rigid attachment for separate hair objects, or add an Armature modifier and paint weights to the new chain. |
| Feet slide | The clip translates differently from the game movement speed. | Download locomotion with **In Place**, then control world movement in the game. PixelOver is rendering the animation, not solving gameplay velocity. |
