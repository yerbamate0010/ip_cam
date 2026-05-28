import os
import tempfile
import unittest

from config import load_settings
from detection_config import normalize_detection_config, runtime_values
from roi import RuntimeConfigStore


class DetectionConfigTest(unittest.TestCase):
    def test_default_runtime_config_uses_sensitive_profile(self):
        settings = load_settings()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RuntimeConfigStore(
                os.path.join(tmpdir, "config.json"),
                settings.stream_url,
                settings,
            )

            config = store.get_detection()

        self.assertEqual(config["profile"], "sensitive")
        self.assertEqual(config["model_path"], "yolov8s.pt")
        self.assertEqual(config["yolo_imgsz"], 1280)
        self.assertEqual(config["detect_width"], 1280)
        self.assertEqual(config["dog_conf"], 0.18)
        self.assertEqual(config["person_conf"], 0.32)
        self.assertEqual(config["trigger_labels"], ["dog", "person"])

    def test_normalize_custom_values_and_runtime_numbers(self):
        config = normalize_detection_config(
            {
                "profile": "custom",
                "model_path": "yolov8n.pt",
                "yolo_imgsz": "1536",
                "detect_width": "960",
                "dog_conf": "0.12",
                "person_conf": "0.31",
                "trigger_labels": ["dog"],
                "evidence_fps": "8",
            }
        )
        runtime = runtime_values(config)

        self.assertEqual(config["yolo_imgsz"], 1536)
        self.assertEqual(config["detect_width"], 960)
        self.assertEqual(runtime["yolo_imgsz"], 1536)
        self.assertEqual(runtime["detect_width"], 960)
        self.assertEqual(runtime["min_confidence"], 0.12)
        self.assertEqual(runtime["trigger_labels"], {"dog"})
        self.assertEqual(runtime["evidence_fps"], 8.0)

    def test_profile_name_applies_profile_values(self):
        config = normalize_detection_config({"profile": "stable"})

        self.assertEqual(config["profile"], "stable")
        self.assertEqual(config["yolo_imgsz"], 960)
        self.assertEqual(config["detect_width"], 960)
        self.assertEqual(config["dog_conf"], 0.24)
        self.assertEqual(config["person_conf"], 0.35)

    def test_profile_override_becomes_custom(self):
        config = normalize_detection_config(
            {
                "profile": "stable",
                "dog_conf": 0.2,
                "active_track_seconds": 20,
            }
        )

        self.assertEqual(config["profile"], "custom")
        self.assertEqual(config["detect_width"], 960)
        self.assertEqual(config["dog_conf"], 0.2)
        self.assertEqual(config["active_track_seconds"], 20.0)

    def test_string_false_disables_preview(self):
        config = normalize_detection_config({"preview_enabled": "false"})

        self.assertFalse(config["preview_enabled"])

    def test_store_returns_detection_copy(self):
        settings = load_settings()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RuntimeConfigStore(
                os.path.join(tmpdir, "config.json"),
                settings.stream_url,
                settings,
            )

            config = store.get_detection()
            config["trigger_labels"].append("mutated")

            self.assertEqual(store.get_detection()["trigger_labels"], ["dog", "person"])

    def test_rejects_empty_trigger_labels(self):
        with self.assertRaises(ValueError):
            normalize_detection_config({"trigger_labels": []})


if __name__ == "__main__":
    unittest.main()
