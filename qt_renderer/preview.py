import numpy as np
import matplotlib.pyplot as plt

from PyQt5.QtWidgets import QOpenGLWidget, QSizePolicy

from PyQt5.QtCore import pyqtSignal

from OpenGL.GL import *
from OpenGL.GL import shaders

from qt_renderer.math import perspective, look_at
from qt_renderer.mem import query_vram
from qt_renderer.shaders import VERTEX_SHADER_DEPTH, FRAGMENT_SHADER_DEPTH, SCREEN_VERTEX_SHADER, SCREEN_FRAGMENT_SHADER

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
        self.vram_total  = None # cached at initializeGL, used for % estimates

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

        # Cache total VRAM once while the context is already current.
        # query_vram() returns (free, total, method); we only need total.
        _, self.vram_total, _ = query_vram()

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
        glUniform1i(glGetUniformLocation(self.screen_prog, "flipY"), 0)  # preview: no flip
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