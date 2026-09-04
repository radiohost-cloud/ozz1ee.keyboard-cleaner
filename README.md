# Keyboard Cleaner

An **Omalaunch** extension that temporarily blocks every keyboard and
pointing device so you can wipe them down without triggering anything —
the same trick `KeyboardCleanTool` uses on macOS, with a live desktop
pop-up showing the remaining time.

## What it does

The plugin adds a **Keyboard Cleaner** shortcut to Omalaunch's
**Extensions** directory. Opening it shows a small menu with three
durations: **15 seconds**, **30 seconds**, and **1 minute**.

Pick one and the helper walks `/proc/bus/input/devices`, classifies each
entrypoint as a keyboard, a pointer, or a single-button device to skip,
opens the matching `/dev/input/event*` node, and issues `EVIOCGRAB` on
the file descriptor. The kernel stops delivering events from every
grabbed node until the timer expires.

- No terminal window. The launcher closes the moment you pick a duration
  and the helper detaches into its own session.
- A single desktop pop-up (top-right) appears with the keyboard glyph,
  announces "Blocking keyboard and pointer. Releasing in N s — wipe
  safely." and refreshes in place every second until the timer ends.
- On completion the pop-up turns into a short "Cleaning finished"
  toast. Failures (no `input` group membership, all devices refusing
  `EVIOCGRAB`, no input nodes visible) surface as their own notification
  — there is no stderr to look at.

## Requirements

- `python` — runs `bin/keyboard-cleaner.py` (Python 3, base Omarchy
  install).
- `setsid` — used as `setsid --fork` so the helper detaches into a new
  session and the menu closes immediately. Ships with `util-linux` on
  every default Omarchy install.

Your account must be a member of the `input` group, which owns the
`/dev/input/event*` nodes:

```sh
groups                    # check whether 'input' is listed
sudo usermod -aG input "$USER"
# log out and back in for the group change to take effect
```

A notification channel is recommended but optional. The helper shells
out to `/usr/share/omarchy/bin/omarchy-notification-send`; if the wrapper
is missing, the bus is down, or the daemon hangs, the grab and release
path is unchanged. Every `notify()` failure is swallowed on purpose — a
glitchy notification channel must never delay the keyboard release.

## Installation

The preferred install path is `omarchy plugin add`, which clones the
repository into `~/.config/omarchy/plugins/` and enables the plugin in
one step:

```sh
omarchy plugin add https://github.com/radiohost-cloud/ozz1ee.keyboard-cleaner --enable
```

After the plugin is on disk, you can validate it from the plugin
directory itself:

```sh
omarchy plugin validate ~/.config/omarchy/plugins/ozz1ee.keyboard-cleaner
omarchy plugin enable  ozz1ee.keyboard-cleaner
```

### Manual install (alternative)

If you want to install from a local checkout instead of a git URL, copy
the directory into the user-local plugin root Omarchy watches:

```sh
git clone https://github.com/radiohost-cloud/ozz1ee.keyboard-cleaner
cp -r ozz1ee.keyboard-cleaner ~/.config/omarchy/plugins/
omarchy plugin enable ozz1ee.keyboard-cleaner
```

## Removal

The preferred removal path is `omarchy plugin remove`, which deletes the
plugin directory and clears its enablement:

```sh
omarchy plugin remove ozz1ee.keyboard-cleaner
```

### Manual removal (alternative)

```sh
omarchy plugin disable ozz1ee.keyboard-cleaner
rm -rf ~/.config/omarchy/plugins/ozz1ee.keyboard-cleaner
```

The extension never mutates any user data, so disabling it leaves no
trace. It does not uninstall `python`, `setsid`, or the kernel-side
`EVIOCGRAB` machinery; those are owned by your distribution and used
by many other programs.

## Privilege boundaries

This extension runs as the current user with no elevated privileges:

- Reads `/proc/bus/input/devices` (world-readable on Linux).
- Opens `/dev/input/event*` nodes owned by the `input` group; the helper
  requires membership in that group and never escalates via `sudo`,
  `setuid`, or `pkexec`.
- Shells out to `setsid --fork` (no input from the user is interpolated
  into argv; the duration is passed as a single integer argument).
- Shells out to `/usr/share/omarchy/bin/omarchy-notification-send` for
  best-effort desktop notifications; every argument is a fixed string or
  the captured D-Bus id, never shell-substituted.
- Does not call any package manager, does not modify any system file,
  does not read or write outside `/dev/input/`, `/proc/bus/input/`, and
  `/dev/null`.
- Does not open network sockets.
- Does not require `sudo` at any point.

Removing the plugin removes every byte it ever wrote.

## Usage

1. Open Omalaunch.
2. Type `keyboard-cleaner`, or pick **Keyboard Cleaner** from
   **Extensions**.
3. Pick a duration: **15 seconds**, **30 seconds**, or **1 minute**.
4. The menu closes immediately, the desktop pop-up appears, and your
   keyboard and pointer stop responding. Wipe away.
5. When the timer ends the pop-up turns into a "Cleaning finished"
   toast and input is restored automatically.

## How it works (and why setsid)

When you pick a duration, the row's command is:

```json
["setsid", "--fork", "python", "{extensionDir}/bin/keyboard-cleaner.py", "<seconds>"]
```

`setsid --fork` forks into a new session and exits immediately, so
Omalaunch sees a successful exit in 0 ms and closes the launcher
(`closeOnSuccess: true` is the default behaviour). The helper keeps
running in its own session for the full duration; it is not a child of
the launcher and survives the launcher's exit.

Omalaunch does not auto-detach non-terminal commands — only `xdg-terminal-exec`
and `omarchy-launch-terminal` are special-cased (per Omalaunch's
`EXTENSIONS.md` contract). Without `setsid --fork` the launcher would
wait 30 s and SIGTERM the helper, which would release the grab early.
`setsid --fork` is the smallest piece that buys us the "close
immediately" behaviour without taking on the terminal-leaf detour.

### The grab itself

Inside the helper:

1. Open `/proc/bus/input/devices` and parse each block into a
   `{name, event, ev, key}` record.
2. Classify the device as `keyboard`, `pointer`, or `skip` from its
   `EV_*` mask and `KEY_*` bit set. Devices with EV_KEY but only a
   handful of bits set (power button, lid switch, headphone jack) are
   skipped on purpose — grabbing them would block events you still want
   (power, audio).
3. Open the matching `/dev/input/eventX` node and call
   `fcntl.ioctl(fd, 0x40044590 /* EVIOCGRAB */, 1)`. The kernel stops
   delivering events from that node while the fd is held.
4. Send the initial desktop notification with `urgency=normal` and the
   `nf-md-keyboard` glyph; capture the D-Bus id it prints.
5. Sleep in 0.25 s slices, recomputing `remaining = deadline - now` each
   slice, refreshing the pop-up in place with `urgency=low` and
   `replaces=<id>`.
6. On natural completion, SIGTERM, SIGHUP, or KeyboardInterrupt, call
   `EVIOCGRAB` with 0 on every fd to release, close the fds, and send
   the "Cleaning finished" toast.

### Why every notification failure is swallowed

The notification path is best-effort: a stuck bus daemon, a hung
wrapper, or a missing `/usr/share/omarchy/bin/omarchy-notification-send`
must never delay the keyboard release. The helper wraps each call in a
0.5 s `subprocess.run(timeout=0.5)`, catches `OSError` and
`TimeoutExpired`, and treats non-zero exit codes as "no id captured".
When the id is missing the next tick falls back to a fresh notification
instead of replacing — the user still sees the countdown, just as a
new pop-up instead of a refreshed one.

## Known limitations

- **Apple SPI keyboards, trackpads, and internal keyboards.** The
  classifier uses a heuristic on `EV_*` masks and `KEY_*` bit counts; it
  works on every Mac and PC keyboard, trackpad, mouse, drawing tablet,
  and touchscreen we have tried. If a vendor ships a device with an
  exotic descriptor the heuristic may classify it as `skip` and the
  device will keep delivering events while the rest are blocked.
- **Power button, lid switch, headphone-jack buttons.** These are
  intentionally not grabbed. Grabbing them would block system events
  you still want (suspend, audio). If you specifically want to clean
  near those, prefer `input` group membership plus a wipe during the
  timer rather than blocking them.
- **No early abort.** There is no signal path to release early from
  the launcher. The shortest available duration is 15 s — wait it out,
  log out, or restart. The kernel releases the grabs automatically on
  process exit either way.
- **Notification styling on non-Omarchy installs.** If
  `/usr/share/omarchy/bin/omarchy-notification-send` is missing the
  helper falls through silently and the pop-up never appears; the
  terminal-style countdown is also gone because `stdout` is redirected
  to `/dev/null` outside a TTY. On non-Omarchy installs the keyboard
  block still works but there is no user-visible countdown.
- **Concurrent keyboard-cleaner invocations.** A second invocation
  while a first is running will see all `event*` nodes already grabbed
  and report "All input devices refused EVIOCGRAB". Wait for the first
  one to finish, or release it manually by killing the running
  process.

## Files

```
omalaunch.json        extension definition (mode: workflow, three durations)
bin/keyboard-cleaner.py
                      Python 3 helper: parses /proc/bus/input/devices,
                      opens /dev/input/event*, issues EVIOCGRAB,
                      drives the per-second popup refresh, releases on
                      exit/signal
manifest.json         Omarchy plugin manifest (kinds: extension)
CHANGELOG.md          version history
LICENSE               MIT license
```

## See also

- `AGENTS.md` — project-specific rules (atomic file replacement, validate
  before enable, no temp files inside the plugin directory).
- [Omalaunch Extension Directory](https://github.com/DanielLemky/omalaunch-extensions) —
  the community catalog where this extension is listed.
