# Keyboard Cleaner

Rozszerzenie **Omalaunch** pozwalające zablokować klawiaturę i urządzenia
wskazujące na wybrany czas, dzięki czemu można bezpiecznie wyczyścić
klawiaturę (np. ściereczką) bez przypadkowego naciskania klawiszy
i generowania niechcianych akcji.

An **Omalaunch** extension that temporarily blocks every keyboard and
pointing device so you can wipe them down without triggering anything.

## Jak używać / Usage

1. Otwórz Omalaunch i wpisz `keyboard-cleaner` albo wybierz skrót
   **Keyboard Cleaner** z katalogu **Extensions**.
2. Wybierz czas czyszczenia: **15 s**, **30 s** albo **1 minutę**.
3. Skrypt przechwyci klawiaturę, gładzik i mysz — od teraz żadne
   naciśnięcie ani ruch nie dociera do systemu. Bez dodatkowego okna:
   w prawym górnym rogu ekranu pojawi się notyfikacja pulpitu
   z odliczaniem — aktualizuje się co sekundę w tym samym okienku,
   nie nakłada kolejnych.
4. Po upływie wybranego czasu urządzenia zostaną automatycznie
   zwolnione, a notyfikacja zmieni się w krótki toast
   „Cleaning finished”. O ewentualnym błędzie (np. brak dostępu do
   `/dev/input/event*`) również poinformuje osobna notyfikacja.

1. Open Omalaunch, type `keyboard-cleaner`, or pick the **Keyboard
   Cleaner** shortcut from **Extensions**.
2. Pick a duration: **15 s**, **30 s**, or **1 minute**.
3. The script grabs the keyboard, trackpad, and mouse; nothing
   reaches the system. A single desktop pop-up (top-right) shows
   the remaining time and refreshes in place every second.
4. When the timer ends, the pop-up turns into a short
   „Cleaning finished” toast. Failures (e.g. missing `input`
   group membership) also surface as their own toast.

## How to abort early

- Najprościej: poczekaj na koniec odliczania — trwa to najwyżej
  minutę, a klawiatura wraca automatycznie.
- Zamknięcie sesji (wylogowanie, restart) też posprząta
  uchwycone urządzenia.

- Easiest: wait for the countdown. Input is restored automatically.
- Logging out or restarting also closes the file descriptors and
  releases the grab.

## Wymagania / Requirements

- Konto użytkownika musi należeć do grupy `input`, w której znajdują
  się wszystkie urządzenia `/dev/input/event*`:

  ```sh
  groups                    # sprawdź, czy 'input' jest na liście
  sudo usermod -aG input "$USER"
  # po tej zmianie trzeba się ponownie zalogować
  ```

- Dostępne są `python` oraz `setsid`. Na domyślnej instalacji
  Omarchy oba są już w `PATH`.
- Na Macach z Apple SPI klawiatura, gładzik i ewentualna mysz USB
  są wykrywane automatycznie. Skrypt pomija urządzenia, których
  nie da się bezpiecznie zablokować (np. przycisk zasilania, gniazdo
  słuchawek).

- Your account must be a member of the `input` group, which owns the
  `/dev/input/event*` nodes:

  ```sh
  groups                    # check whether 'input' is listed
  sudo usermod -aG input "$USER"
  # log out and back in for the group change to take effect
  ```

- `python` and `setsid` must be on `PATH`. Both ship with
  the default Omarchy install.

## How it works

- Skrypt czyta `/proc/bus/input/devices`, filtruje urządzenia klawiatury
  i wskazujące, otwiera każde z nich jako `/dev/input/eventX` i woła
  `EVIOCGRAB` przez `fcntl.ioctl`. To jądro przestaje dostarczać
  zdarzenia z uchwwyconego urządzenia — dokładnie to samo robi np.
  narzędzie `KeyboardCleanTool` na macOS.
- Złapanie trzymają deskryptory plików; jeśli skrypt się zakończy lub
  zostanie zamknięty, jądro automatycznie je zwalnia i klawiatura
  wraca natychmiast.
- Odliczanie w oknie terminala pozwala śledzić czas pozostały do
  końca blokady.

- The helper walks `/proc/bus/input/devices`, opens matching
  `/dev/input/eventX` nodes, and issues `EVIOCGRAB` via `fcntl.ioctl`.
  The kernel stops delivering events from every grabbed node — the
  same trick `KeyboardCleanTool` uses on macOS.
- Grabs live on the file descriptors. If the process is killed or the
  terminal closes, the kernel releases them automatically.
- The on-screen countdown shows how long is left before release.

## Pliki / Files

| Plik | Rola |
|---|---|
| `manifest.json` | Manifest wtyczki Omarchy (identyfikator `ozz1ee.keyboard-cleaner`). |
| `omalaunch.json` | Definicja rozszerzenia: tryb `workflow`, menu z trzema czasami czyszczenia. |
| `bin/keyboard-cleaner.py` | Skrypt pomocniczy wywoływany przez każdą akcję menu. |
| `AGENTS.md`, `CLAUDE.md`, `.gitignore` | Konwencje projektu wymagane przez kontrakt Omalaunch. |

## Validation

Po każdej zmianie uruchom z katalogu wtyczki:

```sh
omarchy plugin validate .
omarchy plugin enable ozz1ee.keyboard-cleaner
```

Pierwsze polecenie sprawdza poprawność JSON i kontraktu, drugie
przeładowuje wtyczkę, żeby Omalaunch ją zobaczył.
