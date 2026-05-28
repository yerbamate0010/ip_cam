from roi import boxes_to_full_frame, crop_frame
from video_utils import resize_for_detection


def resolve_yolo_device(requested):
    requested = (requested or "auto").strip().lower()
    if requested in {"cpu", "mps", "cuda"}:
        return requested
    if requested != "auto":
        return "cpu"

    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
    except (ImportError, AttributeError, RuntimeError):
        pass

    return "cpu"


def extract_boxes(result, sx, sy, confidence_by_label, target_labels):
    boxes = []
    names = result.names
    for box in result.boxes:
        label = names[int(box.cls[0])]
        if label not in target_labels:
            continue
        confidence = float(box.conf[0])
        if confidence < confidence_by_label.get(label, 1.0):
            continue

        x1, y1, x2, y2 = map(float, box.xyxy[0])
        boxes.append(
            (
                int(x1 * sx),
                int(y1 * sy),
                int(x2 * sx),
                int(y2 * sy),
                label,
                confidence,
            )
        )
    return boxes


class YoloDetector:
    def __init__(self, model_path, device="auto"):
        self.model_path = model_path
        self.requested_device = device
        self.device = resolve_yolo_device(device)
        from ultralytics import YOLO

        self.model = YOLO(model_path)

    def detect(self, frame, roi, detect_width, yolo_imgsz, confidence_by_label, target_labels):
        cropped, offset = crop_frame(frame, roi)
        detect_frame, sx, sy = resize_for_detection(cropped, detect_width)
        result = self._predict(detect_frame, yolo_imgsz, min(confidence_by_label.values()))
        boxes = extract_boxes(result, sx, sy, confidence_by_label, set(target_labels))
        return boxes_to_full_frame(boxes, offset)

    def _predict(self, frame, imgsz, confidence):
        kwargs = {
            "conf": confidence,
            "device": self.device,
            "verbose": False,
        }
        if imgsz > 0:
            kwargs["imgsz"] = imgsz
        try:
            return self.model(frame, **kwargs)[0]
        except Exception:
            if self.requested_device == "auto" and self.device != "cpu":
                self.device = "cpu"
                kwargs["device"] = self.device
                return self.model(frame, **kwargs)[0]
            raise
