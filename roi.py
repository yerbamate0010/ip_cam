import copy
import json
import os
import threading
import urllib.parse

from detection_config import defaults_from_settings, normalize_detection_config


MIN_ROI_SPAN = 0.02


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def normalize_roi(value):
    if value is None:
        return None

    try:
        x1 = float(value["x1"])
        y1 = float(value["y1"])
        x2 = float(value["x2"])
        y2 = float(value["y2"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ROI musi miec pola x1, y1, x2, y2") from exc

    left, right = sorted((_clamp(x1), _clamp(x2)))
    top, bottom = sorted((_clamp(y1), _clamp(y2)))
    if right - left < MIN_ROI_SPAN or bottom - top < MIN_ROI_SPAN:
        raise ValueError("ROI jest za maly")

    return {
        "x1": round(left, 6),
        "y1": round(top, 6),
        "x2": round(right, 6),
        "y2": round(bottom, 6),
    }


def normalize_stream_url(value):
    if value is None:
        raise ValueError("Adres streamu jest pusty")

    raw = str(value).strip()
    if not raw:
        raise ValueError("Adres streamu jest pusty")
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urllib.parse.urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Podaj adres w formacie http://IP:8080/video")

    path = parsed.path or "/video"
    if path == "/":
        path = "/video"

    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def roi_to_pixels(roi, width, height):
    roi = normalize_roi(roi)
    if roi is None:
        return None

    x1 = int(round(roi["x1"] * width))
    y1 = int(round(roi["y1"] * height))
    x2 = int(round(roi["x2"] * width))
    y2 = int(round(roi["y2"] * height))
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + 1, min(width, x2))
    y2 = max(y1 + 1, min(height, y2))
    return x1, y1, x2, y2


def crop_frame(frame, roi):
    height, width = frame.shape[:2]
    pixels = roi_to_pixels(roi, width, height)
    if pixels is None:
        return frame, (0, 0, width, height)

    x1, y1, x2, y2 = pixels
    return frame[y1:y2, x1:x2], pixels


def boxes_to_full_frame(boxes, offset):
    x_offset, y_offset, _, _ = offset
    return [
        (
            x1 + x_offset,
            y1 + y_offset,
            x2 + x_offset,
            y2 + y_offset,
            label,
            conf,
        )
        for x1, y1, x2, y2, label, conf in boxes
    ]


class RuntimeConfigStore:
    def __init__(self, path, default_stream_url, settings=None):
        self.path = path
        self.default_stream_url = normalize_stream_url(default_stream_url)
        self.default_detection = defaults_from_settings(settings) if settings else normalize_detection_config({})
        self.lock = threading.Lock()
        self.payload = self._load()

    def get_roi(self):
        with self.lock:
            roi = self.payload.get("roi")
            return dict(roi) if roi else None

    def set_roi(self, roi):
        normalized = normalize_roi(roi)
        with self.lock:
            self.payload["roi"] = normalized
            self._save_locked()
        return normalized

    def clear_roi(self):
        with self.lock:
            self.payload["roi"] = None
            self._save_locked()

    def get_stream_url(self):
        with self.lock:
            return self.payload.get("stream_url") or self.default_stream_url

    def set_stream_url(self, stream_url):
        normalized = normalize_stream_url(stream_url)
        with self.lock:
            self.payload["stream_url"] = normalized
            self._save_locked()
        return normalized

    def get_detection(self):
        with self.lock:
            return copy.deepcopy(self.payload["detection"])

    def set_detection(self, detection):
        with self.lock:
            normalized = normalize_detection_config(detection, self.payload["detection"])
            before = copy.deepcopy(self.payload["detection"])
            self.payload["detection"] = normalized
            self._save_locked()
            after = copy.deepcopy(normalized)
        return before, after

    def _load(self):
        payload = {
            "roi": None,
            "stream_url": self.default_stream_url,
            "detection": copy.deepcopy(self.default_detection),
        }
        if not os.path.exists(self.path):
            return payload

        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            payload["roi"] = normalize_roi(stored.get("roi"))
            if stored.get("stream_url"):
                payload["stream_url"] = normalize_stream_url(stored["stream_url"])
            payload["detection"] = normalize_detection_config(
                stored.get("detection") or {}, self.default_detection
            )
            return payload
        except (OSError, json.JSONDecodeError, ValueError):
            return payload

    def _save_locked(self):
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(self.payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, self.path)
