"""Throwaway: show a layer-shell overlay with PySide6 from PyPI.

The PyPI wheel carries its own Qt. The QML module org.kde.layershell comes
from the system package layer-shell-qt. This script exposes only that one
module to the bundled Qt, through a temporary directory with one symlink.
The system plugin liblayer-shell.so is not necessary: the QML module makes
the layer-shell integration itself.

Switches (environment variables, for the spike only):
  SPIKE_APP=widgets     use QApplication, not QGuiApplication
  SPIKE_QML=<file>      QML file name in this directory (default Overlay.qml)
  SPIKE_NO_BRIDGE=1     do not expose the system QML module
  SPIKE_RUN_MS=<n>      quit after n milliseconds (default 6000)
  SPIKE_NO_PLATFORM_ENV=1   do not set QT_QPA_PLATFORM
  SPIKE_MODE=<name>     context property spikeMode, read by OverlayMove.qml
"""
import os
import sys
import tempfile
from pathlib import Path

SYSTEM_QML_MODULE = Path("/usr/lib/qt6/qml/org/kde/layershell")


def make_bridge(root: Path) -> Path:
    """Make a QML import directory that holds only org.kde.layershell."""
    (root / "org" / "kde").mkdir(parents=True)
    (root / "org" / "kde" / "layershell").symlink_to(SYSTEM_QML_MODULE)
    return root


if not os.environ.get("SPIKE_NO_PLATFORM_ENV"):
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
print("QT_QPA_PLATFORM=%r" % os.environ.get("QT_QPA_PLATFORM"), file=sys.stderr)

from PySide6.QtCore import QTimer, qVersion  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

bridge = tempfile.TemporaryDirectory(prefix="herdr-float-qml-")
use_bridge = not os.environ.get("SPIKE_NO_BRIDGE")

if os.environ.get("SPIKE_APP") == "widgets":
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    app = QApplication(sys.argv)
    print("app=QApplication tray_available=%s" % QSystemTrayIcon.isSystemTrayAvailable(), file=sys.stderr)
else:
    app = QGuiApplication(sys.argv)
    print("app=QGuiApplication", file=sys.stderr)
print("qt=%s platform=%s" % (qVersion(), app.platformName()), file=sys.stderr)

engine = QQmlApplicationEngine()
if use_bridge:
    engine.addImportPath(str(make_bridge(Path(bridge.name))))
engine.rootContext().setContextProperty("spikeMode", os.environ.get("SPIKE_MODE", "none"))
engine.load(Path(__file__).with_name(os.environ.get("SPIKE_QML", "Overlay.qml")))
if not engine.rootObjects():
    print("qml=load-failed", file=sys.stderr)
    sys.exit(1)
print("qml=loaded", file=sys.stderr)
QTimer.singleShot(int(os.environ.get("SPIKE_RUN_MS", "6000")), app.quit)
code = app.exec()
del engine
bridge.cleanup()
sys.exit(code)
