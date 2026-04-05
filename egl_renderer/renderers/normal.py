from time import time
from tqdm import tqdm

from OpenGL.GL import *
from OpenGL.GL import shaders

from egl_renderer.utils.context import create_egl_context
from egl_renderer.utils.shaders import (
    VERTEX_SHADER_DEPTH, FRAGMENT_SHADER_DEPTH,
    SCREEN_VERTEX_SHADER, SCREEN_FRAGMENT_SHADER,
)
from egl_renderer.utils.rendering import (
    setup_fbo, setup_final_fbo,
    upload_geometry, upload_colormap,
    load_camera_path,
    open_ffmpeg, close_ffmpeg,
    render_frame,
    bind_projection_inputs_screen,
    readback_and_pipe_pbo,
    flush_last_frame, setup_pbos
)

# ---------------- RENDER ----------------

def render_normal(width, height, framerate, data_file, camera_file, video_file,
                  min_val, max_val, under_color, over_color, bad_color, colormap,
                  hwaccel, encoder):
    """
    Standard (non-VR) headless renderer.

    Camera file: N×9  — px py pz  cx cy cz  nx ny nz
                         ^^^^^^^   ^^^^^^^   ^^^^^^^
                         position  look-at   up vector
    """


    create_egl_context(width, height)

    # ── Shaders ────────────────────────────────────────────────────────────────
    print("[INFO]: Compiling shaders...", end='', flush=True)
    t = time()

    depth_prog = shaders.compileProgram(
        shaders.compileShader(VERTEX_SHADER_DEPTH,   GL_VERTEX_SHADER),
        shaders.compileShader(FRAGMENT_SHADER_DEPTH, GL_FRAGMENT_SHADER))
    screen_prog = shaders.compileProgram(
        shaders.compileShader(SCREEN_VERTEX_SHADER,   GL_VERTEX_SHADER),
        shaders.compileShader(SCREEN_FRAGMENT_SHADER, GL_FRAGMENT_SHADER))

    print(f" Done ({int((time()-t)*1000)}ms)")

    # ── FBOs ───────────────────────────────────────────────────────────────────
    print("[INFO]: Creating framebuffers...", end='', flush=True)
    t = time()

    accum_fbo, accum_tex = setup_fbo(width, height)
    final_fbo, _ = setup_final_fbo(width, height)

    print(f" Done ({int((time()-t)*1000)}ms)")

    # ── Geometry, colormap, camera ─────────────────────────────────────────────
    cube_vao, quad_vao, N = upload_geometry(data_file)
    cmap_tex  = upload_colormap(colormap)
    cam_path  = load_camera_path(camera_file,
                                 expected_cols=9,
                                 col_names="px py pz cx cy cz nx ny nz")


    # ── FFmpeg ─────────────────────────────────────────────────────────────────
    process = open_ffmpeg(width, height, framerate, video_file, hwaccel, encoder)

    # ── Uniform locations ──────────────────────────────────────────────────────
    u_proj    = glGetUniformLocation(depth_prog,  "projection")
    u_view    = glGetUniformLocation(depth_prog,  "view")
    u_campos  = glGetUniformLocation(depth_prog,  "cameraPosition")
    u_gscale  = glGetUniformLocation(depth_prog,  "globalScale")
    u_accum   = glGetUniformLocation(screen_prog, "depthTexture")
    u_cmap    = glGetUniformLocation(screen_prog, "colormap")
    u_minv    = glGetUniformLocation(screen_prog, "minVal")
    u_maxv    = glGetUniformLocation(screen_prog, "maxVal")
    u_under   = glGetUniformLocation(screen_prog, "underColor")
    u_over    = glGetUniformLocation(screen_prog, "overColor")
    u_bad     = glGetUniformLocation(screen_prog, "badColor")

    # ── PBOs ───────────────────────────────────────────────────────────────────
    pbos      = setup_pbos(width, height)
    pbo_index = 0

    # ── Global GL state ────────────────────────────────────────────────────────
    glClearColor(0.0, 0.0, 0.0, 0.0)
    glDisable(GL_DEPTH_TEST)

    for i, frame in enumerate(tqdm(cam_path, desc="Rendering frames", unit="frames")):
        pos = frame[:3]
        target = frame[3:6]
        up = frame[6:]

        # ── Pass 1: accumulation ───────────────────────────────────────────────
        render_frame(width, height, pos, target, up, accum_fbo, cube_vao,
                     N, depth_prog, u_view, u_campos, u_gscale, u_proj)

        # ── Pass 2: tone mapping ───────────────────────────────────────────────
        glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
        glViewport(0, 0, width, height)
        glClear(GL_COLOR_BUFFER_BIT)

        bind_projection_inputs_screen(
            screen_prog, accum_tex, cmap_tex,
            u_accum, u_cmap,
            u_minv, u_maxv, u_under, u_over, u_bad,
            min_val, max_val, under_color, over_color, bad_color,
        )

        glBindVertexArray(quad_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        # ── Async readback ─────────────────────────────────────────────────────
        pbo_index = readback_and_pipe_pbo(process, width, height,
                                      pbos, pbo_index, frame_index=i)

    flush_last_frame(process, width, height, pbos, pbo_index)
    close_ffmpeg(process)
