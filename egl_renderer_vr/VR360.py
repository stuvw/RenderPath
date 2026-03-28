from tqdm import tqdm

from OpenGL.GL import *
from OpenGL.GL import shaders

from egl_renderer_vr.context import create_egl_context
from egl_renderer_vr.utils import perspective
from egl_renderer_vr.shaders import VERTEX_SHADER_DEPTH, FRAGMENT_SHADER_DEPTH, SCREEN_VERTEX_SHADER, EQUIRECT_FRAGMENT_SHADER
from egl_renderer_vr.renderer import (
    setup_cubemap_fbo, setup_final_fbo,
    upload_geometry, upload_colormap,
    load_camera_path,
    open_ffmpeg, close_ffmpeg,
    render_cubemap_faces,
    bind_projection_inputs,
    readback_and_pipe,
)

# ---------------- RENDER ----------------

def render_360(width, height, framerate, data_file, camera_file, video_file,
               min_val, max_val, under_color, over_color, bad_color, colormap):
    """
    Render a 360° equirectangular video suitable for VR headsets.

    Camera file: N×3  — px py pz
                         ^^^^^^^
                         position only; equirectangular covers all directions

    Output: 2:1 HEVC video with spherical-video metadata for headset auto-detection.

    NOTE: the original camera file format used 9 columns (px py pz cx cy cz nx ny nz)
    but the center/normal columns were never consumed by the renderer — only the
    position was used. The format has been simplified to 3 columns. If you have an
    existing 9-column file it will still load correctly; extra columns are ignored.
    """
    if width != height * 2:
        print(f"[WARN]: 360 video requires 2:1 aspect. Adjusting height to {width // 2}.")
        height = width // 2

    create_egl_context(width, height)

    # Compile shaders
    depth_prog = shaders.compileProgram(
        shaders.compileShader(VERTEX_SHADER_DEPTH, GL_VERTEX_SHADER),
        shaders.compileShader(FRAGMENT_SHADER_DEPTH, GL_FRAGMENT_SHADER))
    equirect_prog = shaders.compileProgram(
        shaders.compileShader(SCREEN_VERTEX_SHADER, GL_VERTEX_SHADER),
        shaders.compileShader(EQUIRECT_FRAGMENT_SHADER, GL_FRAGMENT_SHADER))

    cube_fbo, cube_tex    = setup_cubemap_fbo()
    final_fbo, final_tex  = setup_final_fbo(width, height)
    cube_vao, quad_vao, N = upload_geometry(data_file)
    cmap_tex               = upload_colormap(colormap)

    # 3 columns expected; 9-column legacy files are accepted (extra cols ignored)
    cam_path = load_camera_path(camera_file,
                                expected_cols=3,
                                col_names="px py pz")

    process = open_ffmpeg(width, height, framerate, video_file, extra_metadata=[
        '-metadata:s:v:0', 'spherical-video=true',
        '-metadata:s:v:0', 'projection=equirectangular',
    ])

    # Cache uniform locations
    u_proj    = glGetUniformLocation(depth_prog,    "projection")
    u_view    = glGetUniformLocation(depth_prog,    "view")
    u_campos  = glGetUniformLocation(depth_prog,    "cameraPosition")
    u_gscale  = glGetUniformLocation(depth_prog,    "globalScale")
    u_cubemap = glGetUniformLocation(equirect_prog, "cubemap")
    u_cmap    = glGetUniformLocation(equirect_prog, "colormap")
    u_minv    = glGetUniformLocation(equirect_prog, "minVal")
    u_maxv    = glGetUniformLocation(equirect_prog, "maxVal")
    u_under   = glGetUniformLocation(equirect_prog, "underColor")
    u_over    = glGetUniformLocation(equirect_prog, "overColor")
    u_bad     = glGetUniformLocation(equirect_prog, "badColor")

    proj_cube = perspective(90, 1.0, 0.1, 1000.0)
    glUseProgram(depth_prog)
    glUniformMatrix4fv(u_proj, 1, GL_FALSE, proj_cube.T)

    for frame in tqdm(cam_path, desc="Rendering VR360"):
        pos = frame[:3]

        # Part A: render all 6 cubemap faces
        render_cubemap_faces(cube_fbo, cube_tex, cube_vao, N,
                             depth_prog, u_view, u_campos, u_gscale, pos)

        # Part B: project cubemap → equirectangular
        glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
        glViewport(0, 0, width, height)
        glClear(GL_COLOR_BUFFER_BIT)

        bind_projection_inputs(
            equirect_prog, cube_tex, cmap_tex,
            u_cubemap, u_cmap,
            u_minv, u_maxv, u_under, u_over, u_bad,
            min_val, max_val, under_color, over_color, bad_color,
        )

        glBindVertexArray(quad_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        readback_and_pipe(process, width, height)

    close_ffmpeg(process)
