import bpy


class MBTProperties(bpy.types.PropertyGroup):
    report_path: bpy.props.StringProperty(
        name="Report",
        subtype="FILE_PATH",
        default="//reports/scene_report.json",
    )
    last_summary: bpy.props.StringProperty(name="Last result", default="Not inspected")
    audit_report_path: bpy.props.StringProperty(
        name="Audit report",
        subtype="FILE_PATH",
        default="//reports/animation_audit.json",
    )
    audit_summary: bpy.props.StringProperty(name="Audit result", default="Not audited")
    glb_path: bpy.props.StringProperty(
        name="GLB",
        subtype="FILE_PATH",
        default="//output/character.glb",
        description="Where Export PixelOver GLB writes; // is the folder of this .blend",
    )
    glb_in_place: bpy.props.BoolProperty(name="In Place", default=True,
                                         description="Remove root travel so sprites stay centred")
    export_summary: bpy.props.StringProperty(name="Export result", default="Not exported")


CLASSES = (MBTProperties,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mbt = bpy.props.PointerProperty(type=MBTProperties)


def unregister():
    del bpy.types.Scene.mbt
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
