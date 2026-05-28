import os
from collections import deque

import cv2

from video_utils import ensure_dirs, make_writer


class EvidenceRecorder:
    def __init__(self, output_dir, min_detections, max_images=3):
        self.images_dir, self.videos_dir = ensure_dirs(output_dir)
        self.pending_frames = deque(maxlen=max(1, min_detections))
        self.max_images = max_images
        self.writer = None
        self.video_path = None
        self.started_at = None
        self.images_saved = 0
        self.event_count = 0

    @property
    def recording(self):
        return self.writer is not None

    def add_pending_frame(self, frame):
        self.pending_frames.append(frame.copy())

    def start(self, timestamp, fps, size):
        self.event_count += 1
        save_name = f"event_{timestamp}_{self.event_count}"
        self.video_path = os.path.join(self.videos_dir, f"{save_name}.mp4")
        self.writer = make_writer(self.video_path, fps, size)
        self.started_at = None
        self.images_saved = 0

        while self.pending_frames:
            self.writer.write(self.pending_frames.popleft())

        return self.video_path

    def mark_started(self, started_at):
        self.started_at = started_at

    def write(self, frame):
        if self.writer is not None:
            self.writer.write(frame)

    def save_image(self, image):
        if not self.video_path or self.images_saved >= self.max_images:
            return None

        image_name = os.path.splitext(os.path.basename(self.video_path))[0]
        path = os.path.join(self.images_dir, f"{image_name}_{self.images_saved + 1}.jpg")
        cv2.imwrite(path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        self.images_saved += 1
        return path

    def stop(self):
        path = self.video_path
        if self.writer is not None:
            self.writer.release()

        self.writer = None
        self.video_path = None
        self.started_at = None
        self.pending_frames.clear()
        return path

    def close(self):
        self.stop()
