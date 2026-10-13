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


class MBT_PT_animation(bpy.types.Panel):
    bl_label = "Animation Audit"
    bl_idname = "MBT_PT_animation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MESHY TOOLKIT"

    def draw(self, context):
        layout = self.layout
        layout.operator("mbt.audit_animations", icon="CHECKMARK")
        op = layout.operator("mbt.audit_animations", text="Audit + Make In Place", icon="ANCHOR_CENTER")
        op.in_place = True
        op = layout.operator("mbt.audit_animations", text="Report Only", icon="TEXT")
        op.report_only = True
        layout.label(text=context.scene.mbt.audit_summary)
        layout.prop(context.scene.mbt, "audit_report_path")


class MBT_PT_pixelover(bpy.types.Panel):
    bl_label = "PixelOver Export"
    bl_idname = "MBT_PT_pixelover"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MESHY TOOLKIT"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.mbt, "glb_path")
        layout.prop(context.scene.mbt, "glb_in_place")
        layout.operator("mbt.export_pixelover", icon="EXPORT")
        layout.label(text=context.scene.mbt.export_summary)


CLASSES = (MBT_PT_setup, MBT_PT_reports, MBT_PT_animation, MBT_PT_pixelover)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
