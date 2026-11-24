"""JSON-lines bridge for WinUI; reuse the tested maintenance engine.

No GUI toolkit is loaded. Execution requires an explicit --execute flag.
Closing the controlling stdin cancels a live run instead of leaving it running.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

import app


def emit(event: str, **fields) -> None:
    print(json.dumps({'type': event, **fields}, ensure_ascii=False), flush=True)


def watch_control(runner: app.MaintenanceRunner) -> None:
    try:
        for line in sys.stdin:
            if line.strip().lower() == 'cancel':
                runner.cancel()
                return
        runner.cancel()
    except (OSError, ValueError):
        # Embedded/test callers may have no readable stdin. Real child launches
        # always receive a pipe owned by the native UI.
        return


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--no-updates', action='store_true')
    parser.add_argument('--full-scan', action='store_true')
    parser.add_argument('--log-path', type=Path)
    args = parser.parse_args(argv)
    failed = skipped = 0
    runner = None
    try:
        tasks = app.build_maintenance_tasks(include_updates=not args.no_updates, full_scan=args.full_scan)
        emit('plan', tasks=[task.name for task in tasks], preview=not args.execute)
        if args.execute and not app.is_windows():
            raise RuntimeError('Maintenance commands only run on Windows.')
        runner = app.MaintenanceRunner(tasks, dry_run=not args.execute, log_path=args.log_path or app.get_log_path())
        if args.execute:
            threading.Thread(target=watch_control, args=(runner,), daemon=True).start()
        current = None
        for message in runner.run_tasks():
            emit('log', message=message)
            text = message.split('] ', 1)[-1]
            if text.startswith('Starting: '):
                current = text.removeprefix('Starting: ')
                emit('task', name=current, status='Running')
            elif text.startswith('DRY RUN: ') and current:
                emit('task', name=current, status='Previewed')
            elif text.startswith('Completed: '):
                emit('task', name=current, status='Done')
            elif text.startswith('Skipped: '):
                skipped += 1
                emit('task', name=current, status='Skipped')
            elif text.startswith(('Failed: ', 'Error: ', 'Unavailable: ', 'Timed out: ')):
                failed += 1
                emit('task', name=current, status='Failed')
            elif text.startswith('Cancelled: '):
                emit('task', name=current, status='Cancelled')
        emit('complete', failed=failed, skipped=skipped, cancelled=runner.cancelled, preview=not args.execute)
        return 1 if failed else 0
    except Exception as exc:
        emit('log', message=f'Unable to run maintenance: {exc}')
        emit('complete', failed=failed + 1, skipped=skipped, cancelled=bool(runner and runner.cancelled), preview=not args.execute)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
