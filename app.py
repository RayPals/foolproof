"""Foolproof: a simple, safer one-click Windows maintenance app.

The maintenance logic is deliberately kept separate from the PyQt6 UI so it can
be tested without launching a GUI or running system-changing commands.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import time
from shlex import quote
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator, Iterable, Optional

APP_NAME = "Foolproof"
DEFAULT_TIMEOUT_SECONDS = 60 * 60


@dataclass(frozen=True)
class MaintenanceTask:
    name: str
    command: list[str]
    requires_admin: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(relative_path: str) -> Path:
    """Resolve bundled assets both from source and from a PyInstaller EXE."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / relative_path


def format_command(command: list[str]) -> str:
    """Return a copy/paste-friendly command preview with quoted arguments."""
    if is_windows():
        return subprocess.list2cmdline(command)
    return " ".join(quote(part) for part in command)


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_admin() -> bool:
    """Return True when running elevated on Windows.

    Non-Windows development/test hosts return False instead of raising.
    """
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


def get_system_drive() -> str:
    drive = os.environ.get("SystemDrive") or os.environ.get("SYSTEMDRIVE") or "C:"
    return drive.rstrip("\\/")


def get_log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Local" if is_windows() else Path.home() / ".local" / "state"
    return root / APP_NAME / "logs" / "foolproof.log"


def get_defender_path() -> str:
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    return str(Path(program_files) / "Windows Defender" / "MpCmdRun.exe")


def build_maintenance_tasks(*, include_updates: bool = True, full_scan: bool = False) -> list[MaintenanceTask]:
    """Build safe command definitions without executing them."""
    drive = get_system_drive()
    scan_type = "2" if full_scan else "1"
    tasks: list[MaintenanceTask] = []

    if include_updates:
        # Scan/check only. Do not install modules, change execution policy, or accept updates.
        tasks.append(
            MaintenanceTask(
                "Check Windows updates",
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    (
                        "$ErrorActionPreference='Continue'; "
                        "if (Get-Command Get-WindowsUpdate -ErrorAction SilentlyContinue) { "
                        "Get-WindowsUpdate "
                        "} else { "
                        "Write-Output 'PSWindowsUpdate is not installed; requesting a built-in Windows Update scan.'; "
                        "Start-Process UsoClient.exe -ArgumentList 'StartScan' -WindowStyle Hidden "
                        "}"
                    ),
                ],
                requires_admin=False,
                timeout_seconds=20 * 60,
            )
        )

    tasks.extend(
        [
            MaintenanceTask(
                "Optimize system drive",
                ["defrag", drive, "/O"],
                requires_admin=True,
                timeout_seconds=60 * 60,
            ),
            MaintenanceTask(
                "Run Disk Cleanup",
                ["cleanmgr", "/verylowdisk"],
                requires_admin=True,
                timeout_seconds=45 * 60,
            ),
            MaintenanceTask(
                "Run antivirus scan",
                [get_defender_path(), "-Scan", "-ScanType", scan_type],
                requires_admin=True,
                timeout_seconds=3 * 60 * 60,
            ),
        ]
    )
    return tasks


class MaintenanceRunner:
    def __init__(
        self,
        tasks: Iterable[MaintenanceTask],
        *,
        dry_run: bool,
        log_path: Path,
        require_admin: Optional[bool] = None,
    ) -> None:
        self.tasks = list(tasks)
        self.dry_run = dry_run
        self.log_path = Path(log_path)
        self.require_admin = is_admin() if require_admin is None else require_admin
        self.cancelled = False
        self.current_process: Optional[subprocess.Popen[str]] = None
        self.logger = self._build_logger()

    def _build_logger(self) -> logging.Logger:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"{APP_NAME}.{id(self)}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
        return logger

    def cancel(self) -> None:
        # Only the worker owns process teardown. The GUI must never block here,
        # and a cancellation arriving during Popen must not be lost.
        self.cancelled = True

    def _stop_process(self) -> None:
        process = self.current_process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            self.current_process = None

    def log(self, message: str) -> str:
        self.logger.info(message)
        return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"

    def run_tasks(self) -> Generator[str, None, None]:
        try:
            yield from self._run_tasks()
        finally:
            self._stop_process()
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)

    def _run_tasks(self) -> Generator[str, None, None]:
        yield self.log(f"Maintenance started. Log file: {self.log_path}")
        if not self.dry_run and not is_windows():
            yield self.log("Unavailable: maintenance commands only run on Windows.")
            return
        if self.dry_run:
            yield self.log("DRY RUN is enabled; commands will be shown but not executed.")

        for task in self.tasks:
            if self.cancelled:
                yield self.log("Maintenance cancelled before next task.")
                break

            yield self.log(f"Starting: {task.name}")
            if task.requires_admin and not self.require_admin and not self.dry_run:
                yield self.log(f"Skipped: {task.name} requires Administrator privileges.")
                continue

            command_text = format_command(task.command)
            if self.dry_run:
                yield self.log(f"DRY RUN: {command_text}")
                continue

            try:
                self.current_process = subprocess.Popen(
                    task.command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    shell=False,
                )
                deadline = time.monotonic() + task.timeout_seconds
                stdout = stderr = ""
                while not self.cancelled:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(task.command, task.timeout_seconds)
                    try:
                        stdout, stderr = self.current_process.communicate(timeout=min(0.1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if self.cancelled:
                    self._stop_process()
                    yield self.log(f"Cancelled: {task.name}")
                    break
                if stdout.strip():
                    yield self.log(stdout.strip())
                if stderr.strip():
                    yield self.log(f"stderr: {stderr.strip()}")
                if self.current_process.returncode == 0:
                    yield self.log(f"Completed: {task.name}")
                else:
                    yield self.log(f"Failed: {task.name} exited with code {self.current_process.returncode}")
            except subprocess.TimeoutExpired:
                self.cancel()
                self._stop_process()
                yield self.log(f"Timed out: {task.name}")
            except FileNotFoundError as exc:
                yield self.log(f"Unavailable: {task.name} ({exc})")
            except Exception as exc:
                yield self.log(f"Error: {task.name} ({exc})")
            finally:
                self._stop_process()

        yield self.log("Maintenance finished.")


def relaunch_as_admin() -> bool:
    if not is_windows():
        return False
    # Frozen executables already include the entry point; source launches need
    # the script path as the first argument to the Python interpreter.
    args = sys.argv[1:] if is_packaged() else [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
    params = subprocess.list2cmdline(args)
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)  # type: ignore[attr-defined]
        return result > 32
    except (OSError, AttributeError):
        return False


def run_gui() -> int:
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtGui import QIcon, QTextCursor
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    class MaintenanceThread(QThread):
        log_signal = pyqtSignal(str)

        def __init__(self, *, dry_run: bool, include_updates: bool, full_scan: bool) -> None:
            super().__init__()
            self.runner = MaintenanceRunner(
                build_maintenance_tasks(include_updates=include_updates, full_scan=full_scan),
                dry_run=dry_run,
                log_path=get_log_path(),
            )

        def run(self) -> None:
            try:
                for message in self.runner.run_tasks():
                    self.log_signal.emit(message)
            except Exception as exc:
                self.log_signal.emit(f"Maintenance error: {exc}")

        def cancel(self) -> None:
            self.runner.cancel()

    class MaintenanceApp(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.worker: Optional[MaintenanceThread] = None
            self.close_when_finished = False
            self.setWindowTitle(APP_NAME)
            self.setGeometry(100, 100, 680, 500)
            icon_path = resource_path("assets/foolproof-logo.png")
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

            self.status_label = QLabel(self._status_text())
            self.log_textbox = QTextEdit()
            self.log_textbox.setReadOnly(True)
            self.log_textbox.setAcceptRichText(False)

            self.dry_run_box = QCheckBox("Dry run (show commands only)")
            self.dry_run_box.setChecked(True)
            self.updates_box = QCheckBox("Check Windows updates")
            self.updates_box.setChecked(True)
            self.full_scan_box = QCheckBox("Full antivirus scan")
            self.full_scan_box.setChecked(False)

            self.start_button = QPushButton("Start Maintenance")
            self.start_button.clicked.connect(self.start_maintenance)
            self.cancel_button = QPushButton("Cancel")
            self.cancel_button.setEnabled(False)
            self.cancel_button.clicked.connect(self.cancel_maintenance)
            self.admin_button = QPushButton("Relaunch as Administrator")
            self.admin_button.clicked.connect(self.relaunch)
            self.admin_button.setEnabled(is_windows() and not is_admin())

            options = QVBoxLayout()
            options.addWidget(self.dry_run_box)
            options.addWidget(self.updates_box)
            options.addWidget(self.full_scan_box)

            buttons = QHBoxLayout()
            buttons.addWidget(self.start_button)
            buttons.addWidget(self.cancel_button)
            buttons.addWidget(self.admin_button)

            layout = QVBoxLayout()
            layout.addWidget(self.status_label)
            layout.addLayout(options)
            layout.addWidget(self.log_textbox)
            layout.addLayout(buttons)
            self.setLayout(layout)

        def _status_text(self) -> str:
            if not is_windows():
                return "Development mode: Windows maintenance commands only run on Windows."
            if is_admin():
                return "Administrator mode detected."
            return "Not running as Administrator. Privileged tasks will be skipped unless you relaunch elevated."

        def start_maintenance(self) -> None:
            if self.worker and self.worker.isRunning():
                return
            try:
                worker = MaintenanceThread(
                    dry_run=self.dry_run_box.isChecked(),
                    include_updates=self.updates_box.isChecked(),
                    full_scan=self.full_scan_box.isChecked(),
                )
            except Exception as exc:
                self.append_log(f"Unable to start maintenance: {exc}")
                return
            self.start_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.admin_button.setEnabled(False)
            self.worker = worker
            self.worker.log_signal.connect(self.append_log)
            self.worker.finished.connect(self.on_finished)
            self.worker.start()

        def append_log(self, message: str) -> None:
            # Insert plain text directly: append() guesses whether a string is
            # HTML, so escaped quotes in otherwise plain commands stay encoded.
            cursor = self.log_textbox.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if not self.log_textbox.document().isEmpty():
                cursor.insertBlock()
            cursor.insertText(message)
            self.log_textbox.setTextCursor(cursor)
            self.log_textbox.ensureCursorVisible()

        def relaunch(self) -> None:
            if relaunch_as_admin():
                self.close()
            else:
                self.append_log("Administrator relaunch failed or was cancelled.")

        def cancel_maintenance(self) -> None:
            if self.worker:
                self.worker.cancel()
                self.log_textbox.append("Cancellation requested...")

        def on_finished(self) -> None:
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.admin_button.setEnabled(is_windows() and not is_admin())
            if self.worker:
                self.worker.deleteLater()
                self.worker = None
            if self.close_when_finished:
                self.close()

        def closeEvent(self, event) -> None:
            if self.worker and self.worker.isRunning():
                self.close_when_finished = True
                self.cancel_maintenance()
                event.ignore()
                return
            event.accept()

    qt_app = QApplication(sys.argv)
    window = MaintenanceApp()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
