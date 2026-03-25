import numpy as np

from OpenGL.GL import *
from OpenGL.GL import shaders

# ---------------- GEOMETRY ----------------

def setup_cube():
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