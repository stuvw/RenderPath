from tqdm import tqdm

from OpenGL.GL import *
from OpenGL.GL import shaders

from egl_renderer_vr.context import create_egl_context
from egl_renderer_vr.utils import perspective, build_dome_basis
from egl_renderer_vr.shaders import VERTEX_SHADER_DEPTH, FRAGMENT_SHADER_DEPTH, SCREEN_VERTEX_SHADER, DOMEMASTER_FRAGMENT_SHADER
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

def render_180(width, height, framerate, data_file, camera_file, video_file,
               min_val, max_val, under_color, over_color, bad_color, colormap):
    """
    Render a fulldome video in Domemaster format (azimuthal equidistant fisheye).

    Camera file: N×6  — px py pz  fx fy fz
                         ^^^^^^^   ^^^^^^^
                         position  zenith/forward direction (need not be unit length)

    Output: square HEVC video; the domemaster circle is inscribed in the frame.
    """
    if width != height:
        print(f"[WARN]: Domemaster output must be square. Adjusting height to {width}.")
        height = width

    create_egl_context(width, height)

    # Compile shaders
    depth_prog = shaders.compileProgram(
        shaders.compileShader(VERTEX_SHADER_DEPTH, GL_VERTEX_SHADER),
        shaders.compileShader(FRAGMENT_SHADER_DEPTH, GL_FRAGMENT_SHADER))
    dome_prog = shaders.compileProgram(
        shaders.compileShader(SCREEN_VERTEX_SHADER, GL_VERTEX_SHADER),
        shaders.compileShader(DOMEMASTER_FRAGMENT_SHADER, GL_FRAGMENT_SHADER))

    cube_fbo, cube_tex   = setup_cubemap_fbo()
    final_fbo, final_tex = setup_final_fbo(width, height)
    cube_vao, quad_vao, N = upload_geometry(data_file)
    cmap_tex              = upload_colormap(colormap)
    cam_path              = load_camera_path(camera_file,
                                             expected_cols=6,
                                             col_names="px py pz fx fy fz")

    process = open_ffmpeg(width, height, framerate, video_file, extra_metadata=[
        '-metadata', 'comment=Domemaster azimuthal-equidistant fisheye 180deg FOV',
    ])

    # Cache uniform locations
    u_proj    = glGetUniformLocation(depth_prog, "projection")
    u_view    = glGetUniformLocation(depth_prog, "view")
    u_campos  = glGetUniformLocation(depth_prog, "cameraPosition")
    u_gscale  = glGetUniformLocation(depth_prog, "globalScale")
    u_cubemap = glGetUniformLocation(dome_prog,  "cubemap")
    u_cmap    = glGetUniformLocation(dome_prog,  "colormap")
    u_minv    = glGetUniformLocation(dome_prog,  "minVal")
    u_maxv    = glGetUniformLocation(dome_prog,  "maxVal")
    u_under   = glGetUniformLocation(dome_prog,  "underColor")
    u_over    = glGetUniformLocation(dome_prog,  "overColor")
    u_bad     = glGetUniformLocation(dome_prog,  "badColor")
    u_basis   = glGetUniformLocation(dome_prog,  "domeBasis")

    proj_cube = perspective(90, 1.0, 0.1, 1000.0)
    glUseProgram(depth_prog)
    glUniformMatrix4fv(u_proj, 1, GL_FALSE, proj_cube.T)

    for frame in tqdm(cam_path, desc="Rendering VR180"):
        pos     = frame[:3]
        forward = frame[3:6]

        # Part A: render all 6 cubemap faces
        render_cubemap_faces(cube_fbo, cube_tex, cube_vao, N,
                             depth_prog, u_view, u_campos, u_gscale, pos)

        # Part B: project cubemap → domemaster
        glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
        glViewport(0, 0, width, height)
        glClear(GL_COLOR_BUFFER_BIT)

        bind_projection_inputs(
            dome_prog, cube_tex, cmap_tex,
            u_cubemap, u_cmap,
            u_minv, u_maxv, u_under, u_over, u_bad,
            min_val, max_val, under_color, over_color, bad_color,
        )

        # Dome-specific: upload orientation basis derived from the forward vector
        basis = build_dome_basis(forward)
        glUniformMatrix3fv(u_basis, 1, GL_FALSE, basis.flatten())

        glBindVertexArray(quad_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        readback_and_pipe(process, width, height)

    close_ffmpeg(process)
