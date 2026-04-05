import os
os.environ['EGL_PLATFORM'] = 'surfaceless'

from egl_renderer.renderers.normal import render_normal
from egl_renderer.renderers.VR180 import render_180
from egl_renderer.renderers.VR360 import render_360
from egl_renderer.utils.args import parse_args

def main():
    args = parse_args()

    if args.mode == "normal":
        render_normal(
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
            colormap=args.colormap,
            hwaccel=args.hwaccel,
            encoder=args.encoder
    )

    elif args.mode == "vr360":
        render_360(
            width=args.width,
            height=args.width//2,
            framerate=args.framerate,
            data_file=args.data_file,
            camera_file=args.camera_file,
            video_file=args.video_file,
            min_val=args.minval,
            max_val=args.maxval,
            under_color=args.undercolor,
            over_color=args.overcolor,
            bad_color=args.badcolor,
            colormap=args.colormap,
            hwaccel=args.hwaccel,
            encoder=args.encoder
    )

    elif args.mode == "vr180":
        render_180(
            width=args.width,
            height=args.width,
            framerate=args.framerate,
            data_file=args.data_file,
            camera_file=args.camera_file,
            video_file=args.video_file,
            min_val=args.minval,
            max_val=args.maxval,
            under_color=args.undercolor,
            over_color=args.overcolor,
            bad_color=args.badcolor,
            colormap=args.colormap,
            hwaccel=args.hwaccel,
            encoder=args.encoder
    )

    else:
        return

if __name__ == "__main__":
    main()
