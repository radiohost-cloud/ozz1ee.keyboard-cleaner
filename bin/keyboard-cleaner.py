#!/usr/bin/env python3
"""Grab every keyboard and pointing device for the requested duration.

Reads /proc/bus/input/devices, opens matching /dev/input/event* nodes and
issues EVIOCGRAB so the kernel stops delivering their events until the
timeout expires. Releases every grabbed device on exit, signal, or fatal
error so the keyboard always comes back even on crashes.

Output is plain text intended for an interactive terminal. The launcher
dispatches this helper through xdg-terminal-exec so the Omalaunch UI can
close immediately while the cleaning window stays on screen.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# EVIOCGRAB on Linux/amd64: _IOW('E', 0x10, 4) -> 0x40044590.
# The size (sizeof int) is the same on every 64-bit Linux ABI we target.
EVIOCGRAB = 0x40044590

EV_KEY = 1
EV_REL = 2
EV_ABS = 3
EV_MSC = 4
EV_SW = 5
EV_LED = 0x11
EV_SND = 0x12
EV_REP = 0x14
EV_FF = 0x15
EV_PWR = 0x16

# KEY bit positions (input-event-codes.h). We use them only to tell whether
# a device actually carries keyboard letters rather than a single button.
KEY_Q = 16
KEY_LEFTCTRL = 29
KEY_LEFTALT = 56
KEY_KPENTER = 96

INPUT_DEVICES_PATH = Path("/proc/bus/input/devices")
INPUT_EVENT_ROOT = Path("/dev/input")

MIN_DURATION = 1
MAX_DURATION = 60 * 60

# PUA codepoint for nf-md-keyboard — matches the launcher icon so the pop-up and the
# extension shortcut read as the same action. Stays a plain string so the rest of the
# script never has to care about encoding.
KEYBOARD_GLYPH = "\U000F0313"

# Omarchy ships a notification wrapper at this fixed path that talks to Quickshell's
# org.freedesktop.Notifications over busctl. Treating it as optional keeps the grab/
# release logic identical for non-Omarchy installs.
OMARCHY_NOTIFY = Path("/usr/share/omarchy/bin/omarchy-notification-send")
OMARCHY_NOTIFY_AVAILABLE = OMARCHY_NOTIFY.is_file()


def parse_input_devices() -> list[dict[str, object]]:
    """Read /proc/bus/input/devices into a structured list.

    Returns one entry per device with the values we care about: a human
    name, the eventX handler, and the populated bitset columns.
    """
    try:
        raw = INPUT_DEVICES_PATH.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []

    entries: list[dict[str, object]] = []
    current: dict[str, object] = {}

    for line in raw.splitlines():
        if line.startswith("N:"):
            current["name"] = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("H:"):
            for handler in line.split(":", 1)[1].split():
                if handler.startswith("event"):
                    current["event"] = handler
        elif line.startswith("B: EV="):
            with contextlib.suppress(ValueError):
                current["ev"] = int(line.split("=", 1)[1].strip(), 16)
        elif line.startswith("B: KEY="):
            parts = line.split("=", 1)[1].split()
            bits = 0
            for index, part in enumerate(parts):
                with contextlib.suppress(ValueError):
                    bits |= int(part, 16) << (index * 32)
            current["key"] = bits
        elif line.strip() == "":
            if current.get("event"):
                entries.append(current)
            current = {}

    if current.get("event"):
        entries.append(current)

    return entries


def categorize(device: dict[str, object]) -> str:
    """Decide whether to grab a device as `keyboard`, `pointer`, or skip it.

    Heuristic:
    - Anything that reports relative or absolute axes is treated as a
      pointing device (mouse, trackpad, drawing tablet, touchscreen).
    - Devices with EV_KEY and many KEY bits are real keyboards.
    - Devices with EV_KEY and very few KEY bits are buttons (power, lid,
      headphone-jack), which we leave untouched.
    """
    ev = int(device.get("ev", 0))
    key = int(device.get("key", 0))
    has_rel = bool(ev & (1 << EV_REL))
    has_abs = bool(ev & (1 << EV_ABS))
    has_key_event = bool(ev & (1 << EV_KEY))

    if has_rel or has_abs:
        return "pointer"

    if has_key_event:
        # Keyboard keys span most of the KEY bitset. A power-button or
        # lid-switch entry usually has only one bit set.
        if key & ((1 << KEY_LEFTCTRL) - 1):
            return "keyboard"
        if key >> KEY_LEFTCTRL and key >> KEY_KPENTER:
            return "keyboard"
        if key & ((1 << KEY_Q) - 1):
            return "keyboard"
        return "skip"

    return "skip"


def grab_devices(categories: set[str]) -> tuple[list[tuple[int, str, str]], list[tuple[str, str, str]]]:
    """Open every matching device and try to EVIOCGRAB it.

    Returns a tuple `(grabbed, skipped)` where `grabbed` carries the live
    file descriptors and `skipped` records reasons so the helper can
    explain why a particular device wasn't blocked.
    """
    grabbed: list[tuple[int, str, str]] = []
    skipped: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for device in parse_input_devices():
        event = device.get("event")
        name = str(device.get("name", "unknown device"))
        if not isinstance(event, str) or event in seen:
            continue
        seen.add(event)

        category = categorize(device)
        if category not in categories:
            continue

        path = INPUT_EVENT_ROOT / event
        try:
            fd = os.open(str(path), os.O_RDWR | os.O_NONBLOCK)
        except OSError as error:
            skipped.append((name, str(path), error.strerror or str(error)))
            continue

        try:
            fcntl.ioctl(fd, EVIOCGRAB, 1)
        except OSError as error:
            os.close(fd)
            skipped.append((name, str(path), error.strerror or str(error)))
            continue

        grabbed.append((fd, str(path), name))

    return grabbed, skipped


def release_devices(grabbed: list[tuple[int, str, str]]) -> None:
    """Best-effort release of every grabbed device."""
    for fd, path, name in grabbed:
        try:
            fcntl.ioctl(fd, EVIOCGRAB, 0)
        except OSError as error:
            print(f"  ! could not release {name} ({path}): {error.strerror or error}", file=sys.stderr)
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)


def has_input_group() -> bool:
    """Return True if the current user can presumably open input nodes."""
    try:
        import grp
        return grp.getgrnam("input").gr_gid in os.getgroups()
    except (KeyError, OSError):
        return False


def notify(*, replaces=None, urgency="low", headline="Keyboard Cleaner",
           body="", glyph="") -> int | None:
    """Best-effort desktop notification via Omarchy's wrapper.

    Returns the assigned D-Bus notification id when `replaces` is None and the
    wrapper is told to print it; subsequent calls pass that id back through
    `replaces=` so Quickshell refreshes the same pop-up instead of stacking new
    ones. Every failure (missing wrapper, bus down, daemon hung) is swallowed —
    a glitchy notification channel must never delay the keyboard release.
    """
    if not OMARCHY_NOTIFY_AVAILABLE:
        return None
    argv = [str(OMARCHY_NOTIFY), "-u", urgency]
    if replaces:
        argv += ["-r", str(int(replaces))]
    if glyph:
        argv += ["-g", glyph]
    argv += [headline, body]
    print_id = replaces is None
    if print_id:
        argv.append("-p")
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=0.5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    if not print_id:
        return None
    out = proc.stdout.strip()
    return int(out) if out.isdigit() else None


def render_table(rows: list[tuple[str, str]], columns: tuple[str, str, int]) -> str:
    """Build a two-column table for consistent terminal output."""
    label_width = max((len(label) for label, _ in rows), default=0)
    width = max(label_width, len(columns[0]))
    lines = []
    header = f"  {columns[0].ljust(width)}  {columns[1]}"
    lines.append(header)
    lines.append("  " + ("-" * width) + "  " + ("-" * len(columns[1])))
    for label, value in rows:
        lines.append(f"  {label.ljust(width)}  {value}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("seconds", type=int, help="how long to block input (seconds)")
    args = parser.parse_args(argv)

    # When the launcher dispatches us directly (no terminal attached), every
    # print() would otherwise write to a broken pipe and spam the busctl log.
    # The desktop notification carries the user-visible progress; stdout is
    # debug-only, so silence it unless the host gave us a real TTY.
    if not sys.stdout.isatty():
        sys.stdout = open(os.devnull, "w", encoding="utf-8")

    if not MIN_DURATION <= args.seconds <= MAX_DURATION:
        notify(
            urgency="normal",
            body=(
                f"Duration must be between {MIN_DURATION} and {MAX_DURATION} seconds."
            ),
        )
        return 2

    duration = args.seconds
    categories = {"keyboard", "pointer"}

    print(f"Blocking keyboard and pointer devices for {duration} second(s).")

    grabbed, skipped = grab_devices(categories)

    if not grabbed:
        if not has_input_group():
            notify(
                urgency="normal",
                body=(
                    "Could not grab any input devices: your user is not in the "
                    "'input' group. Run `sudo usermod -aG input $USER` and log out."
                ),
            )
        elif skipped:
            reasons = "; ".join(f"{name}: {reason}" for name, _, reason in skipped)
            notify(
                urgency="normal",
                body=f"All input devices refused EVIOCGRAB ({reasons}).",
            )
        else:
            notify(
                urgency="normal",
                body="No input devices could be grabbed. Check /dev/input/event* access.",
            )
        return 1

    device_rows: list[tuple[str, str]] = []
    for _, path, name in grabbed:
        device_rows.append((name, path))
    print(render_table(device_rows, ("Device", "Path", 0)))
    print()

    if skipped:
        print("Skipped devices (not grabbed):")
        for name, path, reason in skipped:
            print(f"  - {name} ({path}): {reason}")
        print()

    interrupted = False

    def cleanup() -> None:
        nonlocal interrupted
        interrupted = True
        sys.stdout.write("\r\033[K")
        print("Releasing input devices...")
        release_devices(grabbed)
        print("Done. Input is restored.")
        notify(
            urgency="low",
            body="Cleaning finished. Keyboard and pointer restored.",
        )

    def handle_signal(signum: int, frame: object) -> None:
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGHUP, handle_signal)

    notif_id = notify(
        urgency="normal",
        glyph=KEYBOARD_GLYPH,
        body=(
            f"Blocking keyboard and pointer. Releasing in {duration}s — "
            "wipe safely."
        ),
    ) or 0

    deadline = time.monotonic() + duration
    try:
        while not interrupted:
            remaining = int(round(deadline - time.monotonic()))
            if remaining <= 0:
                break
            print(f"\r  Releasing in {remaining:3d} second(s)... ", end="", flush=True)
            if notif_id:
                notify(
                    replaces=notif_id,
                    urgency="low",
                    glyph=KEYBOARD_GLYPH,
                    body=f"Cleaning keyboard — releasing in {remaining}s.",
                )
            time.sleep(min(0.25, max(deadline - time.monotonic(), 0)))
    except KeyboardInterrupt:
        pass
    finally:
        if not interrupted:
            cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
