import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication

import app


@pytest.fixture(scope='module')
def qt_app():
    return QApplication.instance() or QApplication([])


def open_window(monkeypatch, qt_app, action):
    def exercise():
        window = next(w for w in qt_app.topLevelWidgets() if w.windowTitle() == app.APP_NAME)
        try:
            action(window)
        finally:
            window.worker = None
            window.close()
        return 0

    monkeypatch.setattr(QApplication, 'exec', staticmethod(exercise))
    # Reuse the existing Qt application rather than constructing another one.
    monkeypatch.setattr('PyQt6.QtWidgets.QApplication', lambda argv: qt_app)
    assert app.run_gui() == 0


def test_close_during_work_requests_cancellation(monkeypatch, qt_app):
    class Worker:
        cancelled = False
        def isRunning(self):
            return True
        def cancel(self):
            self.cancelled = True

    def action(window):
        worker = Worker()
        window.worker = worker
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted(), 'Do not destroy a running QThread'
        assert worker.cancelled

    open_window(monkeypatch, qt_app, action)


def test_window_waits_for_real_worker_before_closing(monkeypatch, qt_app, tmp_path):
    import sys
    monkeypatch.setattr(app, 'is_windows', lambda: True)
    monkeypatch.setattr(app, 'is_admin', lambda: False)
    monkeypatch.setattr(app, 'get_log_path', lambda: tmp_path / 'gui.log')
    monkeypatch.setattr(app, 'build_maintenance_tasks', lambda **kw: [
        app.MaintenanceTask('Harmless fixture', [sys.executable, '-c', 'import time; time.sleep(30)'], requires_admin=False)])

    def action(window):
        window.dry_run_box.setChecked(False)
        window.start_button.click()
        worker = window.worker
        assert worker.isRunning()
        assert not window.admin_button.isEnabled()
        window.close()
        assert window.isVisible()
        deadline = time.monotonic() + 5
        while window.isVisible() and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.005)
        assert worker.wait(1000)
        assert not window.isVisible()

    open_window(monkeypatch, qt_app, action)


def test_worker_exception_restores_controls(monkeypatch, qt_app):
    class BrokenRunner:
        def __init__(self, *args, **kwargs):
            pass
        def run_tasks(self):
            raise RuntimeError('Unexpected fixture failure')
        def cancel(self):
            pass

    monkeypatch.setattr(app, 'MaintenanceRunner', BrokenRunner)

    def action(window):
        window.start_button.click()
        worker = window.worker
        deadline = time.monotonic() + 5
        while not window.start_button.isEnabled() and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.005)
        assert worker.wait(1000)
        assert window.start_button.isEnabled()
        assert not window.cancel_button.isEnabled()
        assert 'Unexpected fixture failure' in window.log_textbox.toPlainText()

    open_window(monkeypatch, qt_app, action)


def test_failed_runner_creation_leaves_start_enabled(monkeypatch, qt_app):
    def fail(*args, **kwargs):
        raise OSError('Log directory is read-only')
    monkeypatch.setattr(app, 'MaintenanceRunner', fail)

    def action(window):
        window.start_maintenance()
        assert window.start_button.isEnabled()
        assert not window.cancel_button.isEnabled()
        assert 'read-only' in window.log_textbox.toPlainText()

    open_window(monkeypatch, qt_app, action)


def test_log_preserves_quotes_ampersands_entities_and_tags(monkeypatch, qt_app):
    lines = [
        'DRY RUN: powershell -Command "$x=\'Continue\'; Write-Output \'hello\'"',
        'DRY RUN: "C:\\Program Files\\Windows Defender\\MpCmdRun.exe" -Scan',
        'literal &quot; &#x27; & <b>tag</b>',
        'line one\nline two',
        '    spaces\tand a tab',
    ]

    def action(window):
        for line in lines:
            window.append_log(line)
        assert window.log_textbox.toPlainText() == '\n'.join(lines)

    open_window(monkeypatch, qt_app, action)


def test_dry_run_completes_and_displays_output_as_plain_text(monkeypatch, qt_app, tmp_path):
    monkeypatch.setattr(app, 'get_log_path', lambda: tmp_path / 'gui.log')
    monkeypatch.setattr(app, 'build_maintenance_tasks', lambda **kw: [
        app.MaintenanceTask('HTML <b>literal</b>', ['echo', '<b>literal</b>'])])

    def action(window):
        window.start_button.click()
        deadline = time.monotonic() + 5
        while not window.start_button.isEnabled() and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.005)
        assert window.start_button.isEnabled()
        assert not window.cancel_button.isEnabled()
        assert '<b>literal</b>' in window.log_textbox.toPlainText()
        assert 'DRY RUN' in window.log_textbox.toPlainText()
        if window.worker:
            assert window.worker.wait(1000)

    open_window(monkeypatch, qt_app, action)
