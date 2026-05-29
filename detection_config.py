import copy
import os


TARGET_LABELS = ("dog", "person")
PROFILE_NAMES = ("stable", "sensitive", "max_detail")
RESTART_FIELDS = {"model_path", "yolo_device"}
AUTO_CHOICES = {"auto", 0, "0", None}


PROFILE_CONFIGS = {
    "stable": {
        "model_path": "yolov8s.pt",
        "yolo_imgsz": "auto",
        "detect_width": "auto",
        "dog_conf": 0.25,
        "person_conf": 0.40,
        "idle_detect_seconds": 2.0,
        "active_detect_seconds": 0.5,
        "post_roll_seconds": 45,
    },
    "sensitive": {
        "model_path": "yolov8s.pt",
        "yolo_imgsz": "auto",
        "detect_width": "auto",
        "dog_conf": 0.18,
        "person_conf": 0.32,
        "idle_detect_seconds": 1.0,
        "active_detect_seconds": 0.35,
        "post_roll_seconds": 45,
    },
    "max_detail": {
        "model_path": "yolov8s.pt",
        "yolo_imgsz": "auto",
        "detect_width": "auto",
        "dog_conf": 0.12,
        "person_conf": 0.28,
        "idle_detect_seconds": 0.5,
        "active_detect_seconds": 0.25,
        "post_roll_seconds": 40,
    },
}

DEFAULT_DETECTION_CONFIG = {
    "profile": "sensitive",
    "model_path": "yolov8s.pt",
    "yolo_device": "auto",
    "yolo_imgsz": "auto",
    "detect_width": "auto",
    "dog_conf": 0.18,
    "person_conf": 0.32,
    "trigger_labels": ["dog", "person"],
    "idle_detect_seconds": 1.0,
    "active_detect_seconds": 0.35,
    "active_track_seconds": 12.0,
    "post_roll_seconds": 45,
    "min_hits_dog": 2,
    "min_hits_person": 2,
    "evidence_fps": "auto",
    "preview_enabled": True,
}


def defaults_from_settings(settings):
    config = copy.deepcopy(DEFAULT_DETECTION_CONFIG)
    if settings.model_path != DEFAULT_DETECTION_CONFIG["model_path"] or "YOLO_MODEL" in os.environ:
        config["model_path"] = settings.model_path
        config["profile"] = "custom"
    if settings.yolo_device != DEFAULT_DETECTION_CONFIG["yolo_device"] or "YOLO_DEVICE" in os.environ:
        config["yolo_device"] = settings.yolo_device
    if settings.detect_width > 0:
        config["detect_width"] = settings.detect_width
        config["yolo_imgsz"] = settings.detect_width
        config["profile"] = "custom"
    if settings.confidence != DEFAULT_DETECTION_CONFIG["dog_conf"] or "YOLO_CONF" in os.environ:
        config["dog_conf"] = settings.confidence
        config["person_conf"] = settings.confidence
        config["profile"] = "custom"
    if settings.target_labels and tuple(settings.target_labels) != TARGET_LABELS:
        config["trigger_labels"] = [label for label in TARGET_LABELS if label in settings.target_labels]
        config["profile"] = "custom"
    if settings.evidence_fps > 0:
        config["evidence_fps"] = settings.evidence_fps
        config["profile"] = "custom"
    if settings.idle_detect_seconds != DEFAULT_DETECTION_CONFIG["idle_detect_seconds"]:
        config["idle_detect_seconds"] = settings.idle_detect_seconds
        config["profile"] = "custom"
    if settings.active_detect_seconds != DEFAULT_DETECTION_CONFIG["active_detect_seconds"]:
        config["active_detect_seconds"] = settings.active_detect_seconds
        config["profile"] = "custom"
    config["active_track_seconds"] = settings.active_track_seconds
    if settings.active_track_seconds != DEFAULT_DETECTION_CONFIG["active_track_seconds"]:
        config["profile"] = "custom"
    if settings.post_roll_seconds != DEFAULT_DETECTION_CONFIG["post_roll_seconds"]:
        config["post_roll_seconds"] = settings.post_roll_seconds
        config["profile"] = "custom"
    config["min_hits_dog"] = settings.min_detections
    config["min_hits_person"] = settings.min_detections
    if settings.min_detections != DEFAULT_DETECTION_CONFIG["min_hits_dog"]:
        config["profile"] = "custom"
    return normalize_detection_config(config)


def model_status(model_path):
    if not model_path:
        return {"exists": False, "message": "Brak sciezki modelu"}
    if os.path.isabs(model_path):
        exists = os.path.exists(model_path)
    else:
        exists = os.path.exists(model_path) or os.path.exists(os.path.abspath(model_path))
    return {
        "exists": exists,
        "message": "Model dostepny" if exists else f"Model nie istnieje lokalnie: {model_path}",
    }


def runtime_values(config):
    return {
        "detect_width": _auto_int(config["detect_width"]),
        "yolo_imgsz": _auto_int(config["yolo_imgsz"]),
        "min_confidence": min(config["dog_conf"], config["person_conf"]),
        "target_labels": tuple(TARGET_LABELS),
        "trigger_labels": set(config["trigger_labels"]),
        "evidence_fps": _auto_float(config["evidence_fps"]),
    }


def changed_restart_fields(before, after):
    return sorted(field for field in RESTART_FIELDS if before.get(field) != after.get(field))


def public_profiles():
    profiles = {}
    for name, values in PROFILE_CONFIGS.items():
        profile = copy.deepcopy(DEFAULT_DETECTION_CONFIG)
        profile.update(values)
        profile["profile"] = name
        profiles[name] = profile
    return profiles


def normalize_detection_config(value, defaults=None):
    merged = copy.deepcopy(defaults or DEFAULT_DETECTION_CONFIG)
    incoming = value or {}

    profile = _choice(
        incoming.get("profile", merged.get("profile")),
        {"stable", "sensitive", "max_detail", "custom"},
        "custom",
    )
    if profile in PROFILE_NAMES:
        merged.update(PROFILE_CONFIGS[profile])
        merged["profile"] = profile

    for key in DEFAULT_DETECTION_CONFIG:
        if key in incoming:
            merged[key] = incoming[key]

    merged["profile"] = _choice(merged["profile"], {"stable", "sensitive", "max_detail", "custom"}, "custom")
    merged["model_path"] = _model_path(merged["model_path"])
    merged["yolo_device"] = _choice(merged["yolo_device"], {"auto", "cpu", "mps", "cuda"}, "auto")
    merged["yolo_imgsz"] = _size_choice(merged["yolo_imgsz"])
    merged["detect_width"] = _size_choice(merged["detect_width"])
    merged["dog_conf"] = _float_range(merged["dog_conf"], 0.01, 0.95, "dog_conf")
    merged["person_conf"] = _float_range(merged["person_conf"], 0.01, 0.95, "person_conf")
    merged["trigger_labels"] = _labels(merged["trigger_labels"])
    merged["idle_detect_seconds"] = _float_range(merged["idle_detect_seconds"], 0.2, 30.0, "idle_detect_seconds")
    merged["active_detect_seconds"] = _float_range(merged["active_detect_seconds"], 0.1, 10.0, "active_detect_seconds")
    merged["active_track_seconds"] = _float_range(merged["active_track_seconds"], 1.0, 120.0, "active_track_seconds")
    merged["post_roll_seconds"] = _int_range(merged["post_roll_seconds"], 1, 600, "post_roll_seconds")
    merged["min_hits_dog"] = _int_range(merged["min_hits_dog"], 1, 20, "min_hits_dog")
    merged["min_hits_person"] = _int_range(merged["min_hits_person"], 1, 20, "min_hits_person")
    merged["evidence_fps"] = _fps_choice(merged["evidence_fps"])
    merged["preview_enabled"] = _bool(merged["preview_enabled"])

    if merged["profile"] in PROFILE_NAMES and not _matches_profile(merged, merged["profile"]):
        merged["profile"] = "custom"

    return merged


def _matches_profile(config, profile_name):
    profile = copy.deepcopy(DEFAULT_DETECTION_CONFIG)
    profile.update(PROFILE_CONFIGS[profile_name])
    profile["profile"] = profile_name
    for key, value in profile.items():
        if config.get(key) != value:
            return False
    return True


def _model_path(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("Podaj sciezke modelu YOLO")
    return text


def _choice(value, allowed, default):
    text = str(value or default).strip().lower()
    return text if text in allowed else default


def _size_choice(value):
    if value in AUTO_CHOICES:
        return "auto"
    number = _int_range(value, 1, 4096, "rozmiar YOLO")
    if number not in {640, 768, 960, 1280, 1536, 1920, 2560}:
        raise ValueError("Rozmiar YOLO musi byc auto, 640, 768, 960, 1280, 1536, 1920 albo 2560")
    return number


def _fps_choice(value):
    if value in AUTO_CHOICES:
        return "auto"
    return _float_range(value, 1.0, 60.0, "evidence_fps")


def _labels(value):
    if isinstance(value, str):
        labels = [label.strip() for label in value.split(",")]
    else:
        labels = list(value or [])
    normalized = [label for label in TARGET_LABELS if label in labels]
    if not normalized:
        raise ValueError("Wybierz co najmniej jedna klase triggera")
    return normalized


def _auto_int(value):
    return 0 if value == "auto" else int(value)


def _auto_float(value):
    return 0.0 if value == "auto" else float(value)


def _bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "tak", "yes", "on"}:
            return True
        if text in {"0", "false", "nie", "no", "off"}:
            return False
    return bool(value)


def _float_range(value, low, high, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} musi byc liczba") from exc
    if not low <= number <= high:
        raise ValueError(f"{name} musi byc w zakresie {low}-{high}")
    return round(number, 3)


def _int_range(value, low, high, name):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} musi byc liczba calkowita") from exc
    if not low <= number <= high:
        raise ValueError(f"{name} musi byc w zakresie {low}-{high}")
    return number
