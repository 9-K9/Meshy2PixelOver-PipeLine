import importlib.util
import pathlib
import sys

import bpy

root = pathlib.Path(__file__).resolve().parents[1]
package = root / "meshy_blender_toolkit"
spec = importlib.util.spec_from_file_location(
    "meshy_blender_toolkit", package / "__init__.py", submodule_search_locations=[str(package)]
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.register()

assert hasattr(bpy.types.Scene, "mbt")
assert hasattr(bpy.types, "MBT_OT_inspect_scene")
assert bpy.ops.mbt.inspect_scene() == {"FINISHED"}
print("MBT_SMOKE_TEST_OK", bpy.context.scene.mbt.last_summary)

module.unregister()
