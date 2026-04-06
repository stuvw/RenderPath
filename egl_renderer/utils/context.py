import sys
import ctypes
from time import time
import os
os.environ['EGL_PLATFORM'] = 'surfaceless'
os.environ['PYOPENGL_PLATFORM'] = 'egl'

from OpenGL import EGL
from OpenGL import GL

def create_context(width, height):
    # 1. Try EGL first if we are on Linux (Best for headless servers)
    if sys.platform.startswith("linux"):
        try:
            return create_egl_context(width, height)
        except Exception as e:
            print(f"[WARN]: EGL failed, falling back to GLFW: {e}")

    # 2. Use GLFW for MacOS, Windows, or Linux with a Desktop Environment
    return create_glfw_context(width, height)

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
    if not EGL.eglChooseConfig(display,
                              (EGL.EGLint * len(config_attribs))(*config_attribs),
                              ctypes.byref(config), 1,
                              ctypes.byref(num)):

        raise RuntimeError("eglChooseConfig failed")

    if num.value == 0:
        raise RuntimeError("No EGL configs found")

    pbuffer_attribs = [EGL.EGL_WIDTH, width, EGL.EGL_HEIGHT, height, EGL.EGL_NONE]
    surface = EGL.eglCreatePbufferSurface(display, config, (EGL.EGLint * len(pbuffer_attribs))(*pbuffer_attribs))
    EGL.eglBindAPI(EGL.EGL_OPENGL_API)

    ctx_attribs = [EGL.EGL_CONTEXT_MAJOR_VERSION, 3, EGL.EGL_CONTEXT_MINOR_VERSION, 3, EGL.EGL_NONE]
    ctx = EGL.eglCreateContext(display, config, EGL.EGL_NO_CONTEXT, (EGL.EGLint * len(ctx_attribs))(*ctx_attribs))

    if ctx == EGL.EGL_NO_CONTEXT:
        raise RuntimeError("eglCreateContext failed")
    if not EGL.eglMakeCurrent(display, surface, surface, ctx):
        raise RuntimeError("eglMakeCurrent failed")

    print(f" Done ({int((time()-start)*1000)}ms)")

    print(f"[INFO]: EGL version: {major.value}.{minor.value}")
    print(f"[INFO]: OpenGL version: {GL.glGetString(GL.GL_VERSION).decode()}")
    print(f"[INFO]: Renderer: {GL.glGetString(GL.GL_RENDERER).decode()}")
    return display, surface, ctx

# --------------- GLFW CONTEXT ----------------

def create_glfw_context(width, height):
    import glfw
    print("[INFO]: Initializing GLFW...", end='', flush=True)
    start = time()

    if not glfw.init():
        raise RuntimeError("GLFW could not be initialized")

    # 1. Configure Window Hints for Offscreen Rendering
    # This tells GLFW not to actually show a window on the taskbar/dock
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    
    # 2. Set OpenGL Version (3.3 Core Profile)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    
    # 3. MacOS Specific Compatibility
    if sys.platform == "darwin":
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, GL.GL_TRUE)

    # 4. Create the Window (The Context Container)
    window = glfw.create_window(width, height, "Offscreen Context", None, None)
    
    if not window:
        glfw.terminate()
        raise RuntimeError("Failed to create GLFW window")

    # 5. Bind the Context to the Current Thread
    glfw.make_context_current(window)

    print(f" Done ({int((time()-start)*1000)}ms)")

    # 6. Report Environment Details
    print(f"[INFO]: GLFW Version: {glfw.get_version_string().decode()}")
    print(f"[INFO]: OpenGL Version: {GL.glGetString(GL.GL_VERSION).decode()}")
    print(f"[INFO]: Renderer: {GL.glGetString(GL.GL_RENDERER).decode()}")

    return window