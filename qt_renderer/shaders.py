# ══════════════════════════════════════════════════════════════════════════════
# GLSL Shaders
# ══════════════════════════════════════════════════════════════════════════════

import os

with open(os.path.join("qt_renderer", "shaders", "depth.vert"), "r") as vsdf:
    VERTEX_SHADER_DEPTH = vsdf.read()

with open(os.path.join("qt_renderer", "shaders", "depth.frag"), "r") as fsdf:
    FRAGMENT_SHADER_DEPTH = fsdf.read()

with open(os.path.join("qt_renderer", "shaders", "screen.vert"), "r") as svsf:
    SCREEN_VERTEX_SHADER = svsf.read()

with open(os.path.join("qt_renderer", "shaders", "screen.frag"), "r") as sfsf:
    SCREEN_FRAGMENT_SHADER = sfsf.read()
