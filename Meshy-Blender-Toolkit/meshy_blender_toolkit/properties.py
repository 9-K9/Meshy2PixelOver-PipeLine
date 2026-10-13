import bpy


class MBTProperties(bpy.types.PropertyGroup):
    report_path: bpy.props.StringProperty(
        name="Report",
        subtype="FILE_PATH",
        default="//reports/scene_report.json",
    )
    last_summary: bpy.props.StringProperty(name="Last result", default="Not inspected")


CLASSES = (MBTProperties,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mbt = bpy.props.PointerProperty(type=MBTProperties)


def unregister():
    del bpy.types.Scene.mbt
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
