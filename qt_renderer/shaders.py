# ══════════════════════════════════════════════════════════════════════════════
# GLSL Shaders
# ══════════════════════════════════════════════════════════════════════════════

import os

with open(os.path.join("qt_renderer", "shaders", "vertex_shader_depth.glsl"), "r") as vsdf:
    VERTEX_SHADER_DEPTH = vsdf.read()

with open(os.path.join("qt_renderer", "shaders", "fragment_shader_depth.glsl"), "r") as fsdf:
    FRAGMENT_SHADER_DEPTH = fsdf.read()

with open(os.path.join("qt_renderer", "shaders", "screen_vertex_shader.glsl"), "r") as svsf:
    SCREEN_VERTEX_SHADER = svsf.read()

with open(os.path.join("qt_renderer", "shaders", "screen_fragment_shader.glsl"), "r") as sfsf:
    SCREEN_FRAGMENT_SHADER = sfsf.read()
