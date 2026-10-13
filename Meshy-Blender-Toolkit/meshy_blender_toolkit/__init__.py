bl_info = {
    "name": "Meshy Blender Toolkit",
    "author": "Emanzi + Codex",
    "version": (0, 1, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > MESHY TOOLKIT",
    "description": "Prepare, inspect, and report on Meshy/Mixamo character assets",
    "category": "3D View",
}

from . import operators, panels, properties


def register():
    properties.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    properties.unregister()
