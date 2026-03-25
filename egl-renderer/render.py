import subprocess
from time import time
import ctypes
import os
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm

from OpenGL.GL import *
from OpenGL.GL import shaders

from .context import create_egl_context
from .shaders import (
    SCREEN_FRAGMENT_SHADER, 
    SCREEN_VERTEX_SHADER, 
    VERTEX_SHADER_DEPTH, 
    FRAGMENT_SHADER_DEPTH
)
from .geometry import setup_cube, setup_quad
from .utils import perspective, look_at

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