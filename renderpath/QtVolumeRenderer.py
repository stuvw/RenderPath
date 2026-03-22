"""
VolumeRendererGUI.py  –  PyQt5 + QOpenGLWidget version of HeadlessVolumeRenderer
No EGL needed; PyQt5 provides the OpenGL context automatically.
"""

import sys
import os
import ctypes
import subprocess
import threading
from time import time

import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
try:
    import psutil
except ImportError:
    psutil = None

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QOpenGLWidget,
    QSplitter, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSpinBox, QComboBox,
    QLineEdit, QFileDialog, QGroupBox, QStatusBar,
    QProgressBar, QScrollArea, QCheckBox, QSlider, QToolBar,
    QSizePolicy, QFrame, QTabWidget, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject, QSize
from PyQt5.QtGui import QFont, QColor, QIcon, QPalette

from OpenGL.GL import *
from OpenGL.GL import shaders


# ══════════════════════════════════════════════════════════════════════════════
# Palette & Stylesheet
# ══════════════════════════════════════════════════════════════════════════════

C = {
    "bg":           "#0d0d0f",
    "panel":        "#13131a",
    "panel_border": "#1e1e2e",
    "surface":      "#1a1a26",
    "surface2":     "#22223a",
    "accent":       "#5c7cfa",
    "accent_dim":   "#3a4fa8",
    "danger":       "#f05252",
    "danger_dim":   "#8c2a2a",
    "success":      "#3ecf8e",
    "success_dim":  "#1a6b4a",
    "warning":      "#f7b731",
    "text":         "#e0e0f0",
    "text_dim":     "#7a7a9a",
    "text_muted":   "#44445a",
}

SS = """
QMainWindow, QWidget {{
    background-color: {bg};
    color: {text};
    font-family: "Courier New", monospace;
    font-size: 11px;
}}
QToolBar {{
    background-color: {panel};
    border-bottom: 1px solid {panel_border};
    spacing: 4px;
    padding: 4px 8px;
}}
QStatusBar {{
    background-color: {panel};
    border-top: 1px solid {panel_border};
    color: {text_dim};
    font-size: 11px;
    padding: 2px 8px;
}}
QTabWidget::pane {{ border: none; background: {bg}; }}
QTabBar {{ background: {panel}; }}
QTabBar::tab {{
    background: {panel};
    color: {text_dim};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 18px;
    font-size: 10px;
    letter-spacing: 2px;
    font-weight: bold;
}}
QTabBar::tab:selected {{
    color: {text};
    border-bottom: 2px solid {accent};
    background: {bg};
}}
QTabBar::tab:hover:!selected {{
    color: {text};
    background: {surface};
}}
QGroupBox {{
    color: {text_muted};
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 2px;
    border: 1px solid {panel_border};
    border-radius: 3px;
    margin-top: 10px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 8px;
}}
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {{
    background: {surface};
    color: {text};
    border: 1px solid {panel_border};
    border-radius: 2px;
    padding: 3px 6px;
    font-family: "Courier New", monospace;
    font-size: 11px;
}}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
    border-color: {accent};
}}
QComboBox QAbstractItemView {{
    background: {surface2};
    color: {text};
    selection-background-color: {accent_dim};
}}
QComboBox::drop-down {{ border: none; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {panel};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {surface2};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QSlider::groove:horizontal {{
    height: 4px;
    background: {surface2};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider::sub-page:horizontal {{ background: {accent_dim}; border-radius: 2px; }}
QCheckBox {{ spacing: 6px; color: {text_dim}; }}
QCheckBox::indicator {{
    width: 13px; height: 13px;
    background: {surface};
    border: 1px solid {panel_border};
    border-radius: 2px;
}}
QCheckBox::indicator:checked {{
    background: {accent_dim};
    border-color: {accent};
}}
QPushButton {{
    background: transparent;
    color: {text_dim};
    border: 1px solid {panel_border};
    border-radius: 3px;
    padding: 6px 12px;
    font-family: "Courier New", monospace;
    font-size: 11px;
    letter-spacing: 1px;
    text-align: left;
}}
QPushButton:hover {{ background: {surface}; color: {text}; border-color: {surface2}; }}
QPushButton:pressed {{ background: {surface2}; }}
QPushButton[role="primary"] {{
    background: {accent_dim}; color: {text}; border-color: {accent};
}}
QPushButton[role="primary"]:hover {{ background: {accent}; }}
QPushButton[role="danger"] {{
    color: {danger}; border-color: {danger_dim};
}}
QPushButton[role="danger"]:hover {{ background: {danger_dim}; color: {text}; }}
QPushButton[role="success"] {{
    background: {success_dim}; color: {success}; border-color: {success};
}}
QPushButton[role="success"]:hover {{ background: {success}; color: {bg}; }}
QProgressBar {{
    background: {surface};
    border: 1px solid {panel_border};
    border-radius: 2px;
    text-align: center;
    color: {text};
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: {accent_dim};
    border-radius: 2px;
}}
QSplitter::handle {{ background: {panel_border}; }}
QLabel#AppTitle {{
    color: {text};
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 4px;
}}
QLabel#SectionLabel {{
    color: {text_muted};
    font-size: 9px;
    letter-spacing: 3px;
    font-weight: bold;
    padding: 6px 0 2px 0;
}}
""".format(**C)


# ══════════════════════════════════════════════════════════════════════════════
# GLSL Shaders  (identical to original)
# ══════════════════════════════════════════════════════════════════════════════

VERTEX_SHADER_DEPTH = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec4 posScale;
layout(location = 5) in float quantity;
layout(location = 6) in float weight;

uniform mat4 projection;
uniform mat4 view;
uniform float globalScale;

out vec3 vWorldPosition;
flat out vec2 vDataValue;

void main() {
    vec3 scaledPos = position * globalScale * posScale.w;
    vec3 worldPos  = scaledPos + posScale.xyz;
    vWorldPosition = worldPos;
    vDataValue     = vec2(quantity * weight, weight) / (posScale.w * posScale.w);
    gl_Position    = projection * view * vec4(worldPos, 1.0);
}
"""

FRAGMENT_SHADER_DEPTH = """
#version 330 core
in  vec3 vWorldPosition;
flat in  vec2 vDataValue;
uniform vec3 cameraPosition;
out vec4 FragColor;
void main() {
    float d = distance(vWorldPosition, cameraPosition);
    FragColor = vec4(d * vDataValue.x, d * vDataValue.y, 0.0, 1.0);
}
"""

SCREEN_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 position;
out vec2 vUv;
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
out vec4 FragColor;
void main() {
    vec2  data  = texture(depthTexture, vUv).rg;
    float qw    = data.r;
    float w     = data.g;
    if (w == 0.0) discard;
    const float INV_LOG10 = 0.4342944819;
    float depth = log(qw / w) * INV_LOG10;
    float t     = (depth - minVal) / (maxVal - minVal);
    vec4 color  = texture(colormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(underColor, color, step(0.0, t));
    color = mix(color, overColor,  step(1.0, t));
    FragColor = color;
}
"""


# ══════════════════════════════════════════════════════════════════════════════
# Math helpers
# ══════════════════════════════════════════════════════════════════════════════

def perspective(fovy, aspect, near, far):
    f = 1.0 / np.tan(np.radians(fovy) / 2)
    m = np.zeros((4, 4), np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1
    return m


def look_at(eye, center, up):
    f = center - eye;  f /= np.linalg.norm(f)
    u = up / np.linalg.norm(up)
    s = np.cross(f, u); s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = s;  m[1, :3] = u;  m[2, :3] = -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


# ══════════════════════════════════════════════════════════════════════════════
# Render thread worker
# ══════════════════════════════════════════════════════════════════════════════

class RenderWorker(QObject):
    progress   = pyqtSignal(int)          # 0-100
    status_msg = pyqtSignal(str)
    finished   = pyqtSignal()
    error      = pyqtSignal(str)

    def __init__(self, gl_state, cam, params):
        super().__init__()
        self.gl_state  = gl_state   # dict with all compiled GL objects
        self.cam       = cam
        self.params    = params
        self._cancel   = False

    def cancel(self):
        self._cancel = True

    def run(self):
        p     = self.params
        N     = self.gl_state["N"]
        width, height = p["width"], p["height"]

        depth_prog  = self.gl_state["depth_prog"]
        screen_prog = self.gl_state["screen_prog"]
        fbo         = self.gl_state["fbo"]
        final_fbo   = self.gl_state["final_fbo"]
        accum_tex   = self.gl_state["accum_tex"]
        cmap_tex    = self.gl_state["cmap_tex"]
        cube_vao    = self.gl_state["cube_vao"]
        quad_vao    = self.gl_state["quad_vao"]

        cmd = [
            "ffmpeg", "-hide_banner", "-v", "error", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}", "-pix_fmt", "rgba",
            "-r", str(p["framerate"]), "-i", "-",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-crf", "22", "-preset", "fast",
            p["video_file"],
        ]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except FileNotFoundError:
            self.error.emit("ffmpeg not found – install ffmpeg and ensure it is on PATH.")
            return

        num_pbos = 2
        pbos = glGenBuffers(num_pbos)
        for pbo in pbos:
            glBindBuffer(GL_PIXEL_PACK_BUFFER, pbo)
            glBufferData(GL_PIXEL_PACK_BUFFER, width * height * 4, None, GL_STREAM_READ)
        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)

        pbo_index = 0
        total = len(self.cam)

        for i, row in enumerate(self.cam):
            if self._cancel:
                break
            x, y, z, cx, cy, cz, nx, ny, nz = row

            # Pass 1 – depth accumulation
            glBindFramebuffer(GL_FRAMEBUFFER, fbo)
            glViewport(0, 0, width, height)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glDisable(GL_DEPTH_TEST)

            glUseProgram(depth_prog)
            proj = perspective(60, width / height, 0.1, 100)
            view = look_at(np.array([x, y, z]),
                           np.array([cx, cy, cz]),
                           np.array([nx, ny, nz]))
            glUniformMatrix4fv(glGetUniformLocation(depth_prog, "projection"), 1, GL_FALSE, proj.T)
            glUniformMatrix4fv(glGetUniformLocation(depth_prog, "view"),       1, GL_FALSE, view.T)
            glUniform3f(glGetUniformLocation(depth_prog, "cameraPosition"), x, y, z)
            glUniform1f(glGetUniformLocation(depth_prog, "globalScale"), 1.0)
            glBindVertexArray(cube_vao)
            glDrawElementsInstanced(GL_TRIANGLES, 36, GL_UNSIGNED_INT, None, N)

            # Pass 2 – tone-map to final FBO
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
            glUniform1f(glGetUniformLocation(screen_prog, "minVal"), p["minVal"])
            glUniform1f(glGetUniformLocation(screen_prog, "maxVal"), p["maxVal"])
            glUniform4f(glGetUniformLocation(screen_prog, "underColor"), *p["underColor"])
            glUniform4f(glGetUniformLocation(screen_prog, "overColor"),  *p["overColor"])
            glBindVertexArray(quad_vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

            # Double-buffered PBO readback
            next_pbo = (pbo_index + 1) % num_pbos
            glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
            glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, ctypes.c_void_p(0))
            glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[next_pbo])
            ptr = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, width * height * 4, GL_MAP_READ_BIT)
            if ptr and i > 0:
                buf = ctypes.string_at(ptr, width * height * 4)
                proc.stdin.write(buf)
            if ptr:
                glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
            glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
            pbo_index = next_pbo

            self.progress.emit(int((i + 1) / total * 100))
            self.status_msg.emit(f"Frame {i + 1} / {total}")

        # Flush last frame
        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
        ptr = glMapBuffer(GL_PIXEL_PACK_BUFFER, GL_READ_ONLY)
        if ptr:
            buf = ctypes.string_at(ptr, len(self.cam) > 0 and width * height * 4 or 0)
            if buf:
                proc.stdin.write(buf)
            glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)

        glDeleteBuffers(num_pbos, pbos)
        proc.stdin.close()
        proc.wait()
        self.finished.emit()


# ══════════════════════════════════════════════════════════════════════════════
# Memory estimation helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_bytes(b):
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def query_system_memory():
    """Return (free_ram, total_ram) in bytes, or (None, None) if psutil missing."""
    if psutil is None:
        return None, None
    vm = psutil.virtual_memory()
    return vm.available, vm.total


def query_vram():
    """
    Return (free_vram, total_vram, method) in bytes.
    Tries NVIDIA NV_query_memory_info, then AMD ATI_meminfo.
    Returns (None, None, 'unknown') if neither works.
    GL context must be current when called.
    """
    NV_TOTAL, NV_FREE = 0x9047, 0x9049
    try:
        free_kb  = glGetIntegerv(NV_FREE)
        total_kb = glGetIntegerv(NV_TOTAL)
        while glGetError() != GL_NO_ERROR:
            pass
        if free_kb and int(free_kb) > 0:
            return int(free_kb) * 1024, int(total_kb) * 1024, "NVIDIA"
    except Exception:
        pass
    while glGetError() != GL_NO_ERROR:
        pass

    AMD_FREE = 0x87FC
    try:
        info = glGetIntegerv(AMD_FREE)
        free_kb = int(info[0]) if hasattr(info, "__len__") else int(info)
        while glGetError() != GL_NO_ERROR:
            pass
        if free_kb > 0:
            return free_kb * 1024, None, "AMD"
    except Exception:
        pass
    while glGetError() != GL_NO_ERROR:
        pass

    return None, None, "unknown"


def estimate_load_memory(N_file, N_load=None):
    """
    Estimate RAM peak and VRAM steady-state for loading N_load points
    from a file that contains N_file points total.

    RAM peak  = index array N_file*8 (int64, only when N_load < N_file)
              + 6 column copies N_load*24
              + column_stack tmp N_load*16
    VRAM      = 3 GPU buffers (x,y,z,dx) + qty + w = N_load * 24 bytes
    """
    if N_load is None:
        N_load = N_file
    capping     = N_load < N_file
    ram_peak    = (N_file * 8 if capping else 0) + N_load * 24 + N_load * 16
    vram_steady = N_load * 24
    return ram_peak, vram_steady


# ══════════════════════════════════════════════════════════════════════════════
# OpenGL preview widget
# ══════════════════════════════════════════════════════════════════════════════

class VolumeGLWidget(QOpenGLWidget):
    gl_ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # GL objects – populated in initializeGL / load_data
        self.depth_prog  = None
        self.screen_prog = None
        self.fbo = self.final_fbo = None
        self.accum_tex = self.cmap_tex = None
        self.cube_vao = self.quad_vao = None
        self.N = 0

        # Render state
        self.cam_frame    = None   # single (9,) row
        self.render_w     = 1280
        self.render_h     = 720
        self.minVal       = -3.0
        self.maxVal       =  3.0
        self.underColor   = (0.0, 0.0, 0.0, 1.0)
        self.overColor    = (1.0, 1.0, 1.0, 1.0)
        self.colormap_name = "inferno"
        self.data_loaded = False
        self._fbo_size   = (0, 0)
        self.N_total     = 0    # full point count after load
        self.preview_N   = 0    # active count used in preview draw calls

    # ── GL lifecycle ──────────────────────────────────────────────────────────

    def initializeGL(self):
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_ONE, GL_ONE)
        glClearColor(0.05, 0.05, 0.08, 1.0)

        self.depth_prog = shaders.compileProgram(
            shaders.compileShader(VERTEX_SHADER_DEPTH,   GL_VERTEX_SHADER),
            shaders.compileShader(FRAGMENT_SHADER_DEPTH, GL_FRAGMENT_SHADER),
        )
        self.screen_prog = shaders.compileProgram(
            shaders.compileShader(SCREEN_VERTEX_SHADER,    GL_VERTEX_SHADER),
            shaders.compileShader(SCREEN_FRAGMENT_SHADER,  GL_FRAGMENT_SHADER),
        )
        self._build_quad()
        self.gl_ready.emit()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        # QOpenGLWidget does NOT render to framebuffer 0 -- it composites
        # via its own internal FBO. Binding 0 goes to the real screen and
        # is invisible inside the widget. Always use defaultFramebufferObject().
        default_fbo = self.defaultFramebufferObject()

        glBindFramebuffer(GL_FRAMEBUFFER, default_fbo)
        glViewport(0, 0, self.width(), self.height())
        glClearColor(0.05, 0.05, 0.08, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        if not self.data_loaded or self.cam_frame is None:
            return

        # FBO matches widget pixel dimensions exactly
        rw = self.width()
        rh = self.height()
        self._ensure_fbos(rw, rh)

        x, y, z, cx, cy, cz, nx, ny, nz = self.cam_frame

        # Pass 1 -- accumulate weighted depth into RG32F offscreen FBO
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glViewport(0, 0, rw, rh)
        glClearColor(0, 0, 0, 0)
        glClear(GL_COLOR_BUFFER_BIT)  # no depth attachment on this FBO
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_ONE, GL_ONE)

        glUseProgram(self.depth_prog)
        proj = perspective(60, rw / rh, 0.1, 100)
        view = look_at(np.array([x, y, z]),
                       np.array([cx, cy, cz]),
                       np.array([nx, ny, nz]))
        glUniformMatrix4fv(glGetUniformLocation(self.depth_prog, "projection"), 1, GL_FALSE, proj.T)
        glUniformMatrix4fv(glGetUniformLocation(self.depth_prog, "view"),       1, GL_FALSE, view.T)
        glUniform3f(glGetUniformLocation(self.depth_prog, "cameraPosition"), x, y, z)
        glUniform1f(glGetUniformLocation(self.depth_prog, "globalScale"), 1.0)
        glBindVertexArray(self.cube_vao)
        glDrawElementsInstanced(GL_TRIANGLES, 36, GL_UNSIGNED_INT, None, self.preview_N)

        # Unbind the offscreen FBO BEFORE sampling its texture in Pass 2.
        # Reading a texture while it is still attached to the bound FBO is
        # undefined behaviour in OpenGL.
        glBindFramebuffer(GL_FRAMEBUFFER, default_fbo)

        # Pass 2 -- tone-map accum_tex onto the widget surface
        glViewport(0, 0, rw, rh)
        glDisable(GL_BLEND)
        glClearColor(0.05, 0.05, 0.08, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        glUseProgram(self.screen_prog)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.accum_tex)
        glUniform1i(glGetUniformLocation(self.screen_prog, "depthTexture"), 0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.cmap_tex)
        glUniform1i(glGetUniformLocation(self.screen_prog, "colormap"), 1)
        glUniform1f(glGetUniformLocation(self.screen_prog, "minVal"), self.minVal)
        glUniform1f(glGetUniformLocation(self.screen_prog, "maxVal"), self.maxVal)
        glUniform4f(glGetUniformLocation(self.screen_prog, "underColor"), *self.underColor)
        glUniform4f(glGetUniformLocation(self.screen_prog, "overColor"),  *self.overColor)
        glBindVertexArray(self.quad_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)


    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_fbos(self, w, h):
        if self._fbo_size == (w, h):
            return
        # Delete old objects (if any)
        if self.fbo is not None:
            glDeleteFramebuffers(1, [self.fbo])
        if self.accum_tex is not None:
            glDeleteTextures(1, [self.accum_tex])

        # Accumulation FBO (RG32F) – no depth attachment needed (depth test is disabled)
        self.accum_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.accum_tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RG32F, w, h, 0, GL_RG, GL_FLOAT, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glBindTexture(GL_TEXTURE_2D, 0)

        self.fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_2D, self.accum_tex, 0)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"Accumulation FBO incomplete: {status:#x}")
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

        self._fbo_size = (w, h)

    def _build_quad(self):
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32)
        self.quad_vao = glGenVertexArrays(1)
        glBindVertexArray(self.quad_vao)
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, quad.nbytes, quad, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 2, GL_FLOAT, False, 0, None)
        glEnableVertexAttribArray(0)

    def _build_cube(self):
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

    # ── Public API ────────────────────────────────────────────────────────────

    def load_volume(self, data_file, max_points=None):
        """Load raw binary volume data, shuffle for even subsampling, upload to GPU.

        max_points  -- if set, only this many points are read from disk and
                       uploaded to VRAM.  The cap is applied BEFORE the shuffle
                       so we pick a spatially representative random subset and
                       never touch the rest of the file.
        """
        self.makeCurrent()

        # Use memmap to read only the metadata (file size) without loading
        # the full array into RAM, then decide how many points to keep.
        mm = np.memmap(data_file, dtype=np.float32, mode="r")
        N_file = mm.size // 6
        del mm  # release the mapping immediately

        if max_points is None or max_points >= N_file:
            N_load = N_file
        else:
            N_load = max(1, int(max_points))

        # Pick N_load random indices from [0, N_file) WITHOUT loading the
        # full file.  Then sort them so we can read each column in one
        # contiguous pass (much faster than random-access reads).
        rng = np.random.default_rng(0)
        if N_load < N_file:
            chosen = np.sort(rng.choice(N_file, size=N_load, replace=False))
        else:
            chosen = np.arange(N_file)

        # Read each of the 6 columns (each N_file floats long) and
        # immediately index with `chosen` to keep only the selected rows.
        cols = []
        for i in range(6):
            col_mm = np.memmap(data_file, dtype=np.float32, mode="r",
                               offset=int(i * N_file * 4),
                               shape=(N_file,))
            cols.append(col_mm[chosen].copy())  # copy out of the mmap
            del col_mm
        x, y, z, dx, qty, w = cols
        N = len(x)

        # Shuffle the loaded subset so any further prefix [0:k] is also
        # a representative subsample (used by the preview points slider).
        perm = rng.permutation(N)
        x, y, z, dx, qty, w = (a[perm] for a in (x, y, z, dx, qty, w))

        instance_data = np.column_stack([x, y, z, dx]).astype(np.float32)

        self.cube_vao = self._build_cube()
        glBindVertexArray(self.cube_vao)

        mvbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, mvbo)
        glBufferData(GL_ARRAY_BUFFER, instance_data.nbytes, instance_data, GL_STATIC_DRAW)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 4, GL_FLOAT, False, 0, None)
        glVertexAttribDivisor(1, 1)

        for loc, arr in zip([5, 6], [qty, w]):
            vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            glBufferData(GL_ARRAY_BUFFER, arr.nbytes, arr, GL_STATIC_DRAW)
            glVertexAttribPointer(loc, 1, GL_FLOAT, False, 0, None)
            glEnableVertexAttribArray(loc)
            glVertexAttribDivisor(loc, 1)

        self.N_total   = N
        self.preview_N = N   # start at 100%
        self.data_loaded = True
        self.doneCurrent()

    def update_colormap(self, name):
        self.makeCurrent()
        self.colormap_name = name
        cmap = plt.get_cmap(name, 256)
        data = (cmap(np.linspace(0, 1, 256)) * 255).astype(np.uint8)
        if self.cmap_tex is None:
            self.cmap_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.cmap_tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 256, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        self.doneCurrent()
        self.update()

    def set_frame(self, cam_row):
        self.cam_frame = cam_row
        self.update()

    def get_gl_state(self):
        return {
            "depth_prog":  self.depth_prog,
            "screen_prog": self.screen_prog,
            "fbo":         self.fbo,
            "final_fbo":   getattr(self, "final_fbo", None),
            "accum_tex":   self.accum_tex,
            "cmap_tex":    self.cmap_tex,
            "cube_vao":    self.cube_vao,
            "quad_vao":    self.quad_vao,
            "N":           self.N_total,   # export always uses all points
        }


# ══════════════════════════════════════════════════════════════════════════════
# Helper widgets
# ══════════════════════════════════════════════════════════════════════════════

def section_label(text):
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    return lbl


def file_picker_row(label_text, placeholder, callback):
    """Returns (row_widget, line_edit)."""
    row = QWidget()
    hl  = QHBoxLayout(row)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(4)
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    btn = QPushButton("···")
    btn.setFixedWidth(32)
    btn.setToolTip(f"Browse for {label_text}")
    btn.clicked.connect(callback)
    hl.addWidget(le)
    hl.addWidget(btn)
    return row, le


def color_button(rgba):
    btn = QPushButton()
    btn.setFixedSize(28, 22)
    r, g, b, a = [int(v * 255) for v in rgba]
    btn.setStyleSheet(
        f"QPushButton {{ background: rgba({r},{g},{b},{a}); border: 1px solid #1e1e2e; }}"
        f"QPushButton:hover {{ border: 1px solid #5c7cfa; }}"
    )
    return btn


# ══════════════════════════════════════════════════════════════════════════════
# Main window
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VOLUME RENDERER")
        self.resize(1400, 860)

        self.cam_data     = None
        self.render_thread = None
        self.render_worker = None
        self._under_rgba  = (0.0, 0.0, 0.0, 1.0)
        self._over_rgba   = (1.0, 1.0, 1.0, 1.0)

        self._build_ui()
        self._connect_signals()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Toolbar ──
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        title = QLabel("VOLUME RENDERER")
        title.setObjectName("AppTitle")
        tb.addWidget(title)
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.addToolBar(tb)

        # ── Status bar ──
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready  ·  load a data file to begin")

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.status.addPermanentWidget(self.progress_bar)

        # ── Central splitter ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # ── Left: GL preview ──
        self.gl_widget = VolumeGLWidget()
        self.gl_widget.gl_ready.connect(self._on_gl_ready)

        preview_wrap = QWidget()
        pvl = QVBoxLayout(preview_wrap)
        pvl.setContentsMargins(0, 0, 0, 0)
        pvl.setSpacing(0)

        # frame scrubber
        scrub_row = QWidget()
        scrub_row.setFixedHeight(36)
        scrub_row.setStyleSheet(f"background:{C['panel']}; border-bottom:1px solid {C['panel_border']};")
        sl = QHBoxLayout(scrub_row)
        sl.setContentsMargins(8, 4, 8, 4)
        self.frame_label = QLabel("FRAME  —")
        self.frame_label.setObjectName("SectionLabel")
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(0)
        self.frame_slider.setEnabled(False)
        sl.addWidget(self.frame_label)
        sl.addWidget(self.frame_slider, 1)

        # Downsample separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f'color: {C["panel_border"]};')
        sl.addWidget(sep)

        ds_lbl = QLabel('POINTS')
        ds_lbl.setObjectName('SectionLabel')
        ds_lbl.setStyleSheet('padding: 0;')
        sl.addWidget(ds_lbl)

        self.ds_slider = QSlider(Qt.Horizontal)
        self.ds_slider.setMinimum(1)    # 1% .. 100% of total points
        self.ds_slider.setMaximum(100)
        self.ds_slider.setValue(100)    # default: all points
        self.ds_slider.setFixedWidth(100)
        self.ds_slider.setToolTip('Preview point subsample. Drag left to use fewer points (faster, less VRAM). Export always uses 100%.')
        sl.addWidget(self.ds_slider)

        self.ds_label = QLabel('100%')
        self.ds_label.setObjectName('SectionLabel')
        self.ds_label.setFixedWidth(38)
        self.ds_label.setStyleSheet('padding: 0; text-align: right;')
        sl.addWidget(self.ds_label)

        pvl.addWidget(scrub_row)
        pvl.addWidget(self.gl_widget, 1)

        # ── Right: control panel ──
        ctrl_scroll = QScrollArea()
        ctrl_scroll.setWidgetResizable(True)
        ctrl_scroll.setFixedWidth(310)
        ctrl_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        ctrl_inner = QWidget()
        ctrl_scroll.setWidget(ctrl_inner)
        vl = QVBoxLayout(ctrl_inner)
        vl.setContentsMargins(10, 10, 10, 10)
        vl.setSpacing(4)

        # ── FILES group ──
        grp_files = QGroupBox("FILES")
        gfl = QVBoxLayout(grp_files)
        gfl.setSpacing(6)

        gfl.addWidget(section_label("DATA FILE  (.bin / raw float32)"))
        row_df, self.le_data = file_picker_row("data file", "x y z dx qty w  ×  N", self._browse_data)
        gfl.addWidget(row_df)

        gfl.addWidget(section_label("CAMERA PATH  (.txt)"))
        row_cf, self.le_cam = file_picker_row("camera file", "x y z  cx cy cz  nx ny nz", self._browse_cam)
        gfl.addWidget(row_cf)
        self.lbl_mem_info = QLabel("")
        self.lbl_mem_info.setWordWrap(True)
        self.lbl_mem_info.setStyleSheet(
            "font-size:10px; font-family:'Courier New',monospace;"
            f"color:{C['text_dim']}; padding:4px 0;")
        gfl.addWidget(self.lbl_mem_info)

        gfl.addWidget(section_label("MAX POINTS TO LOAD"))
        mp_row = QWidget()
        mp_hl  = QHBoxLayout(mp_row)
        mp_hl.setContentsMargins(0, 0, 0, 0)
        mp_hl.setSpacing(4)
        self.chk_max_pts = QCheckBox("cap at")
        self.spin_max_pts = QSpinBox()
        self.spin_max_pts.setRange(1000, 2_000_000_000)
        self.spin_max_pts.setValue(10_000_000)
        self.spin_max_pts.setSingleStep(1_000_000)
        self.spin_max_pts.setGroupSeparatorShown(True)
        self.spin_max_pts.setEnabled(False)
        self.spin_max_pts.setToolTip(
            "Hard cap on points loaded into RAM and VRAM.\n"
            "Points are chosen randomly (seed=0) so the result\n"
            "is a spatially representative subsample.")
        mp_hl.addWidget(self.chk_max_pts)
        mp_hl.addWidget(self.spin_max_pts, 1)
        gfl.addWidget(mp_row)

        self.btn_load = QPushButton("▶  LOAD FILES")
        self.btn_load.setProperty("role", "primary")
        self.btn_load.setEnabled(False)
        gfl.addWidget(self.btn_load)
        vl.addWidget(grp_files)

        # ── RENDER SETTINGS group ──
        grp_rend = QGroupBox("EXPORT RESOLUTION")
        grl = QGridLayout(grp_rend)
        grl.setVerticalSpacing(6)
        grl.setHorizontalSpacing(8)

        grl.addWidget(section_label("RESOLUTION"), 0, 0, 1, 2)
        self.spin_w = QSpinBox(); self.spin_w.setRange(64, 7680); self.spin_w.setValue(1280)
        self.spin_h = QSpinBox(); self.spin_h.setRange(64, 4320); self.spin_h.setValue(720)
        grl.addWidget(QLabel("W"), 1, 0); grl.addWidget(self.spin_w, 1, 1)
        grl.addWidget(QLabel("H"), 2, 0); grl.addWidget(self.spin_h, 2, 1)

        grl.addWidget(section_label("FRAMERATE"), 3, 0, 1, 2)
        self.spin_fps = QSpinBox(); self.spin_fps.setRange(1, 240); self.spin_fps.setValue(30)
        grl.addWidget(QLabel("FPS"), 4, 0); grl.addWidget(self.spin_fps, 4, 1)
        vl.addWidget(grp_rend)

        # ── COLORMAP group ──
        grp_cmap = QGroupBox("COLORMAP")
        gcl = QVBoxLayout(grp_cmap)
        gcl.setSpacing(6)

        self.combo_cmap = QComboBox()
        colormaps = ["inferno", "magma", "plasma", "viridis", "cividis",
                     "hot", "coolwarm", "RdBu_r", "turbo", "jet", "gray"]
        self.combo_cmap.addItems(colormaps)
        gcl.addWidget(self.combo_cmap)

        gcl.addWidget(section_label("VALUE RANGE  (log₁₀)"))
        rng_row = QWidget()
        rng_hl  = QHBoxLayout(rng_row); rng_hl.setContentsMargins(0,0,0,0); rng_hl.setSpacing(4)
        self.spin_min = QDoubleSpinBox(); self.spin_min.setRange(-20, 20); self.spin_min.setValue(-3.0); self.spin_min.setSingleStep(0.5)
        self.spin_max = QDoubleSpinBox(); self.spin_max.setRange(-20, 20); self.spin_max.setValue(3.0);  self.spin_max.setSingleStep(0.5)
        rng_hl.addWidget(QLabel("min")); rng_hl.addWidget(self.spin_min)
        rng_hl.addWidget(QLabel("max")); rng_hl.addWidget(self.spin_max)
        gcl.addWidget(rng_row)

        gcl.addWidget(section_label("CLAMP COLORS"))
        color_row = QWidget()
        chr_hl = QHBoxLayout(color_row); chr_hl.setContentsMargins(0,0,0,0); chr_hl.setSpacing(6)
        self.btn_under_color = color_button(self._under_rgba)
        self.btn_over_color  = color_button(self._over_rgba)
        chr_hl.addWidget(QLabel("under")); chr_hl.addWidget(self.btn_under_color)
        chr_hl.addStretch()
        chr_hl.addWidget(QLabel("over"));  chr_hl.addWidget(self.btn_over_color)
        gcl.addWidget(color_row)
        vl.addWidget(grp_cmap)

        # ── EXPORT group ──
        grp_exp = QGroupBox("EXPORT")
        gel = QVBoxLayout(grp_exp)
        gel.setSpacing(6)

        gel.addWidget(section_label("OUTPUT FILE"))
        row_vf, self.le_video = file_picker_row("video output", "output.mp4", self._browse_video)
        self.le_video.setText("output.mp4")
        gel.addWidget(row_vf)

        self.btn_render = QPushButton("⬛  RENDER VIDEO")
        self.btn_render.setProperty("role", "success")
        self.btn_render.setEnabled(False)
        gel.addWidget(self.btn_render)

        self.btn_cancel = QPushButton("✕  CANCEL")
        self.btn_cancel.setProperty("role", "danger")
        self.btn_cancel.setVisible(False)
        gel.addWidget(self.btn_cancel)
        vl.addWidget(grp_exp)

        vl.addStretch(1)

        # ── Assemble ──
        splitter.addWidget(preview_wrap)
        splitter.addWidget(ctrl_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        self.setCentralWidget(splitter)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.le_data.textChanged.connect(self._check_load_ready)
        self.le_data.textChanged.connect(self._on_data_file_changed)
        self.le_cam.textChanged.connect(self._check_load_ready)
        self.btn_load.clicked.connect(self._load_files)
        self.btn_render.clicked.connect(self._start_render)
        self.btn_cancel.clicked.connect(self._cancel_render)

        self.combo_cmap.currentTextChanged.connect(self._on_cmap_changed)
        self.spin_min.valueChanged.connect(self._on_range_changed)
        self.spin_max.valueChanged.connect(self._on_range_changed)
        self.frame_slider.valueChanged.connect(self._on_frame_changed)

        self.chk_max_pts.toggled.connect(self.spin_max_pts.setEnabled)
        self.ds_slider.valueChanged.connect(self._on_ds_changed)
        self.btn_under_color.clicked.connect(lambda: self._pick_color("under"))
        self.btn_over_color.clicked.connect(lambda: self._pick_color("over"))

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_ds_changed(self, val):
        """val is 1..100 (percent of total points to use in preview)."""
        if self.gl_widget.N_total == 0:
            return
        self.gl_widget.preview_N = max(1, int(self.gl_widget.N_total * val / 100))
        self.ds_label.setText(f'{val}%')
        if self.gl_widget.data_loaded:
            self.gl_widget.update()

    def _on_data_file_changed(self, path):
        """Update the memory info label whenever the data file path changes."""
        self.lbl_mem_info.setText("")
        if not path or not os.path.exists(path):
            return
        try:
            file_bytes = os.path.getsize(path)
            N_file = file_bytes // (6 * 4)
        except OSError:
            return
        free_ram, total_ram = query_system_memory()
        ram_peak, vram_need = estimate_load_memory(N_file)
        lines = [f"File   : {_fmt_bytes(file_bytes)}  ({N_file:,} pts)"]
        if total_ram:
            pct = ram_peak / total_ram * 100
            lines.append(f"RAM    : ~{_fmt_bytes(ram_peak)} peak  ({pct:.0f}% of total)")
        else:
            lines.append(f"RAM    : ~{_fmt_bytes(ram_peak)} peak")
        lines.append(f"VRAM   : ~{_fmt_bytes(vram_need)} steady")
        warn = []
        if free_ram is not None and ram_peak > free_ram * 0.85:
            warn.append("LOW RAM")
        color = C["danger"] if warn else C["success"] if free_ram else C["text_dim"]
        suffix = "  ⚠ " + " / ".join(warn) if warn else ""
        self.lbl_mem_info.setStyleSheet(
            "font-size:10px; font-family:'Courier New',monospace;"
            f"color:{color}; padding:4px 0;")
        self.lbl_mem_info.setText("\n".join(lines) + suffix)

    def _on_gl_ready(self):
        self.status.showMessage("OpenGL context ready  ·  load a data file to begin")

    def _browse_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select data file", "", "Binary (*.bin *.dat *.raw);;All (*)")
        if path:
            self.le_data.setText(path)

    def _browse_cam(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select camera path", "", "Text (*.txt *.csv);;All (*)")
        if path:
            self.le_cam.setText(path)

    def _browse_video(self):
        path, _ = QFileDialog.getSaveFileName(self, "Output video", "output.mp4", "MP4 (*.mp4);;All (*)")
        if path:
            self.le_video.setText(path)

    def _check_load_ready(self):
        ok = bool(self.le_data.text()) and bool(self.le_cam.text())
        self.btn_load.setEnabled(ok)

    def _load_files(self):
        data_file = self.le_data.text()
        cam_file  = self.le_cam.text()

        if not os.path.exists(data_file):
            self.status.showMessage(f"Data file not found: {data_file}")
            return
        if not os.path.exists(cam_file):
            self.status.showMessage(f"Camera file not found: {cam_file}")
            return

        file_bytes = os.path.getsize(data_file)
        N_file     = file_bytes // (6 * 4)

        free_ram, _ = query_system_memory()
        self.gl_widget.makeCurrent()
        free_vram, total_vram, vram_src = query_vram()
        self.gl_widget.doneCurrent()

        max_pts = (self.spin_max_pts.value()
                   if self.chk_max_pts.isChecked() else None)

        # Auto-cap: largest N that fits in 80% of free RAM and VRAM
        auto_cap = None
        if free_ram is not None:
            limit = int(free_ram * 0.80 / 48)  # ram_peak ~ N*48 worst case
            if limit < N_file:
                auto_cap = limit
        if free_vram is not None:
            limit = int(free_vram * 0.80 / 24)  # vram = N*24
            if limit < N_file:
                auto_cap = min(auto_cap, limit) if auto_cap is not None else limit
        if max_pts is not None:
            auto_cap = min(auto_cap, max_pts) if auto_cap is not None else max_pts

        if auto_cap is not None and auto_cap < N_file and not self.chk_max_pts.isChecked():
            r_full, v_full = estimate_load_memory(N_file)
            r_cap,  v_cap  = estimate_load_memory(N_file, auto_cap)
            vl = f"VRAM ({vram_src})" if vram_src != "unknown" else "VRAM"
            msg_lines = [
                f"Loading all {N_file:,} points would require:",
                f"  RAM  peak : ~{_fmt_bytes(r_full)}" + (f"   (free: {_fmt_bytes(free_ram)})" if free_ram else ""),
                f"  {vl}  : ~{_fmt_bytes(v_full)}" + (f"   (free: {_fmt_bytes(free_vram)})" if free_vram else ""),
                "",
                "This may exceed available resources.",
                "",
                f"Auto-cap to {auto_cap:,} points?",
                f"  RAM  peak : ~{_fmt_bytes(r_cap)}",
                f"  {vl}  : ~{_fmt_bytes(v_cap)}",
                "",
                "Yes = cap  |  No = load all anyway  |  Cancel = abort",
            ]
            reply = QMessageBox.warning(
                self, "Memory Warning", "\n".join(msg_lines),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                max_pts = auto_cap

        cap_str = (f"  capped at {max_pts:,}" if max_pts else "")
        self.status.showMessage(f"Loading volume data {cap_str}...")
        QApplication.processEvents()

        try:
            self.gl_widget.load_volume(data_file, max_points=max_pts)
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))
            return

        try:
            self.cam_data = np.loadtxt(cam_file, dtype=np.float32)
            if self.cam_data.ndim == 1:
                self.cam_data = self.cam_data[np.newaxis, :]
        except Exception as e:
            QMessageBox.critical(self, "Camera file error", str(e))
            return

        n_frames = len(self.cam_data)
        self.frame_slider.setMaximum(max(0, n_frames - 1))
        self.frame_slider.setEnabled(True)
        self.frame_slider.setValue(0)

        # Upload default colormap
        self.gl_widget.update_colormap(self.combo_cmap.currentText())

        # Show first frame
        self.gl_widget.set_frame(self.cam_data[0])
        self.frame_label.setText(f"FRAME  0 / {n_frames - 1}")

        # Reset the points slider so preview_N matches the full dataset
        self.ds_slider.setValue(100)
        self.ds_label.setText('100%')

        self.btn_render.setEnabled(True)
        loaded = self.gl_widget.N_total
        _, vram_used = estimate_load_memory(N_file, loaded)
        pt_note = f"{loaded:,} / {N_file:,} pts" if max_pts else f"{loaded:,} pts"
        self.status.showMessage(
            f"Loaded  [{pt_note}]  VRAM ~{_fmt_bytes(vram_used)}  {n_frames} frames"
        )

    def _on_cmap_changed(self, name):
        if self.gl_widget.data_loaded:
            self.gl_widget.update_colormap(name)

    def _on_range_changed(self):
        self.gl_widget.minVal = self.spin_min.value()
        self.gl_widget.maxVal = self.spin_max.value()
        if self.gl_widget.data_loaded:
            self.gl_widget.update()

    def _on_frame_changed(self, idx):
        if self.cam_data is not None and 0 <= idx < len(self.cam_data):
            self.gl_widget.set_frame(self.cam_data[idx])
            n = len(self.cam_data)
            self.frame_label.setText(f"FRAME  {idx} / {n - 1}")

    def _pick_color(self, which):
        from PyQt5.QtWidgets import QColorDialog
        current = self._under_rgba if which == "under" else self._over_rgba
        r,g,b,a = [int(v*255) for v in current]
        init = QColor(r,g,b,a)
        col = QColorDialog.getColor(init, self, f"Pick {which} color",
                                    QColorDialog.ShowAlphaChannel)
        if col.isValid():
            rgba = (col.redF(), col.greenF(), col.blueF(), col.alphaF())
            if which == "under":
                self._under_rgba = rgba
                self.gl_widget.underColor = rgba
                self.btn_under_color.setStyleSheet(
                    f"QPushButton {{ background: rgba({col.red()},{col.green()},{col.blue()},{col.alpha()}); "
                    f"border: 1px solid #1e1e2e; }}"
                    f"QPushButton:hover {{ border: 1px solid #5c7cfa; }}"
                )
            else:
                self._over_rgba = rgba
                self.gl_widget.overColor = rgba
                self.btn_over_color.setStyleSheet(
                    f"QPushButton {{ background: rgba({col.red()},{col.green()},{col.blue()},{col.alpha()}); "
                    f"border: 1px solid #1e1e2e; }}"
                    f"QPushButton:hover {{ border: 1px solid #5c7cfa; }}"
                )
            if self.gl_widget.data_loaded:
                self.gl_widget.update()

    def _start_render(self):
        if self.cam_data is None:
            return

        rw = self.spin_w.value()
        rh = self.spin_h.value()

        # Build / resize the accumulation FBO at export resolution
        self.gl_widget.makeCurrent()
        self.gl_widget.render_w = rw
        self.gl_widget.render_h = rh
        self.gl_widget._ensure_fbos(rw, rh)

        # Separate RGBA8 FBO for the tone-mapped output (readback target)
        final_fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
        final_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, final_tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, rw, rh, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, final_tex, 0)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        self.gl_widget.doneCurrent()

        if status != GL_FRAMEBUFFER_COMPLETE:
            QMessageBox.critical(self, "GL error", f"Export FBO incomplete: {status:#x}")
            return

        gl_state = self.gl_widget.get_gl_state()
        gl_state["final_fbo"] = final_fbo

        params = {
            "width":      rw,
            "height":     rh,
            "framerate":  self.spin_fps.value(),
            "video_file": self.le_video.text() or "output.mp4",
            "minVal":     self.spin_min.value(),
            "maxVal":     self.spin_max.value(),
            "underColor": self._under_rgba,
            "overColor":  self._over_rgba,
        }

        self.render_worker = RenderWorker(gl_state, self.cam_data, params)
        self.render_worker.progress.connect(self._on_render_progress)
        self.render_worker.status_msg.connect(lambda m: self.status.showMessage(m))
        self.render_worker.finished.connect(self._on_render_done)
        self.render_worker.error.connect(self._on_render_error)

        self._render_iter = self._render_generator(self.render_worker)
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._render_step)
        self._render_timer.start(0)

        self.btn_render.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def _render_generator(self, worker):
        """Generator that yields one frame per step, keeping GL on main thread.

        IMPORTANT: We call makeCurrent() on every iteration because Qt may
        call paintGL() (which internally manages the context) between our
        yields, leaving the context unbound for us when we resume.
        """
        p     = worker.params
        N     = worker.gl_state["N"]
        width, height = p["width"], p["height"]
        depth_prog  = worker.gl_state["depth_prog"]
        screen_prog = worker.gl_state["screen_prog"]
        fbo         = worker.gl_state["fbo"]
        final_fbo   = worker.gl_state["final_fbo"]
        accum_tex   = worker.gl_state["accum_tex"]
        cmap_tex    = worker.gl_state["cmap_tex"]
        cube_vao    = worker.gl_state["cube_vao"]
        quad_vao    = worker.gl_state["quad_vao"]

        cmd = [
            "ffmpeg", "-hide_banner", "-v", "error", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}", "-pix_fmt", "rgba",
            "-r", str(p["framerate"]), "-i", "-",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-crf", "22", "-preset", "fast",
            p["video_file"],
        ]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except FileNotFoundError:
            worker.error.emit("ffmpeg not found – install ffmpeg and add it to PATH.")
            return

        # Allocate PBOs with context current
        self.gl_widget.makeCurrent()
        num_pbos = 2
        pbos = glGenBuffers(num_pbos)
        for pbo in pbos:
            glBindBuffer(GL_PIXEL_PACK_BUFFER, pbo)
            glBufferData(GL_PIXEL_PACK_BUFFER, width * height * 4, None, GL_STREAM_READ)
        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
        self.gl_widget.doneCurrent()

        pbo_index = 0
        total = len(worker.cam)

        for i, row in enumerate(worker.cam):
            if worker._cancel:
                break
            x, y, z, cx, cy, cz, nx, ny, nz = row

            # Re-acquire context every frame – Qt may have taken it for paintGL
            self.gl_widget.makeCurrent()

            # Pass 1 – accumulate into RG32F FBO
            glBindFramebuffer(GL_FRAMEBUFFER, fbo)
            glViewport(0, 0, width, height)
            glClearColor(0, 0, 0, 0)
            glClear(GL_COLOR_BUFFER_BIT)   # no depth attachment
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_ONE, GL_ONE)

            glUseProgram(depth_prog)
            proj = perspective(60, width / height, 0.1, 100)
            view = look_at(np.array([x,y,z]), np.array([cx,cy,cz]), np.array([nx,ny,nz]))
            glUniformMatrix4fv(glGetUniformLocation(depth_prog, "projection"), 1, GL_FALSE, proj.T)
            glUniformMatrix4fv(glGetUniformLocation(depth_prog, "view"),       1, GL_FALSE, view.T)
            glUniform3f(glGetUniformLocation(depth_prog, "cameraPosition"), x, y, z)
            glUniform1f(glGetUniformLocation(depth_prog, "globalScale"), 1.0)
            glBindVertexArray(cube_vao)
            glDrawElementsInstanced(GL_TRIANGLES, 36, GL_UNSIGNED_INT, None, N)

            # Unbind FBO before sampling its texture
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

            # Pass 2 – tone-map into the export FBO
            glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
            glViewport(0, 0, width, height)
            glClearColor(0, 0, 0, 1)
            glClear(GL_COLOR_BUFFER_BIT)
            glDisable(GL_BLEND)
            glUseProgram(screen_prog)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, accum_tex)
            glUniform1i(glGetUniformLocation(screen_prog, "depthTexture"), 0)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, cmap_tex)
            glUniform1i(glGetUniformLocation(screen_prog, "colormap"), 1)
            glUniform1f(glGetUniformLocation(screen_prog, "minVal"), p["minVal"])
            glUniform1f(glGetUniformLocation(screen_prog, "maxVal"), p["maxVal"])
            glUniform4f(glGetUniformLocation(screen_prog, "underColor"), *p["underColor"])
            glUniform4f(glGetUniformLocation(screen_prog, "overColor"),  *p["overColor"])
            glBindVertexArray(quad_vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

            # PBO double-buffered readback (reads from currently bound final_fbo)
            next_pbo = (pbo_index + 1) % num_pbos
            glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
            glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, ctypes.c_void_p(0))
            glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[next_pbo])
            ptr = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, width * height * 4, GL_MAP_READ_BIT)
            if ptr and i > 0:
                buf = ctypes.string_at(ptr, width * height * 4)
                proc.stdin.write(buf)
            if ptr:
                glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
            glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
            pbo_index = next_pbo

            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            self.gl_widget.doneCurrent()

            worker.progress.emit(int((i + 1) / total * 100))
            worker.status_msg.emit(f"Rendering  ·  frame {i + 1} / {total}")
            yield  # hand control back to Qt event loop

        # Flush the last in-flight PBO frame
        self.gl_widget.makeCurrent()
        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
        ptr = glMapBuffer(GL_PIXEL_PACK_BUFFER, GL_READ_ONLY)
        if ptr:
            buf = ctypes.string_at(ptr, width * height * 4)
            proc.stdin.write(buf)
            glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
        glDeleteBuffers(num_pbos, pbos)
        self.gl_widget.doneCurrent()

        proc.stdin.close()
        proc.wait()
        worker.finished.emit()

    def _render_step(self):
        try:
            next(self._render_iter)
        except StopIteration:
            self._render_timer.stop()

    def _on_render_progress(self, val):
        self.progress_bar.setValue(val)

    def _on_render_done(self):
        self._render_timer.stop()
        self.btn_render.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress_bar.setVisible(False)
        out = self.le_video.text() or "output.mp4"
        self.status.showMessage(f"✓  Render complete  ·  {out}")

    def _on_render_error(self, msg):
        self._render_timer.stop()
        self.btn_render.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Render error", msg)
        self.status.showMessage(f"Render failed  ·  {msg}")

    def _cancel_render(self):
        if self.render_worker:
            self.render_worker.cancel()


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Request OpenGL 3.3 Core
    from PyQt5.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setSamples(0)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setStyleSheet(SS)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()