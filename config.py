import os
from dataclasses import dataclass


DEFAULT_TARGET_LABELS = ("dog", "person")


def _env_int(name, default):
    return int(os.environ.get(name, str(default)))


def _env_float(name, default):
    return float(os.environ.get(name, str(default)))


def parse_target_labels(value):
    if not value:
        return set(DEFAULT_TARGET_LABELS)
    return {label.strip() for label in value.split(",") if label.strip()}


@dataclass(frozen=True)
class Settings:
    stream_url: str
    model_path: str
    output_dir: str
    config_path: str
    detect_width: int
    confidence: float
    target_labels: tuple
    evidence_fps: float
    idle_detect_seconds: float
    active_detect_seconds: float
    active_track_seconds: float
    post_roll_seconds: int
    min_detections: int
    max_event_seconds: int
    reconnect_delay: int
    ip_webcam_timeout: float
    preview_seconds: float
    yolo_device: str


def load_settings():
    labels = parse_target_labels(os.environ.get("TARGET_LABELS", "dog,person"))
    return Settings(
        stream_url=os.environ.get("CAM_STREAM_URL", "http://192.168.0.13:8080/video"),
        model_path=os.environ.get("YOLO_MODEL", "yolov8s.pt"),
        output_dir=os.environ.get("OUTPUT_DIR", "output"),
        config_path=os.environ.get("DOG_WATCH_CONFIG", "config.json"),
        detect_width=_env_int("DETECT_WIDTH", 0),
        confidence=_env_float("YOLO_CONF", 0.18),
        target_labels=tuple(sorted(labels)),
        evidence_fps=_env_float("EVIDENCE_FPS", 0),
        idle_detect_seconds=_env_float("IDLE_DETECT_SECONDS", 1.0),
        active_detect_seconds=_env_float("ACTIVE_DETECT_SECONDS", 0.35),
        active_track_seconds=_env_float("ACTIVE_TRACK_SECONDS", 12.0),
        post_roll_seconds=_env_int("POST_ROLL_SECONDS", 45),
        min_detections=_env_int("MIN_DETECTIONS", 2),
        max_event_seconds=_env_int("MAX_EVENT_SECONDS", 300),
        reconnect_delay=_env_int("RECONNECT_DELAY", 5),
        ip_webcam_timeout=_env_float("IP_WEBCAM_TIMEOUT", 5),
        preview_seconds=_env_float("PREVIEW_SECONDS", 0.25),
        yolo_device=os.environ.get("YOLO_DEVICE", "auto").strip().lower() or "auto",
    )
