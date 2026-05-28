import unittest

from detector import extract_boxes


class FakeBox:
    def __init__(self, cls, conf, xyxy):
        self.cls = [cls]
        self.conf = [conf]
        self.xyxy = [xyxy]


class FakeResult:
    names = {0: "person", 16: "dog"}

    def __init__(self, boxes):
        self.boxes = boxes


class DetectorFilterTest(unittest.TestCase):
    def test_filters_confidence_per_label(self):
        result = FakeResult(
            [
                FakeBox(16, 0.17, [10, 10, 20, 20]),
                FakeBox(16, 0.20, [30, 30, 40, 40]),
                FakeBox(0, 0.30, [50, 50, 60, 60]),
                FakeBox(0, 0.35, [70, 70, 80, 80]),
            ]
        )

        boxes = extract_boxes(
            result,
            1.0,
            1.0,
            {"dog": 0.18, "person": 0.32},
            {"dog", "person"},
        )

        self.assertEqual([box[4] for box in boxes], ["dog", "person"])
        self.assertEqual([round(box[5], 2) for box in boxes], [0.20, 0.35])


if __name__ == "__main__":
    unittest.main()
