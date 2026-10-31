"""
BRAWLVERSE Blender 渲染模板一键生成。
用法：Blender -> Scripting 面板 -> 打开本文件 -> Run Script -> 保存为 brawlverse_template.blend
生成：黑场 + 拳台地面 + 主光 + 冷色轮廓光 + 转播机位 + 720p/24fps/H.264
"""
import bpy
import math

# ---- 清场 ----
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# ---- 世界：纯黑 ----
world = bpy.data.worlds.new("BV_World")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.01, 0.01, 0.012, 1)
bpy.context.scene.world = world

# ---- 地面：暗色拳台 ----
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "BV_Floor"
mat = bpy.data.materials.new("BV_FloorMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.03, 0.03, 0.035, 1)
bsdf.inputs["Roughness"].default_value = 0.85
floor.data.materials.append(mat)

# ---- 相机：3/4 转播机位 ----
bpy.ops.object.camera_add(location=(4.2, -4.8, 1.7))
cam = bpy.context.active_object
cam.name = "BV_Cam"
bpy.ops.object.empty_add(location=(0, 0, 1.0))
tgt = bpy.context.active_object
tgt.name = "BV_Target"
con = cam.constraints.new(type='TRACK_TO')
con.target = tgt
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'
cam.data.lens = 50
bpy.context.scene.camera = cam

# ---- 灯光 ----
# 主光：暖色，右前上
bpy.ops.object.light_add(type='AREA', location=(3, -3, 4))
key = bpy.context.active_object
key.name = "BV_Key"
key.data.energy = 1200
key.data.color = (1.0, 0.92, 0.82)
key.data.size = 3
# 轮廓光：冷色，左后（拳击转播感的关键）
bpy.ops.object.light_add(type='SPOT', location=(-3.5, 3.5, 3))
rim = bpy.context.active_object
rim.name = "BV_Rim"
rim.data.energy = 2500
rim.data.color = (0.55, 0.75, 1.0)
rim.data.spot_size = math.radians(60)
con2 = rim.constraints.new(type='TRACK_TO')
con2.target = tgt
con2.track_axis = 'TRACK_NEGATIVE_Z'
con2.up_axis = 'UP_Y'
# 顶光：弱，压住头顶
bpy.ops.object.light_add(type='AREA', location=(0, 0, 5))
top = bpy.context.active_object
top.name = "BV_Top"
top.data.energy = 300
top.data.color = (0.9, 0.95, 1.0)

# ---- 渲染设置：720p / 24fps / H.264 ----
s = bpy.context.scene
s.render.resolution_x = 1280
s.render.resolution_y = 720
s.render.resolution_percentage = 100
s.render.film_transparent = False
s.render.image_settings.file_format = 'FFMPEG'
s.render.ffmpeg.format = 'MPEG4'
s.render.ffmpeg.codec = 'H264'
s.render.ffmpeg.constant_rate_factor = 'MEDIUM'
s.render.ffmpeg.ffmpeg_preset = 'GOOD'
s.render.ffmpeg.video_bitrate = 6000
s.render.ffmpeg.audio_codec = 'AAC'
s.render.fps = 24
s.view_settings.view_transform = 'Filmic'
s.view_settings.look = 'Medium Contrast'

print("BRAWLVERSE 模板就绪：File -> Save As -> brawlverse_template.blend")
