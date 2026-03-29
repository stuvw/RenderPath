# ---------------- SHADERS ----------------

import os

with open(os.path.join("egl_renderer_vr", "shaders", "vertex_shader_depth.glsl"), "r") as vsdf:
    VERTEX_SHADER_DEPTH = vsdf.read()

with open(os.path.join("egl_renderer_vr", "shaders", "fragment_shader_depth.glsl"), "r") as fsdf:
    FRAGMENT_SHADER_DEPTH = fsdf.read()

with open(os.path.join("egl_renderer_vr", "shaders", "equirect_fragment_shader.glsl"), "r") as efsf:
    EQUIRECT_FRAGMENT_SHADER = efsf.read()

with open(os.path.join("egl_renderer_vr", "shaders", "domemaster_fragment_shader.glsl"), "r") as dfsf:
    DOMEMASTER_FRAGMENT_SHADER = dfsf.read()

with open(os.path.join("egl_renderer_vr", "shaders", "screen_vertex_shader.glsl"), "r") as svsf:
    SCREEN_VERTEX_SHADER = svsf.read()
