import argparse
import os
import cv2


def main():
    parser = argparse.ArgumentParser(
        description="Capture frames from an IP Webcam MJPEG stream and show them locally."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("CAM_STREAM_URL", "http://192.168.0.13:8080/video"),
        help="Full URL to the IP Webcam MJPEG stream (default from CAM_STREAM_URL or hardcoded).",
    )
    parser.add_argument(
        "--save",
        help="Optional filename to save one captured frame.",
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.url)
    if not cap.isOpened():
        raise RuntimeError(f"Nie udało się otworzyć strumienia: {args.url}")

    print(f"Otwieram strumień: {args.url}")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Błąd odczytu klatki z kamery.")
            break

        cv2.imshow("DroidCam", frame)

        if args.save:
            cv2.imwrite(args.save, frame)
            print(f"Zapisano klatkę: {args.save}")
            args.save = None

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
