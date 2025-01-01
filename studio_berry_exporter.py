import re
import os
import bpy

bl_info = {
    "name": "Studio Berry",
    "category": "Export",
    "description": "Addon to export a berrybush model for easy compatibility with studio_eleven",
    "author": "Tinifan",
    "version": (1, 0, 1),
    "blender": (2, 80, 2),
    "location": "Object Context Menu (Right-Click)",
    "warning": "",
    "doc_url": "",
    "support": 'COMMUNITY',
}

def get_real_name(name):
    if name.count('.') > 0 and len(name) > 3:
        if name[len(name)-4] == '.':
            match = re.search(r"^(.*?)(\.\d+)$", name)
            if match:
                return match.group(1)
    return name

class ConvertBerryToStudioView(bpy.types.Operator):
    bl_idname = "object.convert_berry_to_studio_view"
    bl_label = "Convert Berry to Studio View"
    bl_description = "Exports the current model and animations, and sets up the scene."

    def execute(self, context):
        try:
            # Logic to check if an armature is selected
            armature_name = None
            if context.view_layer.objects.active and context.view_layer.objects.active.type == 'ARMATURE':
                # If an armature is selected, use it
                armature_name = context.view_layer.objects.active.name
            else:
                # If no armature is selected, use the first armature found in the scene
                for obj in bpy.context.scene.objects:
                    if obj.type == 'ARMATURE':
                        armature_name = obj.name
                        break

            if not armature_name:
                self.report({'ERROR'}, "No armature found in the scene")
                return {'CANCELLED'}
                
            base_path = bpy.path.abspath("//")
            dae_path = os.path.join(base_path, "model_export.dae")
            obj_path = os.path.join(base_path, "model_export.obj")
            mtn2_path = os.path.join(base_path, "animation_export.mtn2")

            # Export to DAE (Collada)
            bpy.ops.wm.collada_export(filepath=dae_path)
            
            # Export to OBJ
            bpy.ops.export_scene.obj(filepath=obj_path)
            
            # Export to MTN2
            transformation_checkboxes = [
                {"name": "Location", "enabled": True},
                {"name": "Rotation", "enabled": True},
                {"name": "Scale", "enabled": True}
            ]

            # Call the bpy.ops.export.animation operator for the MTN2 export
            bpy.ops.export.animation(
                filepath=mtn2_path, 
                animation_type="ARMATURE",
                armature_name=armature_name,
                transformation_checkboxes=transformation_checkboxes,
                extension=".mtn2"
            )

            # Get the collection of the selected armature
            armature_obj = bpy.data.objects.get(armature_name)
            if armature_obj:
                armature_collection = armature_obj.users_collection[0]  # Assuming the armature is in a collection
                armature_collection_name = armature_collection.name  # Name of the armature's current collection
            else:
                armature_collection_name = None

            # Create a new collection to import the DAE
            studio_temp_collection = bpy.data.collections.new("Studio Eleven Temp")
            bpy.context.scene.collection.children.link(studio_temp_collection)
            
            # Activate the new collection
            layer_collection = bpy.context.view_layer.layer_collection.children[studio_temp_collection.name]
            bpy.context.view_layer.active_layer_collection = layer_collection

            # Open the DAE file in the new collection
            bpy.ops.wm.collada_import(filepath=dae_path)
            
            for obj in studio_temp_collection.objects:
                if obj.type == 'MESH':
                    # Delete only MESH in this new collection
                    bpy.data.objects.remove(obj, do_unlink=True)
                elif obj.type == 'ARMATURE':
                    # Rename the armature
                    obj.name = f"{armature_name}_studio"

            # Import the OBJ file into the new collection
            bpy.ops.import_scene.obj(filepath=obj_path)

            # Process the MESH in Studio Eleven Temp
            for obj in studio_temp_collection.objects:
                obj_name = get_real_name(obj.name)
                
                if obj.type == 'MESH':
                    original_obj = None
                    
                    if armature_collection_name:
                        original_armature = bpy.data.objects.get(armature_name)
                        if original_armature:
                            for obj_in_collection in armature_collection.objects:
                                obj_in_collection_name = get_real_name(obj_in_collection.name)
                                if obj_in_collection.type == 'MESH' and obj_in_collection_name == obj_name:
                                    original_obj = obj_in_collection
                                    break
                        
                        if original_obj:
                            # Copy materials
                            obj.data.materials.clear()
                            for material_slot in original_obj.material_slots:
                                if material_slot.material:
                                    obj.data.materials.append(material_slot.material)
                            
                            # Rename materials
                            for mat in obj.data.materials:
                                mat.name = f'DefaultLib.{obj.name}'
                            
                            # Transfer the draw priority
                            if hasattr(original_obj.data, 'brres'):
                                if hasattr(obj.data, 'level5_properties'):
                                    obj.data.level5_properties.draw_priority = original_obj.data.brres.drawPrio + 10
                        
                            # Match parents
                            if original_obj.parent:                                
                                if original_obj.parent_type == 'BONE':
                                    # Get the armature
                                    armature = bpy.data.objects[f"{original_obj.parent.name}_studio"]

                                    # Loop through pose bones to find the correct one
                                    selected_pose_bone = None

                                    for pose_bone in armature.pose.bones:
                                        if get_real_name(pose_bone.name) == get_real_name(original_obj.parent_bone):
                                            selected_pose_bone = pose_bone
                                            break

                                    # Check if a matching bone was found
                                    if selected_pose_bone:
                                        # Add a vertex group for this bone
                                        if selected_pose_bone.name not in obj.vertex_groups:
                                            vertex_group = obj.vertex_groups.new(name=selected_pose_bone.name)
                                        else:
                                            vertex_group = obj.vertex_groups[selected_pose_bone.name]
                                        
                                        # Assign all vertices to the group with weight 1
                                        vertex_indices = [v.index for v in obj.data.vertices]
                                        vertex_group.add(vertex_indices, 1.0, 'REPLACE')

                                        # Update parent to point to the armature
                                        obj.parent = armature
                                        obj.parent_type = 'OBJECT'
                                else:
                                    obj.parent = bpy.data.objects[f"{original_obj.parent.name}_studio"]
                                    
                            # Copy vertex groups and their weights
                            if original_obj.vertex_groups:
                                for vg in original_obj.vertex_groups:
                                    group_name = vg.name
                                    # Create the vertex group in the target object if necessary
                                    if group_name not in obj.vertex_groups:
                                        obj.vertex_groups.new(name=group_name)

                                    # Copy the vertex group weights from the original to the target object
                                    for v in original_obj.data.vertices:
                                        for g in v.groups:
                                            if g.group == vg.index:
                                                weight = g.weight
                                                obj.vertex_groups[group_name].add([v.index], weight, 'ADD')

                            # Add an Armature modifier
                            armature = bpy.data.objects[f"{original_obj.parent.name}_studio"]
                            if not any(mod.type == 'ARMATURE' for mod in obj.modifiers):
                                armature_modifier = obj.modifiers.new(name="Armature Modifier", type='ARMATURE')
                                armature_modifier.object = armature
                                armature_modifier.use_vertex_groups = True

            # Delete the base collection if it exists
            if armature_collection_name:
                base_collection = bpy.data.collections.get(armature_collection_name)
                if base_collection:
                    bpy.data.collections.remove(base_collection)

            # Rename Studio Eleven Temp collection to Collection
            studio_temp_collection.name = "Collection"

            # Check if the current mode is not 'OBJECT' and switch to Object Mode
            if bpy.context.object and bpy.context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            # Select all objects in the Studio Eleven Temp collection
            for obj in studio_temp_collection.objects:
                obj.select_set(True)  # Select the object

            # Apply rotation (and possibly other transformations)
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

            # Update the 3D view
            bpy.context.view_layer.update()
            
            # Select the armature in the scene
            armature_obj = bpy.data.objects.get(armature_name + '_studio')
            if armature_obj:
                # Ensure the armature is active and selected
                bpy.context.view_layer.objects.active = armature_obj
                armature_obj.select_set(True)

                # Call the animation import with the bpy.ops.import.level5_animation operator
                bpy.ops.import_level5.animation(filepath=mtn2_path)

                self.report({'INFO'}, "Animation imported successfully!")
            else:
                self.report({'ERROR'}, f"Armature {armature_name + '_studio'} not found in the scene.")
                return {'CANCELLED'}

            self.report({'INFO'}, "Export and setup completed successfully!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            return {'CANCELLED'}

def menu_func(self, context):
    self.layout.operator(ConvertBerryToStudioView.bl_idname, text="Adapt 3D view for Studio Eleven")

def register():
    bpy.utils.register_class(ConvertBerryToStudioView)
    bpy.types.VIEW3D_MT_object_context_menu.append(menu_func)

def unregister():
    bpy.utils.unregister_class(ConvertBerryToStudioView)
    bpy.types.VIEW3D_MT_object_context_menu.remove(menu_func)

if __name__ == "__main__":
    register()