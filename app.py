import atexit
import os
import time

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from config import load_settings
from monitor import DogMonitor


settings = load_settings()
app = Flask(__name__)
monitor = DogMonitor(settings)


def should_start_monitor():
    flask_debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    return not flask_debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def start_monitor():
    if should_start_monitor():
        monitor.start()
        atexit.register(monitor.stop)


@app.route("/")
def index():
    return render_template("index.html", default_stream=settings.stream_url)


@app.route("/preview.mjpg")
def preview():
    def generate():
        while True:
            _, _, jpeg = monitor.snapshot()
            if jpeg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.2)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    status, events, _ = monitor.snapshot()
    return jsonify({"status": status, "events": events})


@app.route("/api/config")
def api_config():
    return jsonify(monitor.config_snapshot())


@app.route("/api/detection-config")
def api_detection_config():
    return jsonify(monitor.detection_config_snapshot())


@app.route("/api/detection-config", methods=["PUT"])
def api_update_detection_config():
    payload = request.get_json(silent=True) or {}
    try:
        result = monitor.update_detection_config(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.route("/api/roi", methods=["PUT"])
def api_set_roi():
    payload = request.get_json(silent=True) or {}
    try:
        roi = monitor.set_roi(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"roi": roi})


@app.route("/api/roi", methods=["DELETE"])
def api_clear_roi():
    monitor.clear_roi()
    return jsonify({"roi": None})


@app.route("/api/stream", methods=["PUT"])
def api_set_stream():
    payload = request.get_json(silent=True) or {}
    try:
        stream_url = monitor.set_stream_url(payload.get("stream_url") or payload.get("url"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"stream_url": stream_url})


@app.route("/output/<path:filename>")
def output_file(filename):
    return send_from_directory(settings.output_dir, filename)


@app.route("/download/<path:filename>")
def download_file(filename):
    return send_from_directory(settings.output_dir, filename, as_attachment=True)


if __name__ == "__main__":
    flask_debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    start_monitor()
    app.run(host="0.0.0.0", port=8000, debug=flask_debug, threaded=True)
