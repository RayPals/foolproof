import os
import sys
from pathlib import Path

import app


def test_build_tasks_uses_pyqt6_safe_subprocess_commands(monkeypatch):
    monkeypatch.setenv("SystemDrive", "D:")
    tasks = app.build_maintenance_tasks(include_updates=True, full_scan=False)

    assert [task.name for task in tasks] == [
        "Check Windows updates",
        "Optimize system drive",
        "Run Disk Cleanup",
        "Run antivirus scan",
    ]
    assert all(task.shell is False for task in tasks)
    assert tasks[0].command[:4] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert "Install-Module" not in " ".join(tasks[0].command)
    assert "Set-ExecutionPolicy" not in " ".join(tasks[0].command)
    assert "-AcceptAll" not in " ".join(tasks[0].command)
    assert tasks[1].command == ["defrag", "D:", "/O"]
    assert tasks[-1].command[-1] == "1"


def test_log_path_is_under_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = app.get_log_path()
    assert path == tmp_path / "Foolproof" / "logs" / "foolproof.log"


def test_dry_run_records_without_executing(monkeypatch, tmp_path):
    called = []

    def fake_run(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("subprocess.run should not be called in dry-run mode")

    monkeypatch.setattr(app.subprocess, "run", fake_run)
    log_path = tmp_path / "foolproof.log"
    task = app.MaintenanceTask("Example", ["cmd", "/c", "echo", "hello"])
    runner = app.MaintenanceRunner([task], dry_run=True, log_path=log_path, require_admin=False)
    messages = list(runner.run_tasks())

    assert called == []
    assert any("DRY RUN" in msg for msg in messages)
    assert log_path.exists()


def test_requires_admin_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_windows", lambda: True)
    monkeypatch.setattr(app, "is_admin", lambda: False)
    task = app.MaintenanceTask("Admin task", ["defrag", "C:", "/O"], requires_admin=True)
    runner = app.MaintenanceRunner([task], dry_run=False, log_path=tmp_path / "x.log")
    messages = list(runner.run_tasks())

    assert any("Administrator" in msg for msg in messages)
