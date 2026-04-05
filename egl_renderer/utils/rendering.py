"""
renderer.py — shared rendering logic for normal rendering, VR180 (domemaster) and VR360 (equirectangular).

Both render passes share:
  - EGL context creation          → create_egl_context()  [context.py]
  - Geometry helpers              → setup_cube/quad, perspective, look_at  [geometry.py]
  - Normal FBO setup              → setup_fbo()
  - Cubemap FBO setup             → setup_cubemap_fbo()
  - Final FBO setup               → setup_final_fbo()
  - Geometry + instance upload    → upload_geometry()
  - Colormap texture upload       → upload_colormap()
  - Camera path loading           → load_camera_path()
  - Single screen frame render    → 
  - The 6-face cubemap render     → render_cubemap_faces()
  - FFmpeg process management     → open_ffmpeg() / close_ffmpeg()
  - Pixel readback + pipe write   → readback_and_pipe()
  - Double-buffered PBO readback  → setup_pbos(), readback_and_pipe_pbo(), flush_last_frame()

What differs per mode is kept in normal.py / VR180.py / VR360.py:
  - Which projection shader is compiled and its specific uniforms
  - Aspect-ratio enforcement
  - FFmpeg metadata flags
  - Camera file column count
"""
from time import time
import ctypes
import subprocess
import numpy as np
import matplotlib.pyplot as plt

from OpenGL.GL import *

from egl_renderer.utils.geometry import setup_cube, setup_quad, look_at, perspective

# ── Cubemap face directions (OpenGL spec — never change these) ─────────────────
CUBE_TARGETS = [
    (np.array([ 1,  0,  0], np.float32), np.array([ 0, -1,  0], np.float32)),  # +X
    (np.array([-1,  0,  0], np.float32), np.array([ 0, -1,  0], np.float32)),  # -X
    (np.array([ 0,  1,  0], np.float32), np.array([ 0,  0,  1], np.float32)),  # +Y
    (np.array([ 0, -1,  0], np.float32), np.array([ 0,  0, -1], np.float32)),  # -Y
    (np.array([ 0,  0,  1], np.float32), np.array([ 0, -1,  0], np.float32)),  # +Z
    (np.array([ 0,  0, -1], np.float32), np.array([ 0, -1,  0], np.float32)),  # -Z
]

CUBE_FACE_SIZE = 2048  # Resolution per cubemap face


# ── FBO helpers ────────────────────────────────────────────────────────────────

def setup_fbo(width, height):
    """
    Create a framebuffer with an RG32F cubemap texture attachment.
    Returns (fbo, texture). To be used with the normal renderer.
    """
    fbo = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RG32F, width, height,
                 0, GL_RG, GL_FLOAT, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, tex, 0)
    assert glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    return fbo, tex


def setup_cubemap_fbo():
    """
    Create a framebuffer with an RG32F cubemap texture attachment.
    Returns (fbo, cubemap_texture).
    The cubemap stores (weighted_value, weight) in the RG channels for
    the depth-weighted quantity accumulation pass.
    """
    fbo = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)

    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_CUBE_MAP, tex)
    for i in range(6):
        glTexImage2D(GL_TEXTURE_CUBE_MAP_POSITIVE_X + i, 0, GL_RG32F,
                     CUBE_FACE_SIZE, CUBE_FACE_SIZE, 0, GL_RG, GL_FLOAT, None)
    glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_WRAP_R, GL_CLAMP_TO_EDGE)
    return fbo, tex


def setup_final_fbo(width, height):
    """
    Create a framebuffer with an RGBA8 2-D texture attachment for the
    projection pass output (what gets piped to FFmpeg).
    Returns (fbo, texture).
    """
    fbo = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)

    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, None)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, tex, 0)
    glPixelStorei(GL_PACK_ALIGNMENT, 1)
    return fbo, tex


# ── Geometry + data upload ─────────────────────────────────────────────────────

def upload_geometry(data_file):
    """
    Load the binary float32 data file and upload per-instance attributes.

    File layout: 6 contiguous arrays of N float32 values each, concatenated:
        x, y, z   — particle world position
        dx        — particle scale
        qty       — scalar quantity to visualise
        w         — weight for the depth-weighted accumulation

    Returns (cube_vao, quad_vao, N) where N is the number of instances.
    """

    print(f"[INFO]: Loading binary simulation data...", end='', flush=True)
    t = time()

    cube_vao, quad_vao = setup_cube(), setup_quad()

    raw = np.fromfile(data_file, np.float32)
    N = raw.size // 6
    x, y, z, dx, qty, w = np.split(raw, 6)
    instance_data = np.column_stack([x, y, z, dx]).astype(np.float32)

    glBindVertexArray(cube_vao)

    # Per-instance position + scale  (layout location 1)
    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, instance_data.nbytes, instance_data, GL_STATIC_DRAW)
    glEnableVertexAttribArray(1)
    glVertexAttribPointer(1, 4, GL_FLOAT, False, 0, None)
    glVertexAttribDivisor(1, 1)

    # Per-instance quantity (loc 5) and weight (loc 6)
    for loc, arr in zip([5, 6], [qty, w]):
        buf = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, buf)
        glBufferData(GL_ARRAY_BUFFER, arr.nbytes, arr, GL_STATIC_DRAW)
        glEnableVertexAttribArray(loc)
        glVertexAttribPointer(loc, 1, GL_FLOAT, False, 0, None)
        glVertexAttribDivisor(loc, 1)

    print(f" Done ({int((time()-t)*1000)}ms)")
    print(f"[INFO]: Loaded {N} particles")

    return cube_vao, quad_vao, N


def upload_colormap(colormap):
    """
    Bake a matplotlib colormap into a 256×1 RGBA8 GL texture.
    Returns the texture object.
    """
    cmap = plt.get_cmap(colormap, 256)
    data = (cmap(np.linspace(0, 1, 256)) * 255).astype(np.uint8)

    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 256, 1, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    return tex


# ── Camera path loading ────────────────────────────────────────────────────────

def load_camera_path(camera_file, expected_cols, col_names):
    """
    Load a whitespace-delimited camera path file.

    Parameters
    ----------
    camera_file   : path to the text file
    expected_cols : exact number of columns expected
    col_names     : human-readable column description for error messages

    Returns a (N, expected_cols) float32 array.
    """
    cam = np.loadtxt(camera_file, dtype=np.float32)
    if cam.ndim == 1:
        cam = cam[np.newaxis, :]
    if cam.shape[1] < expected_cols:
        raise ValueError(
            f"Camera file must have {expected_cols} columns ({col_names}), "
            f"got {cam.shape[1]}."
        )
    if cam.shape[1] > expected_cols:
        print(f"[WARN]: found {cam.shape[1]} columns in camera path, "
              f"expected {expected_cols}. Extra columns will be ignored.")
    return cam[:, :expected_cols]


# ── FFmpeg process ─────────────────────────────────────────────────────────────

def open_ffmpeg(width, height, framerate, video_file, hwaccel="none", encoder="x264", extra_metadata=None):
    """
    Spawn an FFmpeg process that reads raw RGBA frames from stdin.

    Parameters
    ----------
    extra_metadata : list of alternating ['-metadata', 'key=value', ...] strings
                     appended before the output path (e.g. spherical tags for 360).
    """

    # Encoder settings for each codec on each platform
    encoders = {
        "none" : {
            "x264" : ["-c:v", "libx264", "-crf", "22", "-preset", "fast"],
            "x265" : ["-c:v", "libx265", "-crf", "22", "-preset", "fast"],
            "av1"  : ["-c:v", "libsvtav1", "-crf", "25", "-preset", "11",
                      "-svtav1-params", "lp=6"]
        },
        "nvenc" : {
            "x264" : ["-c:v", "h264_nvenc", "-qp", "22", "-rc", "constqp",
                      "-preset", "p7", "-tune", "hq"],
            "x265" : ["-c:v", "hevc_nvenc", "-qp", "22", "-rc", "constqp",
                      "-preset", "p7", "-tune", "hq"],
            "av1"  : ["-c:v", "av1_nvenc",  "-qp", "25", "-rc", "constqp",
                      "-preset", "p7", "-tune", "hq"]
        },
        "amf" : {
            "x264" : ["-c:v", "h264_amf", "-usage", "high_quality", "-quality",
                      "quality", "-preset", "quality", "-rc", "cqp", "-qp_i", "22",
                      "-qp_p", "22", "-qp_b", "22"],
            "x265" : ["-c:v", "hevc_amf", "-usage", "high_quality", "-quality",
                      "quality", "-preset", "quality", "-rc", "cqp",
                      "-qp_i", "22", "-qp_p", "22"],
            "av1"  : ["-c:v", "av1_amf", "-usage", "high_quality", "-quality",
                      "high_quality", "-preset", "quality", "-rc", "cqp",
                      "-qp_i", "25", "-qp_p", "25", "-qp_b", "25"],
        },
        "qsv" : {
            "x264" : ["-c:v", "h264_qsv", "-preset", "veryslow", "-global_quality", "22"],
            "x265" : ["-c:v", "hevc_qsv", "-preset", "veryslow", "-global_quality", "22"],
            "av1"  : ["-c:v", "av1_qsv", "-preset", "veryslow", "-global_quality", "22"]
        }
    }

    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-v', 'error',
        '-f', 'rawvideo', '-vcodec', 'rawvideo',
        '-s', f'{width}x{height}',
        '-pix_fmt', 'rgba', '-r', str(framerate), '-i', '-',
        '-pix_fmt', 'yuv420p'
    ]

    cmd.extend(encoders[hwaccel][encoder])

    if extra_metadata:
        cmd.extend(extra_metadata)
    cmd.append(video_file)
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def close_ffmpeg(process):
    process.stdin.close()
    process.wait()


# ── Render functions ─────────────────────────────────────────────────────────

def render_frame(width, height, pos, target, up,
                  accum_fbo, cube_vao, N,
                  depth_prog, u_view, u_campos, u_gscale, u_proj):
    """
    Render a single frame for a normal screen
    """
    glBindFramebuffer(GL_FRAMEBUFFER, accum_fbo)
    glViewport(0, 0, width, height)
    glClear(GL_COLOR_BUFFER_BIT)
    glEnable(GL_BLEND)
    glBlendFunc(GL_ONE, GL_ONE)
    glUseProgram(depth_prog)

    proj = perspective(60, width / height, 0.1, 100)
    view = look_at(pos, target, up)
    glUniformMatrix4fv(u_proj,   1, GL_FALSE, proj.T)
    glUniformMatrix4fv(u_view,   1, GL_FALSE, view.T)
    glUniform3f(u_campos, pos[0], pos[1], pos[2])
    glUniform1f(u_gscale, 1.0)

    glBindVertexArray(cube_vao)
    glDrawElementsInstanced(GL_TRIANGLES, 36, GL_UNSIGNED_INT, None, N)


def render_cubemap_faces(cube_fbo, cube_tex, cube_vao, N,
                         depth_prog, u_view, u_campos, u_gscale, pos):
    """
    Render all 6 cubemap faces for a given camera position into cube_fbo.
    Assumes the projection uniform has already been uploaded to depth_prog.
    Uses additive blending to accumulate depth-weighted contributions.
    """
    glBindFramebuffer(GL_FRAMEBUFFER, cube_fbo)
    glViewport(0, 0, CUBE_FACE_SIZE, CUBE_FACE_SIZE)
    glUseProgram(depth_prog)
    glEnable(GL_BLEND)
    glBlendFunc(GL_ONE, GL_ONE)

    for i, (fwd, up) in enumerate(CUBE_TARGETS):
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_CUBE_MAP_POSITIVE_X + i, cube_tex, 0)
        glClear(GL_COLOR_BUFFER_BIT)
        view = look_at(pos, pos + fwd, up)
        glUniformMatrix4fv(u_view, 1, GL_FALSE, view.T)
        glUniform3f(u_campos, *pos)
        glUniform1f(u_gscale, 1.0)
        glBindVertexArray(cube_vao)
        glDrawElementsInstanced(GL_TRIANGLES, 36, GL_UNSIGNED_INT, None, N)


# ── Pixel readback + PBO double-buffering ──────────────────────────────────────

def readback_and_pipe(process, width, height):
    """Read the current framebuffer and write raw RGBA bytes to FFmpeg stdin."""
    pixels = glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE)
    process.stdin.write(pixels)

def setup_pbos(width, height, num_pbos=2):
    """
    Allocate PBOs for async double-buffered pixel readback.
    Returns the list of PBO handles.
    """
    pbos = glGenBuffers(num_pbos)
    for pbo in pbos:
        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbo)
        glBufferData(GL_PIXEL_PACK_BUFFER, width * height * 4,
                     None, GL_STREAM_READ)
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
    return pbos


def readback_and_pipe_pbo(process, width, height, pbos, pbo_index, frame_index):
    """
    Async double-buffered readback using PBOs.

    Issues a DMA transfer from the current framebuffer into pbos[pbo_index],
    then maps the *other* PBO (whose transfer was issued last frame) and
    writes it to the FFmpeg pipe. The one-frame lag is handled by the caller
    flushing the final frame after the loop — see flush_last_frame().

    Returns the new pbo_index.
    """
    next_pbo = (pbo_index + 1) % len(pbos)

    # Kick off async readback into current PBO
    glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
    glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE,
                 ctypes.c_void_p(0))

    # Map the *other* PBO — its transfer was issued the previous frame
    glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[next_pbo])
    ptr = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, width * height * 4,
                           GL_MAP_READ_BIT)
    if ptr and frame_index > 0:  # frame 0: other PBO not yet filled
        buf = ctypes.string_at(ptr, width * height * 4)
        process.stdin.write(buf)
    glUnmapBuffer(GL_PIXEL_PACK_BUFFER)

    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
    return next_pbo


def flush_last_frame(process, width, height, pbos, pbo_index):
    """
    After the render loop, map the PBO that holds the last frame
    (the one that was written to but not yet consumed) and flush it.
    """
    glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
    ptr = glMapBuffer(GL_PIXEL_PACK_BUFFER, GL_READ_ONLY)
    if ptr:
        buf = ctypes.string_at(ptr, width * height * 4)
        process.stdin.write(buf)
        glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)


# ── Common projection-pass setup ──────────────────────────────────────────────

def bind_projection_inputs_cube(proj_prog, cube_tex, cmap_tex,
                            u_cubemap, u_cmap,
                            u_minv, u_maxv, u_under, u_over, u_bad,
                            min_val, max_val,
                            under_color, over_color, bad_color):
    """
    Activate the projection program and bind all uniforms that are identical
    between the domemaster and equirectangular passes (everything except
    the dome-specific domeBasis).
    """
    glDisable(GL_BLEND)
    glUseProgram(proj_prog)

    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_CUBE_MAP, cube_tex)
    glUniform1i(u_cubemap, 0)

    glActiveTexture(GL_TEXTURE1)
    glBindTexture(GL_TEXTURE_2D, cmap_tex)
    glUniform1i(u_cmap, 1)

    glUniform1f(u_minv,  min_val)
    glUniform1f(u_maxv,  max_val)
    glUniform4f(u_under, *under_color)
    glUniform4f(u_over,  *over_color)
    glUniform4f(u_bad,   *bad_color)

def bind_projection_inputs_screen(screen_prog, accum_tex, cmap_tex,
                                u_accum, u_cmap,
                                u_minv, u_maxv, u_under, u_over, u_bad,
                                min_val, max_val,
                                under_color, over_color, bad_color):
    """
    Activate the projection program and bind all uniforms
    """
    glDisable(GL_BLEND)
    glUseProgram(screen_prog)

    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, accum_tex)
    glUniform1i(u_accum, 0)

    glActiveTexture(GL_TEXTURE1)
    glBindTexture(GL_TEXTURE_2D, cmap_tex)
    glUniform1i(u_cmap, 1)
    
    glUniform1f(u_minv,  min_val)
    glUniform1f(u_maxv,  max_val)
    glUniform4f(u_under, *under_color)
    glUniform4f(u_over,  *over_color)
    glUniform4f(u_bad,   *bad_color)