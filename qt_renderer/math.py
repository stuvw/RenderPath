import numpy as np

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