#!/usr/bin/env bash
set -euo pipefail

# ---------- DEFAULT MODE ----------
MODE=${1:-nuitka}
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_DIR"

echo "Checking Python version..."
python3 --version

# ---------- PLATFORM DETECTION ----------
OS_TYPE=$(uname -s)
if [ "$OS_TYPE" = "Linux" ]; then
    DIST_DIR="dist_linux"
elif [[ "$OS_TYPE" =~ ^MINGW|^CYGWIN|^MSYS|^Windows_NT$ ]]; then
    DIST_DIR="dist_windows"
else
    echo "Unsupported OS: $OS_TYPE"
    exit 1
fi

# ---------- HELP FUNCTION ----------
show_help() {
cat << EOF
Usage: ./build_linux_exe.sh [MODE]

This script builds a standalone executable for the Meter Simulator project.

Modes:
  nuitka       Build using Nuitka (default)
  pyinstaller  Build using PyInstaller
  -h, --help   Show this help message

Platform detected: $OS_TYPE
Output directory: $DIST_DIR

Examples:

1) Build using default Nuitka (Linux or Windows):
   ./build_linux_exe.sh

2) Explicitly build using Nuitka:
   ./build_linux_exe.sh nuitka

3) Build using PyInstaller:
   ./build_linux_exe.sh pyinstaller

4) Show help:
   ./build_linux_exe.sh -h
   ./build_linux_exe.sh --help

Notes:
- All builds are isolated in a virtual environment (.venv) to avoid system package conflicts.
- Nuitka builds a highly optimized binary.
- PyInstaller builds a simple one-file executable.
- Output directories:
    Linux   -> $DIST_DIR
    Windows -> $DIST_DIR
EOF
}

# ---------- VIRTUAL ENVIRONMENT ----------
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Upgrading pip, wheel, and setuptools..."
python -m pip install --upgrade pip wheel setuptools

# Show help if requested
if [ "$MODE" = "-h" ] || [ "$MODE" = "--help" ]; then
  show_help
  exit 0
fi

# ---------- BUILD PROCESS ----------
case "$MODE" in
  nuitka)
    echo "Installing Nuitka..."
    python -m pip install nuitka
    echo "Creating standalone executable with Nuitka..."
    python -m nuitka \
      --standalone \
      --onefile \
      --output-filename=emeter_sim \
      --output-dir="$DIST_DIR" \
      run_simulator.py
    ;;

  pyinstaller)
    echo "Installing PyInstaller..."
    python -m pip install pyinstaller
    echo "Creating standalone executable with PyInstaller..."
    python -m PyInstaller \
      --onefile \
      --name emeter_sim \
      --distpath "$DIST_DIR" \
      run_simulator.py
    ;;

  *)
    echo "Unknown mode: $MODE"
    show_help
    exit 1
    ;;
esac

echo "Compilation completed. Output folder: $DIST_DIR"
