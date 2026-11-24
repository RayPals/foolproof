import ctypes
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import app


def runner_for(tmp_path, code, timeout=5):
    task = app.MaintenanceTask('Fixture', [sys.executable, '-c', code],
                               requires_admin=False, timeout_seconds=timeout)
    return app.MaintenanceRunner([task], dry_run=False,
                                 log_path=tmp_path / 'run.log', require_admin=False)


def test_non_windows_live_run_never_launches_commands(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'is_windows', lambda: False)
    runner = runner_for(tmp_path, "print('SHOULD NOT RUN')")
    messages = list(runner.run_tasks())
    assert not any('SHOULD NOT RUN' in m for m in messages)
    assert any('Windows' in m for m in messages)


def test_timeout_reaps_child(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    processes = []
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(app.subprocess, 'Popen', launch)
    runner = runner_for(tmp_path, 'import time; time.sleep(30)', timeout=0.05)
    messages = list(runner.run_tasks())
    assert any('Timed out' in m for m in messages)
    assert processes[0].returncode is not None, 'Timed-out child must be waited for'


def test_cancellation_during_launch_stops_child(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    runner = runner_for(tmp_path, 'import time; time.sleep(30)', timeout=0.5)
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        # Cancel in the gap before current_process is assigned.
        process = real_popen(*args, **kwargs)
        runner.cancel()
        return process

    monkeypatch.setattr(app.subprocess, 'Popen', launch)
    messages = list(runner.run_tasks())
    assert any('Cancelled: Fixture' in m for m in messages)
    assert not any('Timed out' in m for m in messages)


def test_invalid_output_bytes_do_not_fail_task(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    runner = runner_for(tmp_path, "import os; os.write(1, b'hello\\xff\\n')")
    messages = list(runner.run_tasks())
    assert any('Completed: Fixture' in m for m in messages)
    assert not any('Error:' in m for m in messages)


def test_run_closes_log_file(tmp_path):
    runner = app.MaintenanceRunner([], dry_run=True, log_path=tmp_path / 'run.log')
    handlers = list(runner.logger.handlers)
    list(runner.run_tasks())
    assert all(handler.stream is None for handler in handlers)
    assert runner.logger.handlers == []


@pytest.mark.parametrize('packaged', [False, True])
def test_elevation_quotes_correct_argument_list(monkeypatch, packaged):
    calls = []
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    monkeypatch.setattr(app.sys, 'frozen', packaged, raising=False)
    monkeypatch.setattr(app.sys, 'argv', [r'C:\App Folder\Foolproof.exe', 'trailing slash\\', 'a"b'])
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(
        ShellExecuteW=lambda *args: calls.append(args) or 42)), raising=False)
    result = app.relaunch_as_admin()
    expected = sys.argv[1:] if packaged else [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
    assert calls[0][3] == subprocess.list2cmdline(expected)
    assert result is True


def test_elevation_reports_uac_failure(monkeypatch):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(
        ShellExecuteW=lambda *args: 5)), raising=False)
    assert app.relaunch_as_admin() is False


def test_cancel_running_child_is_responsive_and_skips_next_task(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    ready = tmp_path / 'ready'
    runner = runner_for(tmp_path, f'import pathlib,time; pathlib.Path({str(ready)!r}).touch(); time.sleep(30)')
    runner.tasks.append(app.MaintenanceTask('Must not start', [sys.executable, '-c', 'pass'], requires_admin=False))
    messages = []
    thread = threading.Thread(target=lambda: messages.extend(runner.run_tasks()))
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        process = runner.current_process
        runner.cancel()
        thread.join(3)
        assert not thread.is_alive()
        assert process.returncode is not None
        assert any('Cancelled: Fixture' in m for m in messages)
        assert not any('Starting: Must not start' in m for m in messages)
    finally:
        runner.cancel()
        thread.join(5)


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX signal fixture')
def test_timeout_kills_child_that_ignores_termination(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    processes = []
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(app.subprocess, 'Popen', launch)
    runner = runner_for(tmp_path, 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)', timeout=0.5)
    messages = list(runner.run_tasks())
    try:
        assert any('Timed out' in m for m in messages)
        assert processes[0].returncode is not None
        assert processes[0].stdout.closed and processes[0].stderr.closed
    finally:
        if processes[0].poll() is None:
            processes[0].kill()
            processes[0].wait()


def test_nonzero_exit_and_stderr_are_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    runner = runner_for(tmp_path, "import sys; print('problem', file=sys.stderr); sys.exit(7)")
    messages = list(runner.run_tasks())
    assert any('stderr: problem' in m for m in messages)
    assert any('exited with code 7' in m for m in messages)
