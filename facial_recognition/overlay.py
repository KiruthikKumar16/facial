"""On-screen HUD helpers for camera pipelines."""
from __future__ import annotations

from typing import Any, List, Tuple


def draw_text_block(
    frame: Any,
    lines: List[str],
    *,
    corner: str = 'top_left',
    font_scale: float = 0.55,
    thickness: int = 1,
    color: Tuple[int, int, int] = (0, 255, 255),
    margin: int = 8,
    line_gap: int = 4,
) -> None:
    import cv2

    if not lines:
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    sizes = [cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines]
    block_w = max(size[0] for size in sizes)
    block_h = sum(size[1] for size in sizes) + line_gap * max(0, len(lines) - 1)

    frame_h, frame_w = frame.shape[:2]
    pad = 6
    if corner == 'top_right':
        x0 = frame_w - block_w - margin - pad * 2
        y0 = margin
    else:
        x0 = margin
        y0 = margin

    x1 = min(frame_w - 1, x0 + block_w + pad * 2)
    y1 = min(frame_h - 1, y0 + block_h + pad * 2)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 0, 0), cv2.FILLED)

    y = y0 + pad
    for line, (text_w, text_h) in zip(lines, sizes):
        y += text_h
        if corner == 'top_right':
            x = frame_w - text_w - margin - pad
        else:
            x = x0 + pad
        cv2.putText(frame, line, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
        y += line_gap
