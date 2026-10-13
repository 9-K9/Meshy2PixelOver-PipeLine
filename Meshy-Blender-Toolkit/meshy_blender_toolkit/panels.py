import bpy


class MBT_PT_setup(bpy.types.Panel):
    bl_label = "Setup"
    bl_idname = "MBT_PT_setup"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MESHY TOOLKIT"

    def draw(self, context):
        layout = self.layout
        layout.operator("mbt.inspect_scene", icon="VIEWZOOM")
        layout.label(text=context.scene.mbt.last_summary)
        layout.separator()
        layout.operator("mbt.backup_blend", icon="DUPLICATE")


class MBT_PT_reports(bpy.types.Panel):
    bl_label = "Reports"
    bl_idname = "MBT_PT_reports"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MESHY TOOLKIT"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.mbt, "report_path")
        layout.operator("mbt.export_report", icon="FILE_TICK")


CLASSES = (MBT_PT_setup, MBT_PT_reports)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
