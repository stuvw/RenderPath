import numpy as np
from OpenGL.GL import *

# ---------------- UTIL & GEOMETRY ----------------

def setup_cube():
    v = np.array([-0.5,-0.5,-0.5, 0.5,-0.5,-0.5, 0.5, 0.5,-0.5, -0.5, 0.5,-0.5,
                  -0.5,-0.5, 0.5, 0.5,-0.5, 0.5, 0.5, 0.5, 0.5, -0.5, 0.5, 0.5], np.float32)
    i = np.array([0,1,2, 2,3,0, 4,5,6, 6,7,4, 0,4,7, 7,3,0, 1,5,6, 6,2,1, 0,1,5, 5,4,0, 3,2,6, 6,7,3], np.uint32)
    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)
    vbo, ebo = glGenBuffers(2)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, v.nbytes, v, GL_STATIC_DRAW)
    glVertexAttribPointer(0, 3, GL_FLOAT, False, 0, None)
    glEnableVertexAttribArray(0)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, i.nbytes, i, GL_STATIC_DRAW)
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

def perspective(fovy, aspect, near, far):
    f = 1.0 / np.tan(np.radians(fovy) / 2)
    m = np.zeros((4,4), np.float32)
    m[0,0], m[1,1], m[2,2], m[2,3], m[3,2] = f/aspect, f, (far+near)/(near-far), (2*far*near)/(near-far), -1
    return m

def look_at(eye, center, up):
    f = (center - eye) / np.linalg.norm(center - eye)
    s = np.cross(f, up / np.linalg.norm(up))
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0,:3], m[1,:3], m[2,:3] = s, u, -f
    m[:3,3] = -m[:3,:3] @ eye
    return m

def build_dome_basis(forward):
    """
    Build an orthonormal basis (right, up, forward) for the dome orientation.

    'forward' is the direction toward the dome's zenith (centre of the fisheye circle).
    We pick an arbitrary 'up' hint and orthogonalise — the choice of 'up hint' only
    affects the rotation of the dome image around its own axis, which is irrelevant
    for a rotationally-symmetric projection like domemaster.
    """
    forward = forward / np.linalg.norm(forward)

    # Choose a stable up hint: avoid collinearity with forward
    up_hint = np.array([0.0, 1.0, 0.0], np.float32)
    if abs(np.dot(forward, up_hint)) > 0.99:
        up_hint = np.array([1.0, 0.0, 0.0], np.float32)

    right = np.cross(forward, up_hint)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    up /= np.linalg.norm(up)

    # mat3 column-major: [right | up | forward]
    return np.column_stack([right, up, forward]).astype(np.float32)