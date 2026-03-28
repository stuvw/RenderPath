import os
os.environ['EGL_PLATFORM'] = 'surfaceless'

from egl_renderer_vr.VR180 import render_180
from egl_renderer_vr.VR360 import render_360
from egl_renderer_vr.args import parse_args

def main():
    args = parse_args()

    if args.mode == "vr360":
        render_360(
            width=args.width,
            height=args.width//2,
            framerate=args.framerate,
            data_file=args.data_file,
            camera_file=args.camera_file,
            video_file=args.video_file,
            min_val=args.min_val,
            max_val=args.max_val,
            under_color=args.under_color,
            over_color=args.over_color,
            bad_color=args.bad_color,
            colormap=args.colormap
    )

    elif args.mode == "vr180":
        render_180(
            width=args.width,
            height=args.width,
            framerate=args.framerate,
            data_file=args.data_file,
            camera_file=args.camera_file,
            video_file=args.video_file,
            min_val=args.min_val,
            max_val=args.max_val,
            under_color=args.under_color,
            over_color=args.over_color,
            bad_color=args.bad_color,
            colormap=args.colormap
    )

    else:
        return

if __name__ == "__main__":
    main()
