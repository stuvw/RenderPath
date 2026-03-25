try:
    import psutil
except ImportError:
    psutil = None

from OpenGL.GL import *

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