#!/usr/bin/env bash
# Launch Photo Recognition on Linux.
# Creates .venv and installs dependencies on first run; reuses them afterwards.
set -euo pipefail
cd "$(dirname "$0")"

VENV=.venv
PYTHON=${PYTHON:-python3}

if [ ! -x "$VENV/bin/python" ]; then
    echo "Creating virtual environment in $VENV ..."
    if ! "$PYTHON" -m venv "$VENV"; then
        echo "Could not create a virtual environment." >&2
        echo "Install the venv support package first, e.g.:" >&2
        echo "  sudo apt install python3-venv    (Debian/Ubuntu)" >&2
        echo "  sudo dnf install python3-devel   (Fedora)" >&2
        exit 1
    fi
fi

if ! "$VENV/bin/python" -c 'import tkinter' 2>/dev/null; then
    echo "Tkinter is not available for the Python in $VENV." >&2
    echo "Install the Tk package for your system Python, e.g.:" >&2
    echo "  sudo pacman -S tk                  (Arch)" >&2
    echo "  sudo apt install python3-tk        (Debian/Ubuntu)" >&2
    echo "  sudo dnf install python3-tkinter   (Fedora)" >&2
    echo "Then run this script again." >&2
    exit 1
fi

if ! "$VENV/bin/python" -c 'import PIL, ttkbootstrap, requests' 2>/dev/null; then
    echo "Installing dependencies ..."
    "$VENV/bin/python" -m pip install -r requirements.txt
fi

exec "$VENV/bin/python" main.py "$@"
