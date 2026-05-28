import threading
import time
from collections import deque

import cv2

from detector import YoloDetector
from recorder import EvidenceRecorder
from roi import RuntimeConfigStore, crop_frame, roi_to_pixels
from source import IpWebcamSource
from video_utils import draw_detections, draw_roi, format_timestamp, preview_frame, processing_profile


class DogMonitor:
    def __init__(self, settings):
        self.settings = settings
        self.config_store = RuntimeConfigStore(settings.config_path, settings.stream_url)
        self.lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()
        self.source_changed = threading.Event()
        self.latest_jpeg = None
        self.events = deque(maxlen=50)
        self.status = self._initial_status()

    def _initial_status(self):
        roi = self.config_store.get_roi()
        stream_url = self.config_store.get_stream_url()
        return {
            "running": False,
            "stream_url": stream_url,
            "source_type": "ip_webcam",
            "model": self.settings.model_path,
            "requested_detect_width": self.settings.detect_width,
            "confidence": self.settings.confidence,
            "recording": False,
            "target_visible": False,
            "dog_count": 0,
            "person_count": 0,
            "target_labels": list(self.settings.target_labels),
            "last_error": None,
            "last_frame_at": None,
            "last_target_at": None,
            "current_video": None,
            "frame_size": None,
            "active_detect_width": None,
            "detect_interval": None,
            "preview_width": None,
            "evidence_fps": None,
            "actual_fps": None,
            "camera_resolution": None,
            "camera_quality": None,
            "requested_yolo_device": self.settings.yolo_device,
            "yolo_device": None,
            "roi": roi,
            "roi_active": bool(roi),
            "roi_pixels": None,
        }

    def start(self):
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="dog-monitor")
        self.thread.start()

    def stop(self, timeout=5):
        self.stop_event.set()
        if self.thread and self.thread.is_alive() and threading.current_thread() != self.thread:
            self.thread.join(timeout=timeout)

    def snapshot(self):
        with self.lock:
            return dict(self.status), list(self.events), self.latest_jpeg

    def config_snapshot(self):
        with self.lock:
            return {
                "stream_url": self.status.get("stream_url"),
                "model": self.settings.model_path,
                "requested_yolo_device": self.settings.yolo_device,
                "yolo_device": self.status.get("yolo_device"),
                "roi": self.status.get("roi"),
                "target_labels": list(self.settings.target_labels),
                "confidence": self.settings.confidence,
                "detect_width": self.settings.detect_width,
            }

    def set_roi(self, roi):
        normalized = self.config_store.set_roi(roi)
        self._set_status(roi=normalized, roi_active=True)
        return normalized

    def clear_roi(self):
        self.config_store.clear_roi()
        self._set_status(roi=None, roi_active=False, roi_pixels=None)

    def set_stream_url(self, stream_url):
        normalized = self.config_store.set_stream_url(stream_url)
        self.source_changed.set()
        self._set_status(
            stream_url=normalized,
            camera_resolution=None,
            camera_quality=None,
            frame_size=None,
            actual_fps=None,
            last_error="Zmieniam zrodlo kamery",
        )
        return normalized

    def _set_status(self, **changes):
        with self.lock:
            self.status.update(changes)

    def _add_event(self, event):
        with self.lock:
            self.events.appendleft(event)

    def _set_preview(self, frame, boxes, preview_width, roi_pixels):
        preview = preview_frame(frame, boxes, preview_width, roi_pixels)
        ok, encoded = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
        if ok:
            with self.lock:
                self.latest_jpeg = encoded.tobytes()

    def _refresh_camera_status(self, source):
        status = source.status()
        if not status:
            return

        self._set_status(
            camera_resolution=status.get("video_size"),
            camera_quality=status.get("quality"),
        )

    def _open_source(self, source):
        self._set_status(last_error="Lacze z kamera")
        while not self.stop_event.is_set():
            desired_url = self.config_store.get_stream_url()
            if desired_url != source.stream_url:
                source.close()
                source.stream_url = desired_url
                self._set_status(stream_url=desired_url)

            if source.open():
                self._refresh_camera_status(source)
                self._set_status(last_error=None)
                return True

            self._set_status(
                last_error=f"Nie udalo sie otworzyc kamery. Ponawiam za {self.settings.reconnect_delay}s."
            )
            self.stop_event.wait(self.settings.reconnect_delay)
        return False

    def _run(self):
        source = IpWebcamSource(self.config_store.get_stream_url(), self.settings.ip_webcam_timeout)
        recorder = EvidenceRecorder(self.settings.output_dir, self.settings.min_detections)
        self._set_status(running=True, last_error=None)

        try:
            detector = YoloDetector(
                self.settings.model_path,
                self.settings.confidence,
                self.settings.target_labels,
                self.settings.yolo_device,
            )
            self._set_status(yolo_device=detector.device)
            if not self._open_source(source):
                self._set_status(running=False, last_error="Zatrzymano przed polaczeniem z kamera")
                return
        except Exception as exc:
            self._set_status(running=False, last_error=str(exc))
            return

        last_target_at = 0
        last_positive_at = 0
        last_status_at = 0
        last_preview_at = 0
        next_detect_at = 0
        consecutive_detections = 0
        frames_since_fps = 0
        fps_window_started_at = time.time()
        actual_fps = 0.0
        last_boxes = []

        try:
            while not self.stop_event.is_set():
                desired_url = self.config_store.get_stream_url()
                if self.source_changed.is_set() or desired_url != source.stream_url:
                    self.source_changed.clear()
                    source.close()
                    if recorder.recording:
                        video_path = recorder.stop()
                        self._add_event(
                            {
                                "type": "stop",
                                "time": format_timestamp(),
                                "video": video_path,
                                "message": "Zakonczono nagrywanie przed zmiana kamery",
                            }
                        )
                    source = IpWebcamSource(desired_url, self.settings.ip_webcam_timeout)
                    last_target_at = 0
                    last_positive_at = 0
                    last_boxes = []
                    consecutive_detections = 0
                    actual_fps = 0.0
                    frames_since_fps = 0
                    fps_window_started_at = time.time()
                    with self.lock:
                        self.latest_jpeg = None
                    self._set_status(
                        stream_url=desired_url,
                        recording=False,
                        current_video=None,
                        target_visible=False,
                        dog_count=0,
                        person_count=0,
                        camera_resolution=None,
                        camera_quality=None,
                        frame_size=None,
                        actual_fps=None,
                    )
                    if not self._open_source(source):
                        continue

                ret, frame = source.read()
                if not ret:
                    self._set_status(last_error="Blad odczytu klatki. Ponawiam polaczenie.")
                    source.close()
                    if self.stop_event.wait(self.settings.reconnect_delay):
                        break
                    source = IpWebcamSource(self.config_store.get_stream_url(), self.settings.ip_webcam_timeout)
                    self._set_status(stream_url=source.stream_url)
                    if not self._open_source(source):
                        break
                    continue

                now = time.time()
                height, width = frame.shape[:2]
                roi = self.config_store.get_roi()
                roi_pixels = roi_to_pixels(roi, width, height) if roi else None
                detect_frame, _ = crop_frame(frame, roi)
                detect_height, detect_width = detect_frame.shape[:2]
                detect_profile = processing_profile(
                    detect_width,
                    detect_height,
                    self.settings.detect_width,
                    self.settings.evidence_fps,
                )
                frame_profile = processing_profile(
                    width,
                    height,
                    self.settings.detect_width,
                    self.settings.evidence_fps,
                )

                active_tracking = bool(last_boxes) and now - last_positive_at <= self.settings.active_track_seconds
                detect_interval = (
                    self.settings.active_detect_seconds
                    if active_tracking
                    else self.settings.idle_detect_seconds
                )
                should_detect = now >= next_detect_at
                if should_detect:
                    next_detect_at = now + detect_interval
                    try:
                        last_boxes = detector.detect(frame, roi, detect_profile["detect_width"])
                        self._set_status(yolo_device=detector.device)
                    except Exception as exc:
                        last_boxes = []
                        consecutive_detections = 0
                        self._set_status(last_error=f"Blad YOLO: {exc}", yolo_device=detector.device)
                        next_detect_at = now + self.settings.idle_detect_seconds
                        continue
                    if last_boxes:
                        last_positive_at = now
                        next_detect_at = now + self.settings.active_detect_seconds
                    else:
                        consecutive_detections = 0

                target_visible = bool(last_boxes) and now - last_positive_at <= self.settings.active_track_seconds
                visible_boxes = last_boxes if target_visible else []
                dog_count = sum(1 for box in visible_boxes if box[4] == "dog")
                person_count = sum(1 for box in visible_boxes if box[4] == "person")

                if now - last_preview_at >= self.settings.preview_seconds:
                    self._set_preview(frame, visible_boxes, frame_profile["preview_width"], roi_pixels)
                    last_preview_at = now

                frames_since_fps += 1
                if now - fps_window_started_at >= 2.0:
                    actual_fps = frames_since_fps / (now - fps_window_started_at)
                    frames_since_fps = 0
                    fps_window_started_at = now

                if now - last_status_at >= 10.0:
                    self._refresh_camera_status(source)
                    last_status_at = now

                self._set_status(
                    target_visible=target_visible,
                    dog_count=dog_count,
                    person_count=person_count,
                    last_frame_at=now,
                    frame_size=f"{width}x{height}",
                    active_detect_width=detect_profile["detect_width"],
                    detect_interval=detect_interval,
                    preview_width=frame_profile["preview_width"],
                    evidence_fps=frame_profile["evidence_fps"],
                    actual_fps=round(actual_fps, 2) if actual_fps else None,
                    roi=roi,
                    roi_active=bool(roi),
                    roi_pixels=f"{roi_pixels[2] - roi_pixels[0]}x{roi_pixels[3] - roi_pixels[1]}"
                    if roi_pixels
                    else None,
                    last_error=None,
                )

                if should_detect and target_visible:
                    last_target_at = now
                    consecutive_detections += 1
                    self._set_status(last_target_at=now)

                    if not recorder.recording and consecutive_detections >= self.settings.min_detections:
                        timestamp = format_timestamp()
                        writer_fps = actual_fps if actual_fps >= 1 else frame_profile["evidence_fps"]
                        video_path = recorder.start(timestamp, writer_fps, (width, height))
                        recorder.mark_started(now)
                        self._set_status(recording=True, current_video=video_path)
                        self._add_event(
                            {
                                "type": "start",
                                "time": timestamp,
                                "video": video_path,
                                "message": "Rozpoczeto nagrywanie",
                            }
                        )

                    if recorder.recording:
                        full_frame = frame.copy()
                        draw_roi(full_frame, roi_pixels, scale=1.0)
                        draw_detections(full_frame, visible_boxes, scale=1.0)
                        image_path = recorder.save_image(full_frame)
                        if image_path:
                            self._add_event(
                                {
                                    "type": "image",
                                    "time": format_timestamp(),
                                    "image": image_path,
                                    "message": "Zapisano obraz",
                                }
                            )

                if not recorder.recording:
                    recorder.add_pending_frame(frame)
                else:
                    recorder.write(frame)
                    elapsed = now - recorder.started_at
                    missing_for = now - last_target_at
                    if missing_for >= self.settings.post_roll_seconds or elapsed >= self.settings.max_event_seconds:
                        video_path = recorder.stop()
                        self._add_event(
                            {
                                "type": "stop",
                                "time": format_timestamp(),
                                "video": video_path,
                                "message": "Zakonczono nagrywanie",
                            }
                        )
                        self._set_status(recording=False, current_video=None)
        finally:
            source.close()
            recorder.close()
            self._set_status(running=False, recording=False, current_video=None)
