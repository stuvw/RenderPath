import subprocess
from time import time
import ctypes
import argparse
import os
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
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


# ---------------- SHADERS ----------------

VERTEX_SHADER_DEPTH = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec4 posScale; // Combined: x, y, z, and dx (scale)
layout(location = 5) in float quantity;
layout(location = 6) in float weight;

uniform mat4 projection;
uniform mat4 view;
uniform float globalScale;

out vec3 vWorldPosition;
flat out vec2 vDataValue;

void main() {
    // Manually calculate the world position: (local_pos * scale) + translation
    // globalScale is applied to the local vertex before the instance scale
    vec3 scaledPos = position * globalScale * posScale.w;
    vec3 worldPos = scaledPos + posScale.xyz;
    
    vWorldPosition = worldPos;
    
    // denominator is (scaleX * scaleY), which is (posScale.w * posScale.w)
    vDataValue = vec2(quantity * weight, weight) / (posScale.w * posScale.w);
    
    gl_Position = projection * view * vec4(worldPos, 1.0);
}
"""

FRAGMENT_SHADER_DEPTH = """
#version 330 core
in vec3 vWorldPosition;
flat in vec2 vDataValue;
uniform vec3 cameraPosition;
out vec4 FragColor;

void main() {
    float d = distance(vWorldPosition, cameraPosition);
    // Removing glFrontFacing fixes an issue, and I don't know why it was here to begin with...
    // float s = gl_FrontFacing ? 1.0 : -1.0;
    // float f = s * d;
    FragColor = vec4(d * vDataValue.x, d * vDataValue.y, 0.0, 1.0);
}
"""

SCREEN_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 position;
out vec2 vUv;
// Instead of: vUv = (position + 1.0) * 0.5;
// We now flip the frame here, removing one unnecessary call
void main() {
    vUv = vec2((position.x + 1.0) * 0.5, (1.0 - (position.y + 1.0) * 0.5)); 
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

SCREEN_FRAGMENT_SHADER = """
#version 330 core
in vec2 vUv;

uniform sampler2D depthTexture;
uniform sampler2D colormap;
uniform float minVal;
uniform float maxVal;

uniform vec4 underColor;
uniform vec4 overColor;
// uniform vec4 badColor;

out vec4 FragColor;

void main() {
    vec2 data = texture(depthTexture, vUv).rg;
    float qw = data.r;
    float w  = data.g;

    if (w == 0.0) discard;
    //{
    //    FragColor = badColor;
    //    return;
    //}

    const float INV_LOG10 = 0.4342944819;
    float depth = log(qw / w) * INV_LOG10;

    // Branchless tone mapping
    float t = (depth - minVal) / (maxVal - minVal);
    vec4 color = texture(colormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(underColor, color, step(0.0, t));
    color = mix(color, overColor, step(1.0, t));
    FragColor = color;
}
"""

# ---------------- GEOMETRY ----------------

def setup_cube():
    vertices = np.array([
        -0.5,-0.5,-0.5,  0.5,-0.5,-0.5,  0.5, 0.5,-0.5, -0.5, 0.5,-0.5,
        -0.5,-0.5, 0.5,  0.5,-0.5, 0.5,  0.5, 0.5, 0.5, -0.5, 0.5, 0.5
    ], np.float32)

    indices = np.array([
        0,1,2, 2,3,0, 4,5,6, 6,7,4,
        0,4,7, 7,3,0, 1,5,6, 6,2,1,
        0,1,5, 5,4,0, 3,2,6, 6,7,3
    ], np.uint32)

    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)

    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
    glVertexAttribPointer(0, 3, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(0)

    ebo = glGenBuffers(1)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

    return vao


def setup_quad():
    quad = np.array([-1,-1, 1,-1, -1,1, 1,1], np.float32)
    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)
    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, quad.nbytes, quad, GL_STATIC_DRAW)
    glVertexAttribPointer(0, 2, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(0)
    return vao


# ---------------- UTIL ----------------

def perspective(fovy, aspect, near, far):
    f = 1.0 / np.tan(np.radians(fovy) / 2)
    m = np.zeros((4,4), np.float32)
    m[0,0] = f / aspect
    m[1,1] = f
    m[2,2] = (far+near)/(near-far)
    m[2,3] = (2*far*near)/(near-far)
    m[3,2] = -1
    return m


def look_at(eye, center, up):
    f = center - eye
    f /= np.linalg.norm(f)
    u = up / np.linalg.norm(up)
    s = np.cross(f, u)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)

    m = np.eye(4, dtype=np.float32)
    m[0,:3] = s
    m[1,:3] = u
    m[2,:3] = -f
    m[:3,3] = -m[:3,:3] @ eye
    return m


# ---------------- MAIN RENDER ----------------

def render(width, height, framerate,
           data_file, camera_file, video_file,
           minVal, maxVal,
           underColor, overColor, badColor, colormap
           ):

    create_egl_context(width, height) # Remove this line, Earth blows up

    glDisable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_ONE, GL_ONE)
    glClearColor(0.0, 0.0, 0.0, 0.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glPixelStorei(GL_PACK_ALIGNMENT, 1)

    print("[INFO]: Compiling shaders...", end='', flush=True)
    start = time()

    depth_prog = shaders.compileProgram(
        shaders.compileShader(VERTEX_SHADER_DEPTH, GL_VERTEX_SHADER),
        shaders.compileShader(FRAGMENT_SHADER_DEPTH, GL_FRAGMENT_SHADER)
    )

    screen_prog = shaders.compileProgram(
        shaders.compileShader(SCREEN_VERTEX_SHADER, GL_VERTEX_SHADER),
        shaders.compileShader(SCREEN_FRAGMENT_SHADER, GL_FRAGMENT_SHADER)
    )

    end = time()
    print(f" Done ({int((end-start)*1000)}ms)")

    print("[INFO]: Creating Framebuffers...", end='', flush=True)
    start = time()

    # ---------- Accumulation FBO (RG32F) ----------
    fbo = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)

    accum_tex = glGenTextures(1) # aka: fbo_texture
    glBindTexture(GL_TEXTURE_2D, accum_tex)
    glTexImage2D(
        GL_TEXTURE_2D, 0,
        GL_RG32F,
        width, height,
        0, GL_RG, GL_FLOAT, None
    )
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

    glFramebufferTexture2D(
        GL_FRAMEBUFFER,
        GL_COLOR_ATTACHMENT0,
        GL_TEXTURE_2D,
        accum_tex,
        0
    )

    glBindFramebuffer(GL_FRAMEBUFFER, 0)

    assert glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE


    # ---------- Final Color FBO (RGBA8) ----------
    final_fbo = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)

    final_tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, final_tex)
    glTexImage2D(
        GL_TEXTURE_2D, 0,
        GL_RGBA8,
        width, height,
        0, GL_RGBA, GL_UNSIGNED_BYTE, None
    )
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

    glFramebufferTexture2D(
        GL_FRAMEBUFFER,
        GL_COLOR_ATTACHMENT0,
        GL_TEXTURE_2D,
        final_tex,
        0
    )

    assert glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE

    glBindFramebuffer(GL_FRAMEBUFFER, 0)

    end = time()
    print(f" Done ({int((end-start)*1000)}ms)")

    cube_vao = setup_cube()
    quad_vao = setup_quad()


    # colormap
    cmap = plt.get_cmap(colormap, 256)
    data = (cmap(np.linspace(0,1,256)) * 255).astype(np.uint8)
    cmap_tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, cmap_tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 256, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

    print("[INFO]: Loading volume data...", end='', flush=True)
    start = time()

    # load data
    raw = np.fromfile(data_file, np.float32)
    N = raw.size // 6
    x,y,z,dx,qty,w = np.split(raw, 6)

    end = time()
    print(f" Done ({int((end-start)*1000)}ms)")

    print("[INFO]: Creating instance data...", end='', flush=True)

    instance_data = np.column_stack([x, y, z, dx]).astype(np.float32)

    end = time()
    print(f" Done ({int((end-start)*1000)}ms)")

    print("[INFO]: Creating mesh...", end='', flush=True)
    start = time()

    glBindVertexArray(cube_vao)

    mvbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, mvbo)
    glBufferData(GL_ARRAY_BUFFER, instance_data.nbytes, instance_data, GL_STATIC_DRAW)
    glEnableVertexAttribArray(1)
    glVertexAttribPointer(1, 4, GL_FLOAT, False, 0, None)
    glVertexAttribDivisor(1, 1)

    for loc, arr in zip([5,6], [qty,w]):
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, arr.nbytes, arr, GL_STATIC_DRAW)
        glVertexAttribPointer(loc, 1, GL_FLOAT, False, 0, None)
        glEnableVertexAttribArray(loc)
        glVertexAttribDivisor(loc, 1)

    end = time()
    print(f" Done ({int((end-start)*1000)}ms)")

    print("[INFO]: Loading camera path...", end='', flush=True)
    start = time()

    cam = np.loadtxt(camera_file, np.float32)

    end = time()
    print(f" Done ({int((end-start)*1000)}ms)")

    command = [
    'ffmpeg',
    '-hide_banner',
    '-v',
    'error',
    '-y',
    '-f', 'rawvideo',
    '-vcodec', 'rawvideo',
    '-s', f'{width}x{height}',
    '-pix_fmt', 'rgba',
    '-r', str(framerate),
    '-i', '-',                      # Read input from stdin (the pipe)
    '-pix_fmt', 'yuv420p',
    '-c:v', 'hevc_nvenc',           # FFmpeg tuning madness
    '-cq', '22', '-preset', 'p7',
    '-rc', 'vbr_hq',
    '-tune', 'hq',
    video_file
    ]

    process = subprocess.Popen(command, stdin=subprocess.PIPE)

    # -- Setup phase --
    num_pbos = 2
    pbos = glGenBuffers(num_pbos)
    for pbo in pbos:
        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbo)
        glBufferData(GL_PIXEL_PACK_BUFFER, width * height * 4, None, GL_STREAM_READ)
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)

    pbo_index = 0

    for i,(x,y,z,cx,cy,cz,nx,ny,nz) in enumerate(tqdm(cam, desc="Rendering frames", unit=" frames")):
        # Pass 1: Render to FBO
        glBindFramebuffer(GL_FRAMEBUFFER, fbo)
        glViewport(0,0,width,height)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glDisable(GL_DEPTH_TEST)

        glUseProgram(depth_prog)

        proj = perspective(60, width/height, 0.1, 100)
        view = look_at(np.array([x,y,z]), np.array([cx,cy,cz]), np.array([nx,ny,nz]))

        glUniformMatrix4fv(glGetUniformLocation(depth_prog, "projection"), 1, GL_FALSE, proj.T)
        glUniformMatrix4fv(glGetUniformLocation(depth_prog, "view"), 1, GL_FALSE, view.T)
        glUniform3f(glGetUniformLocation(depth_prog, "cameraPosition"), x, y, z)
        glUniform1f(glGetUniformLocation(depth_prog, "globalScale"), 1.0)

        glBindVertexArray(cube_vao)
        glDrawElementsInstanced(GL_TRIANGLES, 36, GL_UNSIGNED_INT, None, N)

        # Pass 2: Render to final frame
        glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT)

        glUseProgram(screen_prog)

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, accum_tex)
        glUniform1i(glGetUniformLocation(screen_prog, "depthTexture"), 0)


        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, cmap_tex)
        glUniform1i(glGetUniformLocation(screen_prog, "colormap"), 1)

        glUniform1f(glGetUniformLocation(screen_prog,"minVal"), minVal)
        glUniform1f(glGetUniformLocation(screen_prog,"maxVal"), maxVal)
        glUniform4f(glGetUniformLocation(screen_prog,"underColor"), *underColor)
        glUniform4f(glGetUniformLocation(screen_prog,"overColor"), *overColor)
        # glUniform4f(glGetUniformLocation(screen_prog,"badColor"), *badColor)
        # Debugging, re-enable in shader too

        glBindVertexArray(quad_vao)
        glDrawArrays(GL_TRIANGLE_STRIP,0,4)
        glEnable(GL_BLEND)

        glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)

        # Double-buffering, avoid pipeline stall

        next_pbo = (pbo_index + 1) % num_pbos

        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
        glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, ctypes.c_void_p(0))

        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[next_pbo])
        ptr = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, width * height * 4, GL_MAP_READ_BIT)
        if ptr:
            # If we don't do this, first frame is empty
            if i > 0:
                buf = ctypes.string_at(ptr, width * height * 4)
                process.stdin.write(buf)
            glUnmapBuffer(GL_PIXEL_PACK_BUFFER)

        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
        pbo_index = next_pbo

    # Write last frame correctly
    glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
    ptr = glMapBuffer(GL_PIXEL_PACK_BUFFER, GL_READ_ONLY)
    if ptr:
        buf = ctypes.string_at(ptr, width * height * 4)
        process.stdin.write(buf)
        glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)

    process.stdin.close()
    process.wait()


def parse_args():
    parser = argparse.ArgumentParser("RenderPath")

    parser.add_argument("--data-file", "-df", type=str, required=True)
    parser.add_argument("--camera-file", "-cf", type=str, required=True)
    parser.add_argument("--video-file", "-vf", type=str, default="out.mp4")
    parser.add_argument("--width", "-wx", type=int, default=1280)
    parser.add_argument("--height", "-hy", type=int, default=720)
    parser.add_argument("--framerate", "-fr", type=int, default=30)
    parser.add_argument("--minval", type=float, default=-3.0)
    parser.add_argument("--maxval", type=float, default=3.0)
    parser.add_argument("--undercolor", "-uc", type=float, nargs=4,default=(0,0,0,1))
    parser.add_argument("--overcolor", "-oc", type=float, nargs=4, default=(1,1,1,1))
    parser.add_argument("--badcolor", "-bc", type=float, nargs=4, default=(1,0,1,1))
    parser.add_argument("--colormap", "-cm", type=str, default="inferno")

    args = parser.parse_args()

    return args

# ---------------- ENTRY ----------------

def main():
    args = parse_args()
    render(
        width=args.width,
        height=args.height,
        framerate=args.framerate,
        data_file=args.data_file,
        camera_file=args.camera_file,
        video_file=args.video_file,
        minVal=args.minval,
        maxVal=args.maxval,
        underColor=args.undercolor,
        overColor=args.overcolor,
        badColor=args.badcolor,
        colormap=args.colormap
    )
