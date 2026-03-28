import argparse


def parse_args():
    parser = argparse.ArgumentParser("RenderPath")

    parser.add_argument("--data-file", "-df", type=str, required=True)
    parser.add_argument("--camera-file", "-cf", type=str, required=True)
    parser.add_argument("--video-file", "-vf", type=str, default="out.mp4")
    parser.add_argument("--width", "-wx", type=int, default=1280)
    parser.add_argument("--height", "-hy", type=int, default=720)
    parser.add_argument("--framerate", "-fr", type=int, default=30)
    parser.add_argument("--minval", type=float, default=-3.0)
    parser.add_argument("--maxval", type=float, default=3.0)
    parser.add_argument("--undercolor", "-uc", type=float, nargs=4,default=(0,0,0,1))
    parser.add_argument("--overcolor", "-oc", type=float, nargs=4, default=(1,1,1,1))
    parser.add_argument("--badcolor", "-bc", type=float, nargs=4, default=(1,0,1,1))
    parser.add_argument("--colormap", "-cm", type=str, default="inferno")

    args = parser.parse_args()

    return args