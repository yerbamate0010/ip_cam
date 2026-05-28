# TODO

## Ustawienia Detekcji

- [x] Dodac panel ustawien detekcji poza kompaktowym statusem.
- [x] Dodac osobne progi confidence dla `person` i `dog`.
- [x] Dodac wybor szerokosci YOLO: `960`, `1280`, `1536`, `auto`.
- [x] Dodac ustawienia interwalow detekcji: spoczynek i po trafieniu.
- [x] Dodac ustawienia `post-roll` i liczby minimalnych trafien.

## Profile

- [x] Dodac profile: `Stabilny`, `Czuly`, `Max detal`.
- [ ] Ustalic konkretne wartosci profili po testach z realnymi nagraniami.
- [x] Pokazywac aktywny profil w panelu.

## ROI I Kadr

- [ ] Doprecyzowac najlepszy ROI dla podworka z 5 pietra.
- [ ] Rozwazyc wiele ROI tylko jesli jeden prostokat bedzie niewystarczajacy.
- [x] Pokazywac w statusie rozmiar ROI w pikselach.

## Material Dowodowy

- [ ] Ustalic, czy trigger ma startowac po `person`, `dog`, czy dowolnym z nich.
- [ ] Rozwazyc osobny zapis zdjec: pelna klatka plus crop ROI.
- [ ] Rozwazyc konwersje wideo do formatu pewnie odtwarzanego w przegladarce.
- [ ] Dodac tryb zapisu `ROI wideo + pelne zdjecia` jako kandydat na domyslny.
- [ ] Dodac tryb `Tylko zdjecia` dla bardzo malego zuzycia dysku.
- [x] Dodac ustawienie FPS zapisu wideo: `4`, `6`, `8`, `12`.
- [ ] Dodac ustawienie interwalu pelnych zdjec: `1s`, `2s`, `5s`.
- [x] Zmniejszyc domyslny `post-roll` do zakresu `30-40s` albo wyniesc go do ustawien.
- [ ] Rozwazyc transkodowanie zakonczonych klipow do H.264 przez `ffmpeg`.
- [ ] Przy zapisie ROI wideo zachowac pelne zdjecia kontekstowe: start, najlepsza detekcja, koniec.

## Testy

- [ ] Zebrac kilka nagran testowych: czlowiek, pies, cien, lawka, brak zdarzen.
- [ ] Porownac `yolov8n.pt` i `yolov8s.pt`.
- [ ] Porownac `1080p + ROI` z `4K + ROI`.
