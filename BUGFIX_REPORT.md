# Foolproof bug-fix report

Base: RayPals/foolproof main at `62adb6420e5d9cf05c2c3a1de08575fa75eb27e5`.
This report describes the bug-fix changes relative to that baseline.

## Confirmed defects fixed

- **Closing during maintenance could destroy an active QThread.** The close event now requests cancellation and defers closure until the built-in thread-finished signal. Administrator relaunch is disabled during work to prevent concurrent elevated runs from that window.
- **Startup errors escaped the UI handler and left controls disabled.** Runner construction is guarded before changing the controls. Background exceptions are displayed, and controls recover through QThread.finished instead of a custom early-completion signal.
- **Cancellation could be lost while Popen was starting.** Cancellation is now a worker-observed flag, checked while waiting for output and immediately after launch. Process teardown no longer occurs on the GUI thread. Cancelled tasks are explicitly labeled and subsequent tasks are not started.
- **Timeouts terminated without waiting or closing pipes.** Cleanup now waits for the child, escalates to kill if termination does not finish, and closes both pipes. Generator cleanup also tears down the current process.
- **Non-Windows live execution contradicted the UI's safety claim.** The runner now refuses non-dry-run execution outside Windows; command previews remain available.
- **Undecodable command output converted successful tasks into errors.** Text decoding now replaces invalid bytes instead of aborting capture.
- **Each maintenance run leaked its file logging handler.** The run generator closes and removes handlers in a finally block.
- **Administrator relaunch had incorrect argument handling and ignored failure.** Frozen executables now exclude argv[0] from their parameters, source script paths are absolute, Windows quoting uses list2cmdline, ShellExecute errors are checked, and a failed/cancelled relaunch is shown in the UI. The original window closes only on a successful relaunch request.
- **Command output was interpreted as HTML by QTextEdit.append.** Logs now use QTextCursor.insertText so literal tags, entities, quotes, whitespace, and command arguments remain unchanged. The initial escaping-based fix was insufficient: commands without HTML tags displayed `&quot;` and `&#x27;` literally. A follow-up exact-text regression reproduced that bug before the plain-text insertion fix; the Linux suite now passes 23 tests.

## Verification

- Original repository suite: **6 passed**.
- Regression negative control: original app.py with the initial regression tests: **11 failed, 6 passed, 5 deselected**. These failures reproduce the defects; the five additional validation cases were excluded from this control.
- Fixed source suite: **22 passed** on Linux, including real harmless Python child processes and offscreen PyQt6 interactions.
- Additional cases cover cancellation during an active process, a process that ignores SIGTERM, stderr/nonzero exit reporting, real close-during-work, and recovery after a worker exception.
- `python -m py_compile app.py tests/*.py` and `git diff --check` pass.
- The pre-existing dry-run test now intercepts Popen as well as run, so it actually guards the application's subprocess entry point.

## Limits

No Windows maintenance command was executed. Real Windows Update, Defender, Disk Cleanup, drive optimization, UAC, and Windows EXE packaging still need testing on a Windows test machine. Windows elevation calls were verified with intercepted ShellExecute calls, not actual UAC prompts. Offscreen Qt checks verify interactions and lifetime handling, not visual appearance.

Cancellation remains best-effort for work delegated by Windows tools to services or child/background processes; only Foolproof's direct subprocess is controlled. Timeout still stops the remainder of the maintenance run, preserving existing behavior. Existing asynchronous UsoClient behavior and maintenance command definitions are unchanged.

## Use

Install the source dependencies and run `python app.py`, following README.md. The archive is updated source, not a Windows executable. Run tests with `python -m pytest -q` after installing requirements-dev.txt.
