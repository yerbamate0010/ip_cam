# ip_cam

Projekt do podglądu strumienia z IP Webcam i wykrywania psów przez YOLO.

## Co zawiera

- `app.py` — serwer Flask, API i panel webowy.
- `monitor.py` — orkiestracja pipeline: wejście, detekcja, zapis i status.
- `source.py` — źródło klatek z IP Webcam.
- `detector.py` — YOLO, wybór device i mapowanie wyników z ROI na pełny kadr.
- `roi.py` — zapis i przeliczanie użytecznego cropa.
- `recorder.py` — zapis zdjęć i pełnoklatkowych filmów dowodowych.
- `templates/index.html` — strona HTML z podgladem, statusem detekcji i parametrami streamu.
- `capture.py` — skrypt do przechwytywania klatek z MJPEG i podglądu w OpenCV.
- `dog_detector.py` — ten sam pipeline bez panelu Flask, uruchamiany z terminala.
- `requirements.txt` — potrzebne zależności Python.

## Jak uruchomić

1. Zainstaluj zależności:

```bash
pip install -r requirements.txt
```

2. Uruchom aplikację webową:

```bash
YOLO_DEVICE=auto python app.py
```

3. Otwórz w przeglądarce:

```
http://localhost:8000
```

4. Panel sam użyje domyślnego adresu strumienia IP Webcam:

- `http://192.168.0.13:8080/video`

Panel pokazuje podgląd z oznaczeniem psa/osoby, bieżący FPS, wykrytą rozdzielczość klatki, dobrany profil YOLO, wybrany device i aktywność ROI. Przycisk `ROI` pozwala zaznaczyć na podglądzie użyteczny prostokąt dla detekcji. Pole adresu kamery pozwala zmienić stream bez restartu Flask, np. po przejściu z routera na hotspot telefonu. Zapisane wideo zostaje pełnoklatkowe; crop dotyczy tylko YOLO.

Panel wykrywa domyślnie klasy YOLO `dog` i `person`. Pies jest oznaczany na zielono, człowiek na niebiesko. To jest praktyczniejsze dla kadru z dużej odległości: człowiek zwykle ma więcej pikseli i jest wykrywany stabilniej niż mały pies.

Zalecany punkt startowy dla stabilności:

- `1280x720`, jakość JPEG `70-80`
- jeśli detekcja jest stabilna i potrzeba więcej szczegółów, spróbuj `1920x1080`
- `3840x2160` jest ciężkie dla MJPEG, dekodowania OpenCV i YOLO; używaj tylko do krótkich testów

## Przechwytywanie klatek z kamery

```bash
python capture.py --url http://192.168.0.13:8080/video
```

Aby zapisać jedną klatkę:

```bash
python capture.py --url http://192.168.0.13:8080/video --save frame.jpg
```

## Detekcja psów i nagrywanie zdarzeń

Pipeline zapisuje pełną klatkę z kamery jako materiał dowodowy, a do YOLO podaje pomniejszoną kopię albo zaznaczony ROI. Dzięki temu nagranie może zostać w wysokiej jakości, a detekcja nie musi liczyć pełnego 4K.

Zalecany start dla IP Webcam:

```bash
./venv/bin/python dog_detector.py \
  --url http://192.168.0.13:8080/video \
  --model yolov8n.pt \
  --target-labels dog,person \
  --post-roll 60 \
  --min-detections 2 \
  --device auto
```

- `--detect-width 0` dobiera rozmiar wejścia YOLO automatycznie.
- `--device auto` użyje `mps` na MacBooku M1, jeśli jest dostępne, a na Raspberry Pi 5 zostanie przy `cpu`.
- `--target-labels dog,person` pozwala nagrywać po wykryciu psa albo człowieka.
- `--post-roll 60` nagrywa jeszcze 60 sekund po zniknięciu psa z kadru.
- `--min-detections 2` wymaga dwóch kolejnych detekcji psa przed startem nagrania.

Pliki zostaną zapisane w katalogu `output/images` i `output/videos`. Katalog `output/` jest ignorowany przez Git.

Auto-profil dla typowych rozdzielczości dobiera szerokość wejścia YOLO i FPS zapisu:

- `1280x720`: YOLO 960 px, zapis 15 FPS
- `1920x1080`: YOLO 960 px, zapis 12 FPS
- `2560x1440`: YOLO 768 px, zapis 10 FPS
- `3840x2160`: YOLO 640 px, zapis 8 FPS

Jakość zapisanego wideo zawsze pozostaje taka jak źródło z telefonu.

Panel webowy dodatkowo nie odpala YOLO na stałe co kilka klatek. W stanie spoczynku wykonuje detekcję co `IDLE_DETECT_SECONDS` sekund, domyślnie co 2 sekundy. Po pierwszym trafieniu przełącza się na `ACTIVE_DETECT_SECONDS`, domyślnie 0.5 sekundy, i utrzymuje aktywne śledzenie przez `ACTIVE_TRACK_SECONDS`, domyślnie 12 sekund. Te wartości można zmienić zmiennymi środowiskowymi przed uruchomieniem `app.py`.

## IP Webcam

W IP Webcam endpoint podglądu to zwykle `http://IP:8080/`, stream MJPEG dla OpenCV to `http://IP:8080/video`, a pojedyncze zdjęcie to `http://IP:8080/shot.jpg`.

Adres streamu można zmienić bez restartu aplikacji w panelu webowym. Wpisanie samego `IP:8080` zostanie zamienione na `http://IP:8080/video`.

Panel używa API IP Webcam `status.json?show_avail=1` tylko do odczytu aktualnych ustawień. Rozdzielczość i jakość JPEG ustawiaj w aplikacji IP Webcam na telefonie. Po zmianie zatrzymaj i uruchom ponownie serwer kamery na telefonie, a panel sam odczyta nowe parametry po ponownym połączeniu.
