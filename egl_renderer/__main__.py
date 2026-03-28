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
        minVal=args.minval,
        maxVal=args.maxval,
        underColor=args.undercolor,
        overColor=args.overcolor,
        badColor=args.badcolor,
        colormap=args.colormap
    )

if __name__ == "__main__":
    main()