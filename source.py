import json
import urllib.error
import urllib.parse
import urllib.request

import cv2


def camera_base_url(stream_url):
    parsed = urllib.parse.urlsplit(stream_url)
    scheme = "https" if parsed.scheme in ("https", "rtsps") else "http"
    return urllib.parse.urlunsplit((scheme, parsed.netloc, "", "", ""))


def ipwebcam_request(stream_url, path, params=None, timeout=5):
    url = f"{camera_base_url(stream_url)}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read()
        text = body.decode("utf-8", errors="replace")
        content_type = response.headers.get("Content-Type", "")
        payload = None
        if "application/json" in content_type or path.endswith(".json"):
            payload = json.loads(text)
        return {
            "ok": 200 <= response.status < 300,
            "status": response.status,
            "text": text,
            "json": payload,
            "url": url,
        }


class IpWebcamSource:
    source_type = "ip_webcam"

    def __init__(self, stream_url, timeout=5):
        self.stream_url = stream_url
        self.timeout = timeout
        self.capture = None

    def open(self):
        self.close()
        self.capture = cv2.VideoCapture()
        timeout_ms = int(max(1, self.timeout) * 1000)
        for prop_name in ("CAP_PROP_OPEN_TIMEOUT_MSEC", "CAP_PROP_READ_TIMEOUT_MSEC"):
            prop = getattr(cv2, prop_name, None)
            if prop is not None:
                self.capture.set(prop, timeout_ms)
        self.capture.open(self.stream_url)
        return self.capture.isOpened()

    def read(self):
        if self.capture is None:
            return False, None
        return self.capture.read()

    def close(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def status(self):
        try:
            response = ipwebcam_request(
                self.stream_url,
                "status.json",
                {"show_avail": 1},
                timeout=min(self.timeout, 2),
            )
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

        payload = response.get("json") or {}
        return dict(payload.get("curvals", payload))
