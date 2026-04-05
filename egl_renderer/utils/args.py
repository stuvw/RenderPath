import argparse

def parse_args():
    parser = argparse.ArgumentParser("RenderPath VR")

    parser.add_argument("--mode", type=str, choices=["normal", "vr180", "vr360"],
                            default="normal", help="Rendering mode: normal, vr180 or vr360")
    
    file_group = parser.add_argument_group("Input an output files")

    file_group.add_argument("--data-file", "-df", type=str, required=True,
                            help="Input binary simulation data file")
    file_group.add_argument("--camera-file", "-cf", type=str, required=True,
                            help="Input camera path, direction and up file")
    file_group.add_argument("--video-file", "-vf", type=str, default="out.mp4",
                            help="Output video file")

    sensitivity_group = parser.add_argument_group("Sensitivity (increase range if you don't see anything)")

    sensitivity_group.add_argument("--minval", type=float, default=-3.0,
                            help="Value below which the data is discarded")
    sensitivity_group.add_argument("--maxval", type=float, default=3.0,
                            help="Value above which the data is discarded")

    palette_group = parser.add_argument_group("Palette")

    palette_group.add_argument("--undercolor", "-uc", type=float, nargs=4,default=(0,0,0,1),
                            help="Color for data under the minimum")
    palette_group.add_argument("--overcolor", "-oc", type=float, nargs=4, default=(1,1,1,1),
                            help="Color for data over the maximum")
    palette_group.add_argument("--badcolor", "-bc", type=float, nargs=4, default=(1,0,1,1),
                            help="Color for NaN/error data")
    palette_group.add_argument("--colormap", "-cm", type=str, default="inferno",
                            help="Matplotlib colormap to choose")

    video_group = parser.add_argument_group("Video settings")

    video_group.add_argument("--width", "-wx", type=int, default=1280,
                            help="Output width. Default 1280 for normal rendering. "
                            "8192 recommended for VR360. 4096 is recommended for VR180 / fulldome.")
    video_group.add_argument("--height", "-hy", type=int, default=720,
                            help="Output width. Default 720. Height is handled automatically for VR360 and VR180")

    video_group.add_argument("--framerate", "-fr", type=int, default=30,
                            help="Framerate of rendered video")

    encoder_group = parser.add_argument_group("Encoder settings (only if you know what you're doing)")

    encoder_group.add_argument("--hwaccel", type=str, choices=["none", "nvenc", "amf", "qsv"], default="none",
                            help="Enable hardware acceleration for video encoding (nvenc for Nvidia, amf for AMD and qsv for Intel)")
    encoder_group.add_argument("--encoder", type=str, choices=["x264", "x265", "av1"], default="x264",
                            help="Choose which video codec you will use to encode the video")

    args = parser.parse_args()

    return args