import argparse
import dataclasses
import time

from config import load_settings, parse_target_labels
from monitor import DogMonitor


def main():
    parser = argparse.ArgumentParser(
        description="Run the same Dog Watch detection pipeline without the Flask panel."
    )
    parser.add_argument("--url", dest="stream_url", help="MJPEG stream URL from IP Webcam.")
    parser.add_argument("--model", dest="model_path", help="YOLO model name or path.")
    parser.add_argument("--conf", dest="confidence", type=float, help="Confidence threshold.")
    parser.add_argument("--target-labels", help="Comma-separated YOLO labels.")
    parser.add_argument("--output-dir", help="Directory where evidence files are saved.")
    parser.add_argument("--fps", dest="evidence_fps", type=float, help="Evidence video FPS; 0 means auto.")
    parser.add_argument("--detect-width", type=int, help="YOLO input width; 0 means auto.")
    parser.add_argument("--post-roll", dest="post_roll_seconds", type=int)
    parser.add_argument("--min-detections", type=int)
    parser.add_argument("--max-event-seconds", type=int)
    parser.add_argument("--reconnect-delay", type=int)
    parser.add_argument("--device", dest="yolo_device", choices=["auto", "cpu", "mps", "cuda"])
    args = parser.parse_args()

    settings = load_settings()
    overrides = {
        key: value
        for key, value in vars(args).items()
        if value is not None and key != "target_labels"
    }
    if args.target_labels is not None:
        overrides["target_labels"] = tuple(sorted(parse_target_labels(args.target_labels)))

    monitor = DogMonitor(dataclasses.replace(settings, **overrides))
    monitor.start()
    print(f"Dog Watch pipeline aktywny: {monitor.settings.stream_url}")
    print("Zatrzymaj przez Ctrl+C.")
    try:
        while True:
            status, _, _ = monitor.snapshot()
            if status.get("last_error"):
                print(status["last_error"])
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()
