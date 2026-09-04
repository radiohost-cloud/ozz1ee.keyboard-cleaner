# Changelog

All notable changes to `ozz1ee.keyboard-cleaner` are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-04

### Changed

- **Live desktop notification replaces the terminal countdown.** The helper
  no longer assumes it is running inside an interactive terminal. As soon
  as the input block starts it sends an Omarchy `Notify` message via
  `/usr/share/omarchy/bin/omarchy-notification-send`; the wrapper prints
  the assigned D-Bus id, and every subsequent tick passes that id back
  with `-r` so Quickshell refreshes the same pop-up instead of stacking
  fresh toasts. The pop-up carries the `nf-md-keyboard` glyph (U+F0313),
  matching the launcher icon, and the body updates in place: "Blocking
  keyboard and pointer. Releasing in {N}s — wipe safely." → "Cleaning
  keyboard — releasing in {N}s." → "Cleaning finished. Keyboard and
  pointer restored." on completion. Notifications are best-effort: if
  the wrapper is missing, the bus is down, or the daemon hangs, the
  grab and release path is unchanged.

- **Menu closes immediately on action pick.** Each workflow command now
  runs through `setsid --fork`, which forks into a new session and exits
  in 0 ms. Omalaunch sees the immediate successful exit, closes the
  plugin window, and returns to the launcher; the helper continues
  running in its own session for the full duration. Before this change
  the menu stayed open until the helper finished because Omalaunch
  dispatches non-terminal commands synchronously.

- **README lists `setsid` instead of `xdg-terminal-exec` as a runtime
  dependency.** The previous text was a leftover from the pre-popup
  flow that spawned a terminal window; the extension no longer uses
  `xdg-terminal-exec` at all.

- **`stdout` is silenced when no TTY is attached.** The helper now
  redirects `sys.stdout` to `/dev/null` unless `isatty()` is true, so
  prints inside the running block never write to a broken pipe. The
  user-visible countdown is delivered entirely through the desktop
  notification; terminal output is debug-only.

## [0.1.0] - 2026-09-04

### Added

- Initial release. Omalaunch workflow extension that grabs every
  keyboard and pointing device via `EVIOCGRAB` (`_IOW('E', 0x10, 4)`,
  ioctl 0x40044590) for a chosen duration — 15 s, 30 s, or 1 min —
  so the keyboard can be wiped without triggering keys. The helper
  walks `/proc/bus/input/devices`, classifies each entrypoint as a
  keyboard, a pointer, or a single-button device to skip, opens the
  matching `/dev/input/event*` node, and issues the ioctl on the file
  descriptor. Grabs live on the descriptors; a SIGTERM, SIGHUP,
  KeyboardInterrupt, or process exit triggers a best-effort release
  (`EVIOCGRAB` with 0) so the keyboard always comes back.
