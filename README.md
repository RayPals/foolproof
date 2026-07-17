# Foolproof

<p align="center">
  <img src="assets/foolproof-logo.png" alt="Foolproof logo: feather duster sweeping sparkles across a blue shield" width="220">
</p>

**Foolproof** is a simple one-click maintenance app for Windows.

It is intentionally conservative: it starts in **Dry run** mode, shows what it will do, and skips privileged actions unless it is running as Administrator.

## Features

- PyQt6 desktop UI
- Dry-run mode by default
- Checks Windows Update status without auto-installing updates
- Optimizes the system drive using Windows `defrag /O`
- Runs Windows Disk Cleanup
- Runs a quick or full Microsoft Defender scan
- Detects Administrator mode and can relaunch elevated
- Cancel button for long-running tasks
- Logs to `%LOCALAPPDATA%\Foolproof\logs\foolproof.log`
- Uses the app logo as the window/package icon

## Install from source

Requirements:

- Windows 10/11
- Python 3.10+

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

## Recommended usage

1. Launch Foolproof normally.
2. Leave **Dry run** enabled and click **Start Maintenance** to review the planned commands.
3. If you want to run privileged maintenance tasks, click **Relaunch as Administrator**.
4. Uncheck **Dry run** only when you are ready to run the selected tasks.

Foolproof does **not** silently install PowerShell modules, change execution policy, or automatically accept Windows updates.

## Build a Windows EXE

```powershell
.\build.ps1
```

The built executable will be written to:

```text
dist\Foolproof.exe
```

## Developer checks

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m py_compile app.py
```

## Logo

The project logo is available in three formats:

- `assets/foolproof-logo.png` — 1024×1024 PNG for GitHub, releases, and app metadata
- `assets/foolproof-logo.svg` — editable vector source with the feather-duster design
- `assets/foolproof-logo.ico` — Windows icon for the app and packaged EXE

## License

Public Domain
