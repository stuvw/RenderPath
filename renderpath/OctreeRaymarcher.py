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


# ============================================================
# EGL CONTEXT
# ============================================================

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
        EGL.EGL_SURFACE_TYPE,     EGL.EGL_PBUFFER_BIT,
        EGL.EGL_RENDERABLE_TYPE,  EGL.EGL_OPENGL_BIT,
        EGL.EGL_RED_SIZE,   8,
        EGL.EGL_GREEN_SIZE, 8,
        EGL.EGL_BLUE_SIZE,  8,
        EGL.EGL_ALPHA_SIZE, 8,
        EGL.EGL_NONE
    ]

    config = EGL.EGLConfig()
    num = ctypes.c_int()
    if not EGL.eglChooseConfig(
        display,
        (EGL.EGLint * len(config_attribs))(*config_attribs),
        ctypes.byref(config), 1, ctypes.byref(num),
    ):
        raise RuntimeError("eglChooseConfig failed")
    if num.value == 0:
        raise RuntimeError("No EGL configs found")

    pbuffer_attribs = [EGL.EGL_WIDTH, width, EGL.EGL_HEIGHT, height, EGL.EGL_NONE]
    surface = EGL.eglCreatePbufferSurface(
        display, config,
        (EGL.EGLint * len(pbuffer_attribs))(*pbuffer_attribs)
    )

    EGL.eglBindAPI(EGL.EGL_OPENGL_API)

    ctx_attribs = [
        EGL.EGL_CONTEXT_MAJOR_VERSION, 4,
        EGL.EGL_CONTEXT_MINOR_VERSION, 3,          # need 4.3 for SSBOs / compute
        EGL.EGL_CONTEXT_OPENGL_PROFILE_MASK,
        EGL.EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT,
        EGL.EGL_NONE
    ]
    ctx = EGL.eglCreateContext(
        display, config, EGL.EGL_NO_CONTEXT,
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


# ============================================================
# OCTREE BUILDER  (CPU side)
# ============================================================

def build_octree(x, y, z, qty, w, max_depth):
    """
    Build a linearised sparse voxel octree from point-cloud data.

    Strategy: level-by-level, fully vectorised with numpy.
    At each depth we assign every particle a Morton-like node index,
    sort by that index, then use np.unique + np.add.at to accumulate
    all particles into their nodes in one pass — no Python loop over
    particles at any level.

    Node layout (flat arrays, indices are stable across levels):
        node_min  : (M,3) float32   lower-left corner
        node_size : (M,)  float32   side length
        node_data : (M,2) float32   (sum_qw, sum_w)  — leaf values only;
                                    interior nodes are filled bottom-up
        children  : (M,8) int32     child indices, -1 = absent
    """
    print("[INFO]: Building octree (vectorised)...")
    t0 = time()

    # ---- domain ----
    pad = 1e-6
    lo = np.array([x.min(), y.min(), z.min()], np.float64) - pad
    hi = np.array([x.max(), y.max(), z.max()], np.float64) + pad
    root_size = float(np.max(hi - lo))
    root_min  = (lo + hi) * 0.5 - root_size * 0.5

    pts = np.stack([x, y, z], axis=1).astype(np.float64)   # (N,3)
    qw  = (qty * w).astype(np.float64)
    wt  = w.astype(np.float64)

    # ---- pre-allocate node storage ----
    # Upper bound on nodes: sum_{d=0}^{max_depth} 8^d — but with 65 M
    # particles and depth 6 the real count is vastly smaller.
    # We grow two Python lists (one entry per level) then vstack at the end.
    all_node_min  = []   # list of (k,3) arrays per level
    all_node_size = []   # list of (k,)  arrays per level
    all_node_data = []   # list of (k,2) arrays per level  (filled bottom-up)
    all_children  = []   # list of (k,8) arrays per level

    # node_base[d] = index of first node at depth d in the flat array
    node_base = []
    total_nodes = 0

    # ---- per-particle state: which node does each particle belong to? ----
    # Represented as integer grid coords at the current level's resolution.
    # At depth d the grid has 2^d cells per axis.
    # particle_node[i] = flat node index within the current level's node list.

    # Initialise: depth 0, all particles in the single root cell.
    # Grid coord at depth 0 is always (0,0,0).
    grid_res   = 1                              # 2^depth cells per axis
    cell_size  = root_size                      # world size of one cell
    # integer grid coordinates of each particle (updated each level)
    p_ix = np.zeros(len(pts), np.int64)
    p_iy = np.zeros(len(pts), np.int64)
    p_iz = np.zeros(len(pts), np.int64)

    # level_node_ids[d] maps (ix,iy,iz) → local node index within depth d
    # We store it as the sorted unique keys and use searchsorted for lookup.

    prev_level_nodes = None   # (K, 3) int64 — unique grid coords at prev depth

    for depth in range(max_depth + 1):
        t_lev = time()

        # unique nodes at this depth: each unique (ix,iy,iz) triple
        node_coords_per_particle = np.stack([p_ix, p_iy, p_iz], axis=1)  # (N,3)

        # pack into a single int64 key for fast unique (ix < 2^depth ≤ 2^20)
        # safe up to depth 20
        shift = max_depth + 1   # bits per axis — enough for any depth we'll see
        keys  = p_ix * (1 << (2 * shift)) + p_iy * (1 << shift) + p_iz

        sort_idx   = np.argsort(keys, kind='stable')
        sorted_keys = keys[sort_idx]
        uniq_keys, first_occ, inv = np.unique(sorted_keys,
                                               return_index=True,
                                               return_inverse=True)
        K = len(uniq_keys)   # number of non-empty nodes at this depth

        # decode unique keys back to grid coords
        uniq_ix = (uniq_keys >> (2 * shift)).astype(np.int64)
        uniq_iy = ((uniq_keys >> shift) & ((1 << shift) - 1)).astype(np.int64)
        uniq_iz = (uniq_keys & ((1 << shift) - 1)).astype(np.int64)

        # world-space lower corners
        n_min = (root_min + np.stack([uniq_ix, uniq_iy, uniq_iz], axis=1)
                 * cell_size).astype(np.float32)
        n_size = np.full(K, cell_size, np.float32)

        # accumulate particle values into nodes (vectorised scatter-add)
        n_data = np.zeros((K, 2), np.float64)
        # inv gives local node index for each particle in sorted order;
        # we need to map back via sort_idx
        local_node_idx = np.empty(len(pts), np.int64)
        local_node_idx[sort_idx] = inv
        np.add.at(n_data[:, 0], local_node_idx, qw)
        np.add.at(n_data[:, 1], local_node_idx, wt)

        n_children = np.full((K, 8), -1, np.int32)

        # If not the first level, wire parent→child links.
        # Parent grid coords = floor(child coords / 2).
        if depth > 0 and prev_level_nodes is not None:
            parent_base = node_base[-1]
            # For each unique node at this depth, compute parent grid coord
            parent_ix = uniq_ix >> 1
            parent_iy = uniq_iy >> 1
            parent_iz = uniq_iz >> 1
            octant    = ((uniq_ix & 1)
                       | ((uniq_iy & 1) << 1)
                       | ((uniq_iz & 1) << 2)).astype(np.int32)

            # find parent local index via searchsorted on prev level's keys
            prev_keys = (prev_level_nodes[:, 0] * (1 << (2 * shift))
                       + prev_level_nodes[:, 1] * (1 << shift)
                       + prev_level_nodes[:, 2])
            child_parent_keys = (parent_ix * (1 << (2 * shift))
                               + parent_iy * (1 << shift)
                               + parent_iz)
            parent_local = np.searchsorted(prev_keys, child_parent_keys)
            parent_global = parent_base + parent_local  # index in flat array

            # write child index into parent's children array
            # (multiple children per parent — must loop over octants;
            #  but this loop is over at most 8 values, not over particles)
            for o in range(8):
                mask_o = octant == o
                if not mask_o.any():
                    continue
                # all_children[-1] is the array for the previous depth
                all_children[-1][parent_local[mask_o], o] = \
                    total_nodes + np.where(mask_o)[0]

        node_base.append(total_nodes)
        all_node_min.append(n_min)
        all_node_size.append(n_size)
        all_node_data.append(n_data.astype(np.float32))
        all_children.append(n_children)
        total_nodes += K

        print(f"  depth {depth:2d}: {K:>10,} nodes  "
              f"cell={cell_size:.4g}  ({int((time()-t_lev)*1000)}ms)")

        prev_level_nodes = np.stack([uniq_ix, uniq_iy, uniq_iz], axis=1)

        if depth < max_depth:
            # refine: child grid coords = parent * 2 + octant bit
            grid_res  *= 2
            cell_size *= 0.5
            # recompute integer coords at finer resolution
            p_ix = np.floor((pts[:, 0] - root_min[0]) / cell_size).astype(np.int64)
            p_iy = np.floor((pts[:, 1] - root_min[1]) / cell_size).astype(np.int64)
            p_iz = np.floor((pts[:, 2] - root_min[2]) / cell_size).astype(np.int64)
            # clamp (numerical safety)
            np.clip(p_ix, 0, grid_res - 1, out=p_ix)
            np.clip(p_iy, 0, grid_res - 1, out=p_iy)
            np.clip(p_iz, 0, grid_res - 1, out=p_iz)

    # ---- bottom-up accumulation for interior nodes ----
    # Interior node data should equal the sum of all descendant leaves.
    # We already accumulated from particles at every level, so each node
    # already holds the correct sum — no extra pass needed.

    # ---- concatenate all levels ----
    node_min  = np.vstack(all_node_min).astype(np.float32)
    node_size = np.concatenate(all_node_size).astype(np.float32)
    node_data = np.vstack(all_node_data).astype(np.float32)
    children  = np.vstack(all_children).astype(np.int32)

    elapsed = int((time() - t0) * 1000)
    print(f"[INFO]: Octree built — {total_nodes:,} nodes total  ({elapsed}ms)")
    return node_min, node_size, node_data, children, root_min, root_size


# ============================================================
# SHADERS
# ============================================================

# ---- full-screen quad ----
SCREEN_VERTEX_SHADER = """
#version 430 core
layout(location = 0) in vec2 position;
out vec2 vUv;
void main() {
    vUv = vec2((position.x + 1.0) * 0.5, 1.0 - (position.y + 1.0) * 0.5);
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

# ---- raymarching fragment shader ----
# The octree is uploaded as four SSBOs:
#   binding 0: node_min  (vec3 per node, padded to vec4)
#   binding 1: node_size (float per node)
#   binding 2: node_data (vec2 per node: sum_qw, sum_w)
#   binding 3: children  (8 ints per node)
#
# The ray walks down the octree (iterative DFS via a small stack)
# and accumulates (qw, w) from every *leaf* it intersects.
# The final colour is computed exactly like the original screen pass.

RAYMARCH_FRAGMENT_SHADER = """
#version 430 core
in vec2 vUv;
out vec4 FragColor;

// ---------- octree SSBOs ----------
layout(std430, binding = 0) readonly buffer NodeMin  { vec4  nodeMin[];  };
layout(std430, binding = 1) readonly buffer NodeSize { float nodeSize[]; };
layout(std430, binding = 2) readonly buffer NodeData { vec2  nodeData[]; };
layout(std430, binding = 3) readonly buffer Children { int   nodeChildren[]; }; // 8 per node

// ---------- camera ----------
uniform vec3  uCamPos;
uniform vec3  uCamFwd;
uniform vec3  uCamRight;
uniform vec3  uCamUp;
uniform float uTanHalfFov;
uniform float uAspect;

// ---------- colormap ----------
uniform sampler2D uColormap;
uniform float uMinVal;
uniform float uMaxVal;
uniform vec4  uUnderColor;
uniform vec4  uOverColor;

// ---------- helpers ----------
bool intersectAABB(vec3 ro, vec3 rd, vec3 bmin, float bsize,
                   out float tNear, out float tFar)
{
    vec3 bmax = bmin + vec3(bsize);
    vec3 invRd = 1.0 / rd;
    vec3 t0 = (bmin - ro) * invRd;
    vec3 t1 = (bmax - ro) * invRd;
    vec3 tMin = min(t0, t1);
    vec3 tMax = max(t0, t1);
    tNear = max(max(tMin.x, tMin.y), tMin.z);
    tFar  = min(min(tMax.x, tMax.y), tMax.z);
    return tFar >= max(tNear, 0.0);
}

// ---- iterative DFS octree traversal ----
// We keep a small stack (max_depth = 20 → at most 20*8 = 160 entries,
// but we only need a stack depth equal to max tree depth).
#define STACK_SIZE 64

void main()
{
    // reconstruct ray
    vec2 ndc = vUv * 2.0 - 1.0;
    vec3 rd  = normalize(
        uCamFwd
        + uCamRight * ndc.x * uTanHalfFov * uAspect
        + uCamUp    * ndc.y * uTanHalfFov
    );
    vec3 ro = uCamPos;

    // early rejection against root (node 0)
    float tNear, tFar;
    if (!intersectAABB(ro, rd, nodeMin[0].xyz, nodeSize[0], tNear, tFar))
    {
        discard;
    }

    // DFS traversal
    float sumQW = 0.0;
    float sumW  = 0.0;

    int stack[STACK_SIZE];
    int top = 0;
    stack[top++] = 0;   // push root

    while (top > 0)
    {
        int nidx = stack[--top];

        float tN, tF;
        if (!intersectAABB(ro, rd, nodeMin[nidx].xyz, nodeSize[nidx], tN, tF))
            continue;

        // check if leaf (all children == -1)
        bool isLeaf = true;
        for (int o = 0; o < 8; o++) {
            if (nodeChildren[nidx * 8 + o] >= 0) { isLeaf = false; break; }
        }

        if (isLeaf)
        {
            // accumulate weighted data; weight by intersection length
            float seg = tF - tN;
            sumQW += nodeData[nidx].x * seg;
            sumW  += nodeData[nidx].y * seg;
        }
        else
        {
            // push children that intersect the ray
            for (int o = 7; o >= 0; o--)   // push in reverse so octant 0 is on top
            {
                int cidx = nodeChildren[nidx * 8 + o];
                if (cidx < 0) continue;
                float cN, cF;
                if (intersectAABB(ro, rd, nodeMin[cidx].xyz, nodeSize[cidx], cN, cF))
                {
                    if (top < STACK_SIZE)
                        stack[top++] = cidx;
                }
            }
        }
    }

    if (sumW == 0.0) discard;

    // same tone-mapping as original
    const float INV_LOG10 = 0.4342944819;
    float depth = log(sumQW / sumW) * INV_LOG10;
    float t = (depth - uMinVal) / (uMaxVal - uMinVal);
    vec4 color = texture(uColormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(uUnderColor, color, step(0.0, t));
    color = mix(color,  uOverColor, step(1.0, t));
    FragColor = color;
}
"""


# ============================================================
# GEOMETRY
# ============================================================

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


# ============================================================
# CAMERA MATH
# ============================================================

def look_at(eye, center, up):
    f = center - eye; f /= np.linalg.norm(f)
    u = up / np.linalg.norm(up)
    s = np.cross(f, u); s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0,:3] = s; m[1,:3] = u; m[2,:3] = -f
    m[:3,3] = -m[:3,:3] @ eye
    return m

def camera_vectors(eye, center, up_hint):
    fwd   = center - eye; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up_hint); right /= np.linalg.norm(right)
    up    = np.cross(right, fwd)
    return fwd, right, up


# ============================================================
# SSBO UPLOAD
# ============================================================

def upload_ssbo(binding, data: np.ndarray):
    ssbo = glGenBuffers(1)
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, ssbo)
    glBufferData(GL_SHADER_STORAGE_BUFFER, data.nbytes, data, GL_STATIC_DRAW)
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER, binding, ssbo)
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, 0)
    return ssbo


# ============================================================
# MAIN RENDER
# ============================================================

def render(width, height, framerate,
           data_file, camera_file, video_file,
           minVal, maxVal,
           underColor, overColor, badColor,
           colormap, max_depth):

    create_egl_context(width, height)

    glDisable(GL_DEPTH_TEST)
    glDisable(GL_BLEND)
    glClearColor(0,0,0,1)
    glPixelStorei(GL_PACK_ALIGNMENT, 1)

    # ---------- shaders ----------
    print("[INFO]: Compiling shaders...", end='', flush=True)
    t0 = time()
    prog = shaders.compileProgram(
        shaders.compileShader(SCREEN_VERTEX_SHADER,    GL_VERTEX_SHADER),
        shaders.compileShader(RAYMARCH_FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
    )
    print(f" Done ({int((time()-t0)*1000)}ms)")

    # ---------- FBO for final frame ----------
    print("[INFO]: Creating framebuffer...", end='', flush=True)
    t0 = time()
    final_fbo = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
    final_tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, final_tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, final_tex, 0)
    assert glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    print(f" Done ({int((time()-t0)*1000)}ms)")

    quad_vao = setup_quad()

    # ---------- colormap texture ----------
    cmap = plt.get_cmap(colormap, 256)
    cmap_data = (cmap(np.linspace(0, 1, 256)) * 255).astype(np.uint8)
    cmap_tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, cmap_tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 256, 1, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, cmap_data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

    # ---------- load point data ----------
    print("[INFO]: Loading volume data...", end='', flush=True)
    t0 = time()
    raw = np.fromfile(data_file, np.float32)
    N   = raw.size // 6
    px, py, pz, pdx, qty, w = np.split(raw, 6)
    print(f" Done ({int((time()-t0)*1000)}ms) — {N} particles")

    # ---------- build octree ----------
    node_min, node_size, node_data, children, root_min, root_size = \
        build_octree(px, py, pz, qty, w, max_depth)

    # ---------- upload SSBOs ----------
    print("[INFO]: Uploading octree SSBOs...", end='', flush=True)
    t0 = time()

    # binding 0: node_min as vec4 (pad to 16 bytes)
    node_min_pad = np.zeros((len(node_min), 4), np.float32)
    node_min_pad[:, :3] = node_min
    upload_ssbo(0, node_min_pad)
    upload_ssbo(1, node_size)
    upload_ssbo(2, node_data)
    upload_ssbo(3, children.flatten())

    print(f" Done ({int((time()-t0)*1000)}ms)")

    # ---------- camera path ----------
    print("[INFO]: Loading camera path...", end='', flush=True)
    t0 = time()
    cam = np.loadtxt(camera_file, np.float32)
    print(f" Done ({int((time()-t0)*1000)}ms)")

    # ---------- ffmpeg ----------
    command = [
        'ffmpeg', '-hide_banner', '-v', 'error', '-y',
        '-f', 'rawvideo', '-vcodec', 'rawvideo',
        '-s', f'{width}x{height}',
        '-pix_fmt', 'rgba', '-r', str(framerate), '-i', '-',
        '-pix_fmt', 'yuv420p',
        '-c:v', 'hevc_nvenc',
        '-cq', '22', '-preset', 'p7', '-rc', 'vbr_hq', '-tune', 'hq',
        video_file
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)

    # ---------- PBO double-buffer ----------
    num_pbos = 2
    pbos = glGenBuffers(num_pbos)
    for pbo in pbos:
        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbo)
        glBufferData(GL_PIXEL_PACK_BUFFER, width * height * 4, None, GL_STREAM_READ)
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
    pbo_index = 0

    fov_y      = np.radians(60.0)
    tan_half   = np.tan(fov_y / 2.0)
    aspect     = width / height
    up_hint    = np.array([0, 1, 0], np.float32)

    glUseProgram(prog)
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, cmap_tex)
    glUniform1i(glGetUniformLocation(prog, "uColormap"), 0)
    glUniform1f(glGetUniformLocation(prog, "uTanHalfFov"), tan_half)
    glUniform1f(glGetUniformLocation(prog, "uAspect"),     aspect)
    glUniform1f(glGetUniformLocation(prog, "uMinVal"),     minVal)
    glUniform1f(glGetUniformLocation(prog, "uMaxVal"),     maxVal)
    glUniform4f(glGetUniformLocation(prog, "uUnderColor"), *underColor)
    glUniform4f(glGetUniformLocation(prog, "uOverColor"),  *overColor)

    loc_cam_pos   = glGetUniformLocation(prog, "uCamPos")
    loc_cam_fwd   = glGetUniformLocation(prog, "uCamFwd")
    loc_cam_right = glGetUniformLocation(prog, "uCamRight")
    loc_cam_up    = glGetUniformLocation(prog, "uCamUp")

    for i, (ex, ey, ez, cx, cy, cz, nx, ny, nz) in enumerate(
            tqdm(cam, desc="Rendering frames", unit=" frames")):

        eye    = np.array([ex, ey, ez], np.float32)
        center = np.array([cx, cy, cz], np.float32)
        up_h   = np.array([nx, ny, nz], np.float32)

        fwd, right, up = camera_vectors(eye, center, up_h)

        glBindFramebuffer(GL_FRAMEBUFFER, final_fbo)
        glViewport(0, 0, width, height)
        glClear(GL_COLOR_BUFFER_BIT)

        glUniform3f(loc_cam_pos,   *eye)
        glUniform3f(loc_cam_fwd,   *fwd)
        glUniform3f(loc_cam_right, *right)
        glUniform3f(loc_cam_up,    *up)

        glBindVertexArray(quad_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        # PBO readback
        next_pbo = (pbo_index + 1) % num_pbos
        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
        glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE,
                     ctypes.c_void_p(0))

        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[next_pbo])
        ptr = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, width * height * 4,
                               GL_MAP_READ_BIT)
        if ptr:
            if i > 0:
                buf = ctypes.string_at(ptr, width * height * 4)
                process.stdin.write(buf)
            glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)
        pbo_index = next_pbo

    # flush last frame
    glBindBuffer(GL_PIXEL_PACK_BUFFER, pbos[pbo_index])
    ptr = glMapBuffer(GL_PIXEL_PACK_BUFFER, GL_READ_ONLY)
    if ptr:
        buf = ctypes.string_at(ptr, width * height * 4)
        process.stdin.write(buf)
        glUnmapBuffer(GL_PIXEL_PACK_BUFFER)
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)

    process.stdin.close()
    process.wait()


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser("OctreeVolumeRenderer")
    parser.add_argument("--data-file",   "-df", type=str, required=True)
    parser.add_argument("--camera-file", "-cf", type=str, required=True)
    parser.add_argument("--video-file",  "-vf", type=str, default="out.mp4")
    parser.add_argument("--width",  "-wx", type=int, default=1280)
    parser.add_argument("--height", "-hy", type=int, default=720)
    parser.add_argument("--framerate", "-fr", type=int, default=30)
    parser.add_argument("--minval",  type=float, default=-3.0)
    parser.add_argument("--maxval",  type=float, default=3.0)
    parser.add_argument("--undercolor", "-uc", type=float, nargs=4, default=(0,0,0,1))
    parser.add_argument("--overcolor",  "-oc", type=float, nargs=4, default=(1,1,1,1))
    parser.add_argument("--badcolor",   "-bc", type=float, nargs=4, default=(1,0,1,1))
    parser.add_argument("--colormap",   "-cm", type=str, default="inferno")
    parser.add_argument(
        "--max-depth", "-md", type=int, default=8,
        help="Maximum octree subdivision depth (higher = finer voxels, more memory/build time)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    render(
        width=args.width, height=args.height, framerate=args.framerate,
        data_file=args.data_file, camera_file=args.camera_file,
        video_file=args.video_file,
        minVal=args.minval, maxVal=args.maxval,
        underColor=args.undercolor, overColor=args.overcolor,
        badColor=args.badcolor,
        colormap=args.colormap,
        max_depth=args.max_depth,
    )


if __name__ == "__main__":
    main()