"""Shared CLI options for main.py and main_cpu.py."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional, Tuple


MAX_DET_SIZE = 640
MAX_CAMERA_WIDTH = 1280
MAX_CAMERA_HEIGHT = 720
MAX_MODEL = 'buffalo_l'


@dataclass
class RunOptions:
    det_width: Optional[int] = None
    det_height: Optional[int] = None
    model: Optional[str] = None
    camera_width: Optional[int] = None
    camera_height: Optional[int] = None
    max_quality: bool = False
    tier: Optional[str] = None
    frame_skip: Optional[int] = None
    webcam_index: Optional[int] = None


def _parse_camera_size(value: str) -> Tuple[int, int]:
    normalized = value.lower().replace(' ', '')
    if 'x' not in normalized:
        raise argparse.ArgumentTypeError(
            f'Expected WIDTHxHEIGHT (e.g. 1280x720), got {value!r}'
        )
    width_text, height_text = normalized.split('x', 1)
    width, height = int(width_text), int(height_text)
    if width < 64 or height < 64:
        raise argparse.ArgumentTypeError('Camera resolution must be at least 64x64')
    return width, height


def parse_run_args(description: str, *, cpu: bool = False) -> RunOptions:
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  python facial_recognition/main_cpu.py -r 480\n'
            '  python facial_recognition/main_cpu.py --max\n'
            '  python facial_recognition/main.py -r 640 --cam-res 1920x1080\n'
            '  python facial_recognition/main_cpu.py --width 640 --height 480 --model buffalo_l'
        ),
    )
    parser.add_argument(
        '-r', '--resolution',
        type=int,
        metavar='SIZE',
        help='Square detection input size in pixels (e.g. 160, 480, 640)',
    )
    parser.add_argument('--width', type=int, help='Detection input width (overrides --resolution width)')
    parser.add_argument('--height', type=int, help='Detection input height (overrides --resolution height)')
    parser.add_argument(
        '--model',
        choices=['buffalo_s', 'buffalo_l'],
        help='InsightFace model (buffalo_l = better range, slower)',
    )
    parser.add_argument(
        '--cam-res', '--camera-resolution',
        dest='camera_resolution',
        type=_parse_camera_size,
        metavar='WxH',
        help='Webcam capture resolution, e.g. 1280x720',
    )
    parser.add_argument(
        '--max',
        action='store_true',
        help=f'Max quality preset: {MAX_DET_SIZE}px detection, {MAX_MODEL}, {MAX_CAMERA_WIDTH}x{MAX_CAMERA_HEIGHT} camera',
    )
    parser.add_argument('--webcam', type=int, metavar='INDEX', help='Webcam device index (default: from config)')
    if cpu:
        parser.add_argument(
            '--tier',
            choices=['auto', 'fast', 'mid', 'slow'],
            help='CPU tier (use "fast" to avoid shrinking resolution at runtime)',
        )
        parser.add_argument('--frame-skip', type=int, help='Run detection every N frames')

    args = parser.parse_args()

    det_width = args.width
    det_height = args.height
    if args.resolution is not None:
        det_width = det_width or args.resolution
        det_height = det_height or args.resolution

    camera_width = camera_height = None
    if args.camera_resolution is not None:
        camera_width, camera_height = args.camera_resolution

    return RunOptions(
        det_width=det_width,
        det_height=det_height,
        model=args.model,
        camera_width=camera_width,
        camera_height=camera_height,
        max_quality=args.max,
        tier=getattr(args, 'tier', None),
        frame_skip=getattr(args, 'frame_skip', None),
        webcam_index=args.webcam,
    )


def resolve_det_size(
    options: RunOptions,
    default_width: int,
    default_height: int,
) -> Tuple[int, int]:
    if options.max_quality:
        return MAX_DET_SIZE, MAX_DET_SIZE
    width = options.det_width if options.det_width is not None else default_width
    height = options.det_height if options.det_height is not None else default_height
    return width, height


def resolve_model(options: RunOptions, default_model: str) -> str:
    if options.max_quality:
        return MAX_MODEL
    return options.model or default_model


def resolve_camera_size(
    options: RunOptions,
    default_width: int,
    default_height: int,
) -> Tuple[int, int]:
    if options.max_quality:
        return MAX_CAMERA_WIDTH, MAX_CAMERA_HEIGHT
    width = options.camera_width if options.camera_width is not None else default_width
    height = options.camera_height if options.camera_height is not None else default_height
    return width, height
