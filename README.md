# GrokKDE_deskBuddy

An always-on Grok button for a KDE Plasma Wayland session. It sits in the corner of the screen. Left-click opens the chat. Right-click opens Log in, Log out, Refresh chat, Autostart, and Exit. Refresh chat drops the current session so the next message starts with an empty context.

This is not an official Grok or KDE app. The Grok name and mark belong to their owners.

## Requirements

- KDE Plasma on Wayland
- Python 3
- [PySide6](https://doc.qt.io/qtforpython/) (`pyside6` on Arch)
- [layer-shell-qt](https://invent.kde.org/plasma/layer-shell-qt) so the button can float over other windows
- The Grok CLI at `~/.grok/bin/grok`, signed in with `grok login`

Each message is one Grok turn with `--yolo`, so tool use is approved automatically.

## Install

```sh
git clone https://github.com/shadeacademia/GrokKDE_deskBuddy.git
cd GrokKDE_deskBuddy
./install.sh
```

That registers the app in the launcher, installs the icon, turns autostart on, and links `grok-corner` into `~/.local/bin`. Run it again after moving the folder. If autostart was switched off, the script leaves it off and only refreshes the paths.

Start it now with `grok-corner`, or from the Grok Corner launcher entry. A second start does nothing if it is already running.
