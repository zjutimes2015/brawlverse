"""
批量渲染：文件夹里每个 FBX -> 一个 mp4（用模板的灯光机位）。
用法（不用开 Blender 界面）：
  blender --background brawlverse_template.blend --python batch_render.py -- ./fbx ./reference/mixamo
"""
import bpy
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
FBX_DIR, OUT_DIR = argv[0], argv[1]
os.makedirs(OUT_DIR, exist_ok=True)

# 记住模板里的东西（灯光/相机/地面），导入后只删角色
template_objs = set(bpy.data.objects[:])


def clear_imported():
    for o in list(bpy.data.objects):
        if o not in template_objs and o.name not in ("BV_Cam", "BV_Target", "BV_Floor",
                                                     "BV_Key", "BV_Rim", "BV_Top"):
            bpy.data.objects.remove(o, do_unlink=True)
    # 清旧动作
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)


for fn in sorted(os.listdir(FBX_DIR)):
    if not fn.lower().endswith(".fbx"):
        continue
    clear_imported()
    fbx = os.path.join(FBX_DIR, fn)
    bpy.ops.import_scene.fbx(filepath=fbx)
    # 取导入动作的帧范围
    actions = list(bpy.data.actions)
    if not actions:
        print("SKIP (no action): " + fn)
        continue
    fr = actions[0].frame_range
    sc = bpy.context.scene
    sc.frame_start = int(fr[0])
    sc.frame_end = int(fr[1])
    name = os.path.splitext(fn)[0]
    sc.render.filepath = os.path.join(OUT_DIR, name + ".mp4")
    print("RENDER %s frames %d-%d" % (name, sc.frame_start, sc.frame_end))
    bpy.ops.render.render(animation=True)

print("done -> " + OUT_DIR)
