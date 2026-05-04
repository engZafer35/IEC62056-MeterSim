#!/usr/bin/env bash
set -euo pipefail

MODE=${1:-nuitka}
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_DIR"

echo "Checking Python version..."
python3 --version

echo "Installing required packages..."
python3 -m pip install --upgrade pip wheel setuptools

case "$MODE" in
  nuitka)
    python3 -m pip install nuitka
    echo "Creating standalone executable with Nuitka..."
    python3 -m nuitka --standalone --onefile --output-dir=dist run_simulator.py
    ;;
  pyinstaller)
    python3 -m pip install pyinstaller
    echo "Creating standalone executable with PyInstaller..."
    python3 -m PyInstaller --onefile --name MeterSimulator run_simulator.py
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Usage: ./build_linux_exe.sh [nuitka|pyinstaller]"
    echo "Example: ./build_linux_exe.sh -Mode nuitka"
    exit 1
    ;;
esac

echo "Compilation completed. Output folder: $PROJECT_DIR/dist"
