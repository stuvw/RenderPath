import ctypes
from OpenGL import EGL

# ---------------- EGL CONTEXT ----------------

def create_egl_context(width, height):
    display = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)
    major, minor = ctypes.c_int(), ctypes.c_int()
    EGL.eglInitialize(display, major, minor)

    config_attribs = [
        EGL.EGL_SURFACE_TYPE, EGL.EGL_PBUFFER_BIT,
        EGL.EGL_RENDERABLE_TYPE, EGL.EGL_OPENGL_BIT,
        EGL.EGL_RED_SIZE, 8, EGL.EGL_GREEN_SIZE, 8,
        EGL.EGL_BLUE_SIZE, 8, EGL.EGL_ALPHA_SIZE, 8,
        EGL.EGL_NONE
    ]
    config = EGL.EGLConfig()
    num = ctypes.c_int()
    EGL.eglChooseConfig(display, (EGL.EGLint * len(config_attribs))(*config_attribs), ctypes.byref(config), 1, ctypes.byref(num))

    pbuffer_attribs = [EGL.EGL_WIDTH, width, EGL.EGL_HEIGHT, height, EGL.EGL_NONE]
    surface = EGL.eglCreatePbufferSurface(display, config, (EGL.EGLint * len(pbuffer_attribs))(*pbuffer_attribs))
    EGL.eglBindAPI(EGL.EGL_OPENGL_API)

    ctx_attribs = [EGL.EGL_CONTEXT_MAJOR_VERSION, 3, EGL.EGL_CONTEXT_MINOR_VERSION, 3, EGL.EGL_NONE]
    ctx = EGL.eglCreateContext(display, config, EGL.EGL_NO_CONTEXT, (EGL.EGLint * len(ctx_attribs))(*ctx_attribs))
    EGL.eglMakeCurrent(display, surface, surface, ctx)
    return display, surface, ctx