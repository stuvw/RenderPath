from egl_renderer.args import parse_args
from egl_renderer.render import render

# ---------------- ENTRY ----------------

def main():
    args = parse_args()
    render(
        width=args.width,
        height=args.height,
        framerate=args.framerate,
        data_file=args.data_file,
        camera_file=args.camera_file,
        video_file=args.video_file,
        min_val=args.minval,
        max_val=args.maxval,
        under_color=args.undercolor,
        over_color=args.overcolor,
        bad_color=args.badcolor,
        colormap=args.colormap
    )

if __name__ == "__main__":
    main()