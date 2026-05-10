param(
    [string]$Mode = "nuitka"
)

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

Write-Host "Checking Python version..."
python --version

Write-Host "Installing required packages..."
python -m pip install --upgrade pip wheel setuptools

switch ($Mode.ToLower()) {
    "nuitka" {
        python -m pip install nuitka
        Write-Host "Creating standalone executable with Nuitka..."
        python -m nuitka `
            --standalone `
            --onefile `
            --output-filename=emeter_sim `
            --output-dir=dist `
            run_simulator.py
        break
    }
    "pyinstaller" {
        python -m pip install pyinstaller
        Write-Host "Creating standalone executable with PyInstaller..."
        python -m PyInstaller --onefile --name emeter_sim run_simulator.py
        break
    }
    default {
        Write-Host "Unknown mode: $Mode"
        Write-Host "Usage: .\build_windows_exe.ps1 [-Mode nuitka|pyinstaller]"
        Write-Host "Example: .\build_windows_exe.ps1 -Mode nuitka"
        exit 1
    }
}

Write-Host "Compilation completed. Output folder: $(Join-Path $projectDir dist)"
