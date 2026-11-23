"""A call of the window system on the main thread of Qt, from a worker thread (the jump runs on a thread of its own).

AppKit documents only the properties of `NSRunningApplication` as safe on any thread, and the windows of Win32 belong
to the thread that made them: so the raise of the Herdr window asks the main thread to make its native calls and
waits for the answer with a time limit. On the main thread itself, or with no Qt application (a test), the call is
made at once. Qt is imported only in a call: the watcher imports the package of the platform and has no Qt.
"""
from __future__ import annotations

import threading

# The longest wait of a worker for the main thread, in seconds.
WAIT = 3.0

_callers: list = []  # the one object on the main thread that runs the calls (made at the first call)


def _caller(app):
    if not _callers:
        from PySide6.QtCore import QObject, Qt, Signal, Slot  # noqa: PLC0415

        class Caller(QObject):
            asked = Signal(object)

            def __init__(self):
                super().__init__()
                self.asked.connect(self.run, Qt.ConnectionType.QueuedConnection)

            @Slot(object)
            def run(self, job):
                job()

        made = Caller()
        made.moveToThread(app.thread())  # from the thread that made it: allowed from any thread
        _callers.append(made)
    return _callers[0]


def on_main_thread(function, wait: float = WAIT):
    """The result of `function()`, called on the main thread of Qt. Its exception goes to the caller. TimeoutError
    when the main thread did not run it in `wait` seconds: then it does not run later either."""
    from PySide6.QtCore import QCoreApplication, QThread  # noqa: PLC0415
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() == app.thread():
        return function()
    done, lock, result = threading.Event(), threading.Lock(), {}

    def job() -> None:
        with lock:
            if "late" in result:
                return
            try:
                result["value"] = function()
            except Exception as error:  # noqa: BLE001  (given to the caller)
                result["error"] = error
            finally:
                done.set()

    _caller(app).asked.emit(job)
    if not done.wait(wait):
        with lock:
            if not done.is_set():
                result["late"] = True
                raise TimeoutError("the main thread did not answer")
    if "error" in result:
        raise result["error"]
    return result["value"]
