import datetime
import os

import cv2


def format_timestamp(ts=None):
    if ts is None:
        ts = datetime.datetime.now()
    return ts.strftime("%Y%m%d_%H%M%S")


def ensure_dirs(output_dir):
    images_dir = os.path.join(output_dir, "images")
    videos_dir = os.path.join(output_dir, "videos")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)
    return images_dir, videos_dir


def make_writer(path, fps, size):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, size)
    if not writer.isOpened():
        raise RuntimeError(f"Nie udalo sie utworzyc pliku wideo: {path}")
    return writer


def resize_for_detection(frame, detect_width):
    if detect_width <= 0 or frame.shape[1] <= detect_width:
        return frame, 1.0, 1.0

    scale = detect_width / frame.shape[1]
    detect_height = int(frame.shape[0] * scale)
    resized = cv2.resize(frame, (detect_width, detect_height), interpolation=cv2.INTER_AREA)
    return resized, frame.shape[1] / detect_width, frame.shape[0] / detect_height


def processing_profile(width, height, requested_detect_width=0, requested_fps=0):
    megapixels = (width * height) / 1_000_000

    if requested_detect_width > 0:
        detect_width = min(width, requested_detect_width)
    elif width >= 3840 or megapixels >= 7:
        detect_width = 640
    elif width >= 2560 or megapixels >= 3.5:
        detect_width = 768
    elif width >= 1920 or megapixels >= 2:
        detect_width = 960
    else:
        detect_width = min(width, 960)

    if width >= 3840 or megapixels >= 7:
        preview_width = 960
        evidence_fps = 8.0
    elif width >= 2560 or megapixels >= 3.5:
        preview_width = 1100
        evidence_fps = 10.0
    elif width >= 1920 or megapixels >= 2:
        preview_width = 1280
        evidence_fps = 12.0
    else:
        preview_width = min(width, 1280)
        evidence_fps = 15.0

    if requested_fps > 0:
        evidence_fps = requested_fps

    return {
        "detect_width": int(detect_width),
        "preview_width": int(preview_width),
        "evidence_fps": float(evidence_fps),
    }


def draw_detections(frame, boxes, scale=1.0):
    for x1, y1, x2, y2, label, conf in boxes:
        color = (0, 255, 0) if label == "dog" else (255, 160, 0)
        cx = int(((x1 + x2) / 2) * scale)
        cy = int(((y1 + y2) / 2) * scale)
        radius = max(18, int(max(x2 - x1, y2 - y1) * scale / 2))
        cv2.circle(frame, (cx, cy), radius, color, 4)
        cv2.putText(
            frame,
            f"{label} {conf:.2f}",
            (max(0, cx - radius), max(28, cy - radius - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            color,
            2,
        )


def draw_roi(frame, roi, scale=1.0):
    if not roi:
        return

    x1, y1, x2, y2 = roi
    start = (int(x1 * scale), int(y1 * scale))
    end = (int(x2 * scale), int(y2 * scale))
    cv2.rectangle(frame, start, end, (0, 220, 255), 3)


def preview_frame(frame, boxes, preview_width, roi_pixels=None):
    if preview_width > 0 and frame.shape[1] > preview_width:
        scale = preview_width / frame.shape[1]
        preview = cv2.resize(
            frame,
            (preview_width, int(frame.shape[0] * scale)),
            interpolation=cv2.INTER_AREA,
        )
    else:
        scale = 1.0
        preview = frame.copy()

    draw_roi(preview, roi_pixels, scale)
    draw_detections(preview, boxes, scale)
    return preview
