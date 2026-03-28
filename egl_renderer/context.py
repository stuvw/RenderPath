from time import time
import ctypes
import os
os.environ['EGL_PLATFORM'] = 'surfaceless'

from OpenGL import EGL
from OpenGL import GL
from OpenGL.GL import *
from OpenGL.GL import shaders

# ---------------- EGL CONTEXT ----------------

def create_egl_context(width, height):
    print("[INFO]: Creating EGL context...", end='', flush=True)
    start = time()

    display = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)
    if display == EGL.EGL_NO_DISPLAY:
        raise RuntimeError("No EGL display")

    major, minor = ctypes.c_int(), ctypes.c_int()
    if not EGL.eglInitialize(display, major, minor):
        raise RuntimeError("eglInitialize failed")

    config_attribs = [
        EGL.EGL_SURFACE_TYPE, EGL.EGL_PBUFFER_BIT,
        EGL.EGL_RENDERABLE_TYPE, EGL.EGL_OPENGL_BIT,
        EGL.EGL_RED_SIZE, 8,
        EGL.EGL_GREEN_SIZE, 8,
        EGL.EGL_BLUE_SIZE, 8,
        EGL.EGL_ALPHA_SIZE, 8,
        EGL.EGL_NONE
    ]

    config = EGL.EGLConfig()
    num = ctypes.c_int()
    if not EGL.eglChooseConfig(
        display,
        (EGL.EGLint * len(config_attribs))(*config_attribs),
        ctypes.byref(config),
        1,
        ctypes.byref(num),
        ):
        raise RuntimeError("eglChooseConfig failed")

    if num.value == 0:
        raise RuntimeError("No EGL configs found")

    pbuffer_attribs = [
        EGL.EGL_WIDTH, width,
        EGL.EGL_HEIGHT, height,
        EGL.EGL_NONE
    ]
    surface = EGL.eglCreatePbufferSurface(
        display,
        config,
        (EGL.EGLint * len(pbuffer_attribs))(*pbuffer_attribs)
    )

    EGL.eglBindAPI(EGL.EGL_OPENGL_API)


    ctx_attribs = [
        EGL.EGL_CONTEXT_MAJOR_VERSION, 3,
        EGL.EGL_CONTEXT_MINOR_VERSION, 3,
        EGL.EGL_CONTEXT_OPENGL_PROFILE_MASK,
        EGL.EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT,
        EGL.EGL_NONE
    ]

    ctx = EGL.eglCreateContext(
        display,
        config,
        EGL.EGL_NO_CONTEXT,
        (EGL.EGLint * len(ctx_attribs))(*ctx_attribs)
    )
    if ctx == EGL.EGL_NO_CONTEXT:
        raise RuntimeError("eglCreateContext failed")
    if not EGL.eglMakeCurrent(display, surface, surface, ctx):
        raise RuntimeError("eglMakeCurrent failed")

    end = time()
    print(f" Done ({int((end-start)*1000)}ms)")

    print(f"[INFO]: EGL version: {major.value}.{minor.value}")
    print(f"[INFO]: OpenGL version: {GL.glGetString(GL.GL_VERSION).decode()}")
    print(f"[INFO]: Renderer: {GL.glGetString(GL.GL_RENDERER).decode()}")

    return display, surface, ctx