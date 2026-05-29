import threading
import time
from collections import deque

import cv2

from detection_config import (
    RESTART_FIELDS,
    changed_restart_fields,
    model_status,
    normalize_detection_config,
    public_profiles,
    runtime_values,
)
from detector import YoloDetector
from recorder import EvidenceRecorder
from roi import RuntimeConfigStore, crop_frame, roi_to_pixels
from source import IpWebcamSource
from video_utils import draw_detections, draw_roi, format_timestamp, preview_frame, processing_profile


class DogMonitor:
    def __init__(self, settings):
        self.settings = settings
        self.config_store = RuntimeConfigStore(settings.config_path, settings.stream_url, settings)
        self.lock = threading.Lock()
        self.thread_lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()
        self.source_changed = threading.Event()
        self.latest_jpeg = None
        self.events = deque(maxlen=50)
        self.status = self._initial_status()

    def _initial_status(self):
        roi = self.config_store.get_roi()
        stream_url = self.config_store.get_stream_url()
        detection = self.config_store.get_detection()
        return {
            "running": False,
            "stream_url": stream_url,
            "source_type": "ip_webcam",
            "model": detection["model_path"],
            "profile": detection["profile"],
            "requested_detect_width": detection["detect_width"],
            "requested_yolo_imgsz": detection["yolo_imgsz"],
            "confidence": min(detection["dog_conf"], detection["person_conf"]),
            "dog_conf": detection["dog_conf"],
            "person_conf": detection["person_conf"],
            "recording": False,
            "target_visible": False,
            "trigger_visible": False,
            "dog_count": 0,
            "person_count": 0,
            "target_labels": ["dog", "person"],
            "trigger_labels": list(detection["trigger_labels"]),
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
            "requested_yolo_device": detection["yolo_device"],
            "yolo_device": None,
            "roi": roi,
            "roi_active": bool(roi),
            "roi_pixels": None,
            "preview_enabled": detection["preview_enabled"],
            "engine_state": "stopped",
            "engine_restarting": False,
            "last_engine_restart_at": None,
            "stream_state": "stopped",
            "read_failures": 0,
            "open_failures": 0,
        }

    def start(self):
        with self.thread_lock:
            if self.thread and self.thread.is_alive():
                return False

            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name="dog-monitor", daemon=True)
            self.thread.start()
            return True

    def stop(self, timeout=5):
        self.stop_event.set()
        with self.thread_lock:
            thread = self.thread
            if thread and thread.is_alive() and threading.current_thread() != thread:
                thread.join(timeout=timeout)
            return not (thread and thread.is_alive())

    def snapshot(self):
        with self.lock:
            return dict(self.status), list(self.events), self.latest_jpeg

    def config_snapshot(self):
        detection = self.config_store.get_detection()
        with self.lock:
            return {
                "stream_url": self.status.get("stream_url"),
                "model": detection["model_path"],
                "requested_yolo_device": detection["yolo_device"],
                "yolo_device": self.status.get("yolo_device"),
                "roi": self.status.get("roi"),
                "target_labels": ["dog", "person"],
                "confidence": min(detection["dog_conf"], detection["person_conf"]),
                "detect_width": detection["detect_width"],
                "detection": detection,
            }

    def detection_config_snapshot(self):
        detection = self.config_store.get_detection()
        return {
            "config": detection,
            "profiles": public_profiles(),
            "restart_fields": sorted(RESTART_FIELDS),
            "model_status": model_status(detection["model_path"]),
        }

    def update_detection_config(self, payload):
        current = self.config_store.get_detection()
        candidate = normalize_detection_config(payload, current)
        status = model_status(candidate["model_path"])
        # Pozwalamy na nieistniejace pliki, bo Ultralytics automatycznie je pobierze
        # if not status["exists"]:
        #     raise ValueError(status["message"])

        before, after = self.config_store.set_detection(candidate)
        restart_fields = changed_restart_fields(before, after)
        self._set_detection_status(after)
        restarted = False
        if restart_fields:
            restarted = self.restart_engine("Zmiana ustawien YOLO: " + ", ".join(restart_fields))
        return {
            "config": after,
            "restart_required": bool(restart_fields),
            "restart_fields": restart_fields,
            "restarted": restarted,
            "model_status": model_status(after["model_path"]),
        }

    def restart_engine(self, reason):
        self._add_event(
            {
                "type": "engine",
                "time": format_timestamp(),
                "message": reason,
            }
        )
        self._set_status(
            engine_state="restarting",
            engine_restarting=True,
            last_error="Przeladowuje silnik detekcji",
            last_engine_restart_at=time.time(),
        )
        if not self.stop(timeout=8):
            self._set_status(
                engine_state="error",
                engine_restarting=False,
                last_error="Nie udalo sie zatrzymac silnika detekcji przed restartem",
            )
            return False

        if not self.start():
            self._set_status(
                engine_state="error",
                engine_restarting=False,
                last_error="Nie udalo sie uruchomic silnika detekcji po restarcie",
            )
            return False
        return True

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
            stream_state="reconnecting",
        )
        return normalized

    def _set_detection_status(self, detection):
        self._set_status(
            model=detection["model_path"],
            profile=detection["profile"],
            requested_detect_width=detection["detect_width"],
            requested_yolo_imgsz=detection["yolo_imgsz"],
            confidence=min(detection["dog_conf"], detection["person_conf"]),
            dog_conf=detection["dog_conf"],
            person_conf=detection["person_conf"],
            trigger_labels=list(detection["trigger_labels"]),
            requested_yolo_device=detection["yolo_device"],
            preview_enabled=detection["preview_enabled"],
        )

    def _set_status(self, **changes):
        with self.lock:
            self.status.update(changes)

    def _increment_status(self, key):
        with self.lock:
            value = int(self.status.get(key) or 0) + 1
            self.status[key] = value
            return value

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
        self._set_status(last_error="Lacze z kamera", stream_state="connecting")
        while not self.stop_event.is_set():
            desired_url = self.config_store.get_stream_url()
            if desired_url != source.stream_url:
                source.close()
                source.stream_url = desired_url
                self._set_status(stream_url=desired_url)

            if source.open():
                self._refresh_camera_status(source)
                self._set_status(last_error=None, stream_state="connected")
                return True

            self._increment_status("open_failures")
            self._set_status(
                last_error=f"Nie udalo sie otworzyc kamery. Ponawiam za {self.settings.reconnect_delay}s.",
                stream_state="reconnecting",
            )
            self.stop_event.wait(self.settings.reconnect_delay)
        return False

    def _run(self):
        source = IpWebcamSource(self.config_store.get_stream_url(), self.settings.ip_webcam_timeout)
        detection = self.config_store.get_detection()
        recorder = EvidenceRecorder(self.settings.output_dir, 20)
        self._set_detection_status(detection)
        self._set_status(running=True, engine_state="starting", engine_restarting=False, last_error=None)

        try:
            status = model_status(detection["model_path"])
            # Pozwalamy na nieistniejace pliki, bo YOLO pobiera je automatycznie
            # if not status["exists"]:
            #     raise RuntimeError(status["message"])
            detector = YoloDetector(detection["model_path"], detection["yolo_device"])
            self._set_status(yolo_device=detector.device)
            if not self._open_source(source):
                self._set_status(
                    running=False,
                    engine_state="stopped",
                    stream_state="stopped",
                    last_error="Zatrzymano przed polaczeniem z kamera",
                )
                return
        except Exception as exc:
            self._set_status(
                running=False,
                engine_state="error",
                engine_restarting=False,
                stream_state="error",
                last_error=str(exc),
            )
            return

        last_target_at = 0
        last_positive_at = 0
        last_status_at = 0
        last_preview_at = 0
        next_detect_at = 0
        frames_since_fps = 0
        fps_window_started_at = time.time()
        actual_fps = 0.0
        last_boxes = []
        consecutive_hits = {"dog": 0, "person": 0}

        try:
            self._set_status(engine_state="running", stream_state="connected")
            while not self.stop_event.is_set():
                detection = self.config_store.get_detection()
                runtime = runtime_values(detection)
                self._set_detection_status(detection)
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
                    consecutive_hits = {"dog": 0, "person": 0}
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
                        stream_state="reconnecting",
                    )
                    if not self._open_source(source):
                        continue

                ret, frame = source.read()
                if not ret:
                    self._increment_status("read_failures")
                    self._set_status(
                        last_error="Blad odczytu klatki. Ponawiam polaczenie.",
                        stream_state="reconnecting",
                    )
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
                    runtime["detect_width"],
                    runtime["evidence_fps"],
                )
                frame_profile = processing_profile(
                    width,
                    height,
                    runtime["detect_width"],
                    runtime["evidence_fps"],
                )

                active_tracking = bool(last_boxes) and now - last_positive_at <= detection["active_track_seconds"]
                detect_interval = (
                    detection["active_detect_seconds"]
                    if active_tracking
                    else detection["idle_detect_seconds"]
                )
                should_detect = now >= next_detect_at
                if should_detect:
                    next_detect_at = now + detect_interval
                    try:
                        confidence_by_label = {
                            "dog": detection["dog_conf"],
                            "person": detection["person_conf"],
                        }
                        last_boxes = detector.detect(
                            frame,
                            roi,
                            detect_profile["detect_width"],
                            runtime["yolo_imgsz"],
                            confidence_by_label,
                            runtime["target_labels"],
                        )
                        self._set_status(yolo_device=detector.device, last_error=None)
                    except Exception as exc:
                        last_boxes = []
                        consecutive_hits = {"dog": 0, "person": 0}
                        self._set_status(last_error=f"Blad YOLO: {exc}", yolo_device=detector.device)
                        next_detect_at = now + detection["idle_detect_seconds"]
                        continue
                    if last_boxes:
                        last_positive_at = now
                        next_detect_at = now + detection["active_detect_seconds"]
                    else:
                        consecutive_hits = {"dog": 0, "person": 0}

                target_visible = bool(last_boxes) and now - last_positive_at <= detection["active_track_seconds"]
                visible_boxes = last_boxes if target_visible else []
                dog_count = sum(1 for box in visible_boxes if box[4] == "dog")
                person_count = sum(1 for box in visible_boxes if box[4] == "person")
                trigger_visible = (
                    ("dog" in runtime["trigger_labels"] and dog_count > 0)
                    or ("person" in runtime["trigger_labels"] and person_count > 0)
                )

                if not detection["preview_enabled"]:
                    with self.lock:
                        self.latest_jpeg = None
                elif now - last_preview_at >= self.settings.preview_seconds:
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
                    trigger_visible=trigger_visible,
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
                    stream_state="connected",
                )

                if should_detect:
                    consecutive_hits["dog"] = consecutive_hits["dog"] + 1 if dog_count else 0
                    consecutive_hits["person"] = consecutive_hits["person"] + 1 if person_count else 0

                dog_ready = (
                    "dog" in runtime["trigger_labels"]
                    and consecutive_hits["dog"] >= detection["min_hits_dog"]
                )
                person_ready = (
                    "person" in runtime["trigger_labels"]
                    and consecutive_hits["person"] >= detection["min_hits_person"]
                )
                trigger_ready = trigger_visible and (dog_ready or person_ready)

                if should_detect and trigger_ready:
                    last_target_at = now
                    self._set_status(last_target_at=now)

                    if not recorder.recording:
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
                    if missing_for >= detection["post_roll_seconds"] or elapsed >= self.settings.max_event_seconds:
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
            self._set_status(
                running=False,
                recording=False,
                current_video=None,
                engine_state="stopped",
                engine_restarting=False,
                stream_state="stopped",
            )
