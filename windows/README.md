# Foolproof — native WinUI 3 edition

## Run

Windows 10 version 2004 (build 19041) or later, x64; Windows 11 recommended.

1. Download `Foolproof-WinUI3-Windows-x64.zip`.
2. Right-click → **Extract All**. Keep the entire extracted `Foolproof` folder together.
3. Open `Foolproof.exe` in that folder.

This is real WinUI 3, not a Qt theme. It includes the .NET and Windows App SDK runtimes and the maintenance engine; Python does not need to be installed. WinUI requires companion runtime files, so this edition is a portable ZIP rather than a single standalone EXE. The app is unsigned and may trigger Windows SmartScreen.

## Simpler interface

- One primary action with plain-language status for each of the four maintenance steps.
- **Preview only** is on by default. Preview never runs maintenance commands.
- **Options** holds update/full-scan choices and administrator relaunch.
- **Activity log** is collapsed until needed, with literal-text logging.
- Native light/dark theme support, Windows controls, keyboard focus and a scrollable layout for smaller screens.

To perform maintenance, optionally choose **Options → Run as administrator**, turn off **Preview only**, and select **Start maintenance**. A confirmation explains the changes before execution. Non-elevated runs skip privileged tasks. Cancel and close request cancellation; Windows tools may still delegate work to services/background children.

The native frontend uses a small bundled worker over JSON-lines stdin/stdout. `worker.py` calls the existing tested `MaintenanceRunner` rather than replacing its command definitions. The Windows Update fallback remains asynchronous; requesting a scan is not proof that Windows finished scanning.

The original `app.py` PyQt6 frontend and its Windows build workflow remain available as a fallback.

## Build

On a Windows machine with Python 3.10+ and the .NET 10 SDK:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m PyInstaller --noconfirm --clean --onefile --console --name Foolproof.Worker --exclude-module PyQt6 --distpath worker-dist worker.py
dotnet publish windows/Foolproof.WinUI/Foolproof.WinUI.csproj -c Release -r win-x64 -p:Platform=x64 --self-contained true -o native-dist/Foolproof
New-Item -ItemType Directory -Force native-dist/Foolproof/backend
Copy-Item worker-dist/Foolproof.Worker.exe native-dist/Foolproof/backend/
```

Check each command's exit code before proceeding. GitHub Actions `Build WinUI 3 app` performs these checks, launches the published app with `--smoke-test`, exercises native controls and both preview option sets with the real bundled worker, and renders actual XAML previews. Smoke mode refuses live execution. CI does not perform drive optimization, cleanup, antivirus scans, UAC or Windows Update maintenance actions.

## Deployment reference

Microsoft's [self-contained deployment guide](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/self-contained-deploy/deploy-self-contained-apps) documents app-local Windows App SDK binaries and why WinUI requires companion native files rather than a single-file EXE.
