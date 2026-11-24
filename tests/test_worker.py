import io
import json

import app
import worker


def run_worker(tmp_path, capsys, args=()):
    code = worker.main(['--log-path', str(tmp_path / 'worker.log'), *args])
    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines()]
    return code, events


def test_worker_defaults_to_preview_without_launching(monkeypatch, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError('Preview must never launch a subprocess')
    monkeypatch.setattr(app.subprocess, 'Popen', forbidden)
    code, events = run_worker(tmp_path, capsys)
    assert code == 0
    assert events[0]['type'] == 'plan'
    assert events[0]['preview'] is True
    assert len(events[0]['tasks']) == 4
    assert any(e['type'] == 'task' and e['status'] == 'Previewed' for e in events)
    assert any('DRY RUN' in e.get('message', '') for e in events)
    assert events[-1]['type'] == 'complete' and events[-1]['failed'] == 0


def test_worker_options_preserve_task_selection(tmp_path, capsys):
    code, events = run_worker(tmp_path, capsys, ['--no-updates', '--full-scan'])
    assert code == 0
    assert len(events[0]['tasks']) == 3
    assert 'Check Windows updates' not in events[0]['tasks']
    assert any('ScanType 2' in e.get('message', '') for e in events)


def test_worker_live_mode_preserves_admin_gate(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    monkeypatch.setattr(app, 'is_admin', lambda: False)
    monkeypatch.setattr(app, 'build_maintenance_tasks', lambda **kw: [
        app.MaintenanceTask('Privileged fixture', ['never-launch'])])
    code, events = run_worker(tmp_path, capsys, ['--execute'])
    assert code == 0
    assert any(e['type'] == 'task' and e['status'] == 'Skipped' for e in events)
    assert events[-1]['skipped'] == 1


def test_worker_live_mode_refuses_non_windows(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(app, 'is_windows', lambda: False)
    code, events = run_worker(tmp_path, capsys, ['--execute'])
    assert code != 0
    assert events[-1]['type'] == 'complete' and events[-1]['failed'] > 0


def test_worker_reports_log_initialization_error(monkeypatch, tmp_path, capsys):
    def broken(*args, **kwargs):
        raise OSError('Read-only log directory')
    monkeypatch.setattr(app, 'MaintenanceRunner', broken)
    code, events = run_worker(tmp_path, capsys)
    assert code != 0
    assert any('Read-only' in e.get('message', '') for e in events)
    assert events[-1]['type'] == 'complete' and events[-1]['failed'] == 1


def test_worker_cancel_input_cancels_live_run(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    monkeypatch.setattr(worker.sys, 'stdin', io.StringIO('cancel\n'))
    monkeypatch.setattr(app, 'build_maintenance_tasks', lambda **kw: [
        app.MaintenanceTask('Privileged fixture', ['never-launch'])])
    code, events = run_worker(tmp_path, capsys, ['--execute'])
    assert events[-1]['type'] == 'complete'
    assert events[-1]['cancelled'] is True
