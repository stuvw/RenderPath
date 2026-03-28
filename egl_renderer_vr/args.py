import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        description="Headless VR180/VR360 volume renderer."
    )
    parser.add_argument("--mode", required=True, type=str, choices=["vr180", "vr360"])
    parser.add_argument("--data-file",   "-df", required=True,  help="Binary float32 data file")
    parser.add_argument("--camera-file", "-cf", required=True,  help="Camera path file (Nx9: px py pz cx cy cz nx ny nz)")
    parser.add_argument("--video-file",  "-vf", required=True,  help="Output video path (.mp4 or .mkv)")
    parser.add_argument("--width",       "-wx", type=int, default=8192,
                        help="Output width. Default 8192, recommended for VR360. 4096 is recommended for VR180 / fulldome)")
    parser.add_argument("--min-val",     type=float, default=-3.0)
    parser.add_argument("--max-val",     type=float, default=3.0)
    parser.add_argument("--under-color", type=float, nargs=4, default=(0.0, 0.0, 0.0, 1.0))
    parser.add_argument("--over-color",  type=float, nargs=4, default=(1.0, 1.0, 1.0, 1.0))
    parser.add_argument("--bad-color",   type=float, nargs=4, default=(1.0, 0.0, 1.0, 1.0))
    parser.add_argument("--colormap",    default="inferno")
    parser.add_argument("--framerate",   type=int, default=60)
    args = parser.parse_args()
    return args