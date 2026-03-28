import sys
import os
import ctypes
import subprocess

import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QSplitter, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSpinBox, QComboBox,
    QFileDialog, QGroupBox, QStatusBar, QToolBar,
    QProgressBar, QScrollArea, QCheckBox, QSlider, 
    QSizePolicy, QFrame, QMessageBox, QColorDialog
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QColor, QSurfaceFormat

from OpenGL.GL import *

from qt_renderer.helpers import section_label, file_picker_row, color_button
from qt_renderer.mem import _fmt_bytes, query_system_memory, estimate_load_memory, query_vram
from qt_renderer.palette import C, SS
from qt_renderer.math import look_at, perspective
from qt_renderer.preview import VolumeGLWidget

# ══════════════════════════════════════════════════════════════════════════════
# Main window
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VOLUME RENDERER")
        self.resize(1400, 860)

        self.cam_data       = None
        self._under_rgba    = (0.0, 0.0, 0.0, 1.0)
        self._over_rgba     = (1.0, 1.0, 1.0, 1.0)
        self._render_cancel = False

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
        vram_total = self.gl_widget.vram_total
        if vram_total:
            pct_v = vram_need / vram_total * 100
            lines.append(f"VRAM   : ~{_fmt_bytes(vram_need)} steady  ({pct_v:.0f}% of total)")
        else:
            lines.append(f"VRAM   : ~{_fmt_bytes(vram_need)} steady")
        warn = []
        if free_ram is not None and ram_peak > free_ram * 0.85:
            warn.append("LOW RAM")
        if vram_total and vram_need > vram_total * 0.85:
            warn.append("LOW VRAM")
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

        self._render_cancel = False
        self._render_iter   = self._render_generator(gl_state, self.cam_data, params)
        self._render_timer  = QTimer(self)
        self._render_timer.timeout.connect(self._render_step)
        self._render_timer.start(0)

        self.btn_render.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def _render_generator(self, gl_state, cam, params):
        """Generator that yields one frame per step, keeping GL on main thread.

        IMPORTANT: We call makeCurrent() on every iteration because Qt may
        call paintGL() (which internally manages the context) between our
        yields, leaving the context unbound for us when we resume.
        """
        p     = params
        N     = gl_state["N"]
        width, height = p["width"], p["height"]
        depth_prog  = gl_state["depth_prog"]
        screen_prog = gl_state["screen_prog"]
        fbo         = gl_state["fbo"]
        final_fbo   = gl_state["final_fbo"]
        accum_tex   = gl_state["accum_tex"]
        cmap_tex    = gl_state["cmap_tex"]
        cube_vao    = gl_state["cube_vao"]
        quad_vao    = gl_state["quad_vao"]

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
            self._on_render_error("ffmpeg not found – install ffmpeg and add it to PATH.")
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
        total = len(cam)

        for i, row in enumerate(cam):
            if self._render_cancel:
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
            glUniform1i(glGetUniformLocation(screen_prog, "flipY"), 1)  # export: flip for ffmpeg
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

            self._on_render_progress(int((i + 1) / total * 100))
            self.status.showMessage(f"Rendering  ·  frame {i + 1} / {total}")
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
        self._on_render_done()

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
        self._render_cancel = True


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Request OpenGL 3.3 Core
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