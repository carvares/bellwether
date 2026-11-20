"""The platform package: the interface that each system gives, the choice of the module, and the rule that only the
package has system-specific code."""
import ast
import inspect
import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bellwether import platform
from bellwether.platform import linux

PACKAGE = Path(platform.__file__).parent
SOURCE = PACKAGE.parent

# The interface: member → (kind, the names of its parameters). Each module of a system gives all of them; the macOS
# and the Windows modules are written against this table.
INTERFACE = {
    "config_home": ("function", ()),
    "state_home": ("function", ()),
    "cache_home": ("function", ()),
    "runtime_dir": ("function", ()),
    "lock": ("function", ("path",)),
    "COMMANDS": ("commands", None),
    "raise_app": ("function", ("run", "commands")),
    "start_app": ("function", ("run", "app", "commands")),
    "clean_environment": ("function", ("argv", "names", "commands")),
    "find_executables": ("function", ()),
    "spawn_child": ("function", ("argv",)),
    "process_host": ("function", ()),
    "app_icon_file": ("function", ()),
    "SHELL_NEEDS": ("text", None),
    "prepare_environment": ("function", ()),
    "prepare_app": ("function", ("app",)),
    "prepare_engine": ("function", ("engine",)),
    "SHELL_FILES": ("shells", None),
    "shell": ("function", ("engine", "environ", "platform_name", "compositor_globals")),
}
# The names of the package that are not members of a system.
OWN = {"load", "MODULES", "annotations", "importlib", "sys", "ModuleType", "linux"}


def test_on_linux_the_package_gives_the_members_of_the_linux_module():
    assert sys.platform == "linux"  # the suite runs on Linux; P3 and P4 add the other systems
    assert platform.load(sys.platform) is linux
    for name in INTERFACE:
        assert getattr(platform, name) is getattr(linux, name), name


def test_the_package_gives_exactly_the_members_of_the_table():
    given = {name for name in vars(platform) if not name.startswith("_")} - OWN
    assert given == set(INTERFACE)


@pytest.mark.parametrize("name", INTERFACE)
def test_each_member_of_the_linux_module_has_its_kind_and_its_parameters(name):
    kind, parameters = INTERFACE[name]
    member = getattr(linux, name)
    if kind == "function":
        assert callable(member)
        assert tuple(inspect.signature(member).parameters) == parameters
    elif kind == "commands":
        assert member and all(isinstance(k, str) and isinstance(v, str) and v for k, v in member.items())
    elif kind == "shells":
        assert set(member) <= {"layer", "plain"} and "plain" in member and all(f.is_file() for f in member.values())
    else:
        assert isinstance(member, str) and member


@pytest.mark.parametrize("name", ["darwin", "win32", "cygwin", "freebsd14", ""])
def test_a_system_with_no_module_is_a_clear_import_error(name):
    with pytest.raises(ImportError) as failure:
        platform.load(name)
    assert str(failure.value) == f"bellwether does not run on this system ({name!r}): it runs on linux"


# ----- only the package has system-specific code -----

# The modules whose import is system-specific. `platform` is the module of the standard library (an absolute import);
# the package of the program is `from . import platform`, a relative import, which the rule does not see.
SYSTEM_MODULES = ("fcntl", "ctypes", "msvcrt", "winreg", "platform")
# A module → its attributes that tell the system.
SYSTEM_ATTRIBUTES = {"sys": ("platform",), "os": ("name", "uname"), "platform": ("system", "uname"),
                     "sysconfig": ("get_platform",)}
# A name that tells the system wherever it comes from (Qt's facts of the system).
SYSTEM_NAMES = ("QSysInfo",)
# A text that names a system-specific mechanism: a call of the kernel, a file system, a program, the XDG rules.
FORBIDDEN_TEXTS = ("prctl", "/proc", "busctl", "systemd-run", "XDG_", ".desktop")
# path relative to bellwether/ → the findings that it may have, with the reason. Empty: no exception.
EXCEPTIONS: dict[str, tuple[str, ...]] = {}


def modules_outside_the_package():
    return sorted(path for path in SOURCE.rglob("*.py") if PACKAGE not in path.parents)


def named_module(node, aliases, importers=("__import__",)):
    """The module that the expression `node` names: a name that an import or an assignment gave, or a call of an
    import function with a constant name (`__import__("m")`, `importlib.import_module("m")`, or a name bound to
    `import_module`). None for anything else."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
        call = node.func
        if (isinstance(call, ast.Name) and call.id in importers) or (
                isinstance(call, ast.Attribute) and call.attr == "import_module"):
            return node.args[0].value if isinstance(node.args[0].value, str) else None
    return None


def system_specific(text):
    """The system-specific parts of the source `text`: "import <module>" for a system module (by an import statement
    or by a call of an import function), "<module>.<attribute>" for an attribute that tells the system (as an
    attribute, through an alias of an import or of an assignment, `from <module> import <attribute>` or `getattr`
    with a constant name), "from <module> import *" for such a module, each name of SYSTEM_NAMES, and each
    forbidden text.

    Not found (a rule of the review, not of a proof): `vars(sys)["platform"]` and `sys.__dict__`, `getattr` with a
    name that is not a constant, `eval`/`exec` of a text, a module object that comes from an other module or from a
    function, and an alias made in a branch or a loop of an other scope than the use. A relative import (`from .
    import platform`, the package of the program) is not seen, by design."""
    tree = ast.parse(text)
    found = []
    aliases = {}  # a name → the module that an absolute import or an assignment bound to it
    importers = {"__import__"}  # the names of import functions
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
                found.append(f"import {alias.name.split('.')[0]}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".")[0]
            found.append(f"import {root}")
            for alias in node.names:
                if alias.name in SYSTEM_ATTRIBUTES.get(root, ()):
                    found.append(f"{root}.{alias.name}")
                elif alias.name == "*" and root in SYSTEM_ATTRIBUTES:
                    found.append(f"from {root} import *")
                elif root == "importlib" and alias.name == "import_module":
                    importers.add(alias.asname or alias.name)
    found = [item for item in found if not item.startswith("import ") or item[7:] in SYSTEM_MODULES]
    changed = True
    while changed:  # an alias by assignment, also of an other alias (s = sys; t = s)
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                module = named_module(node.value, aliases, importers)
                if module and aliases.get(node.targets[0].id) != module:
                    aliases[node.targets[0].id] = module
                    changed = True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            module = named_module(node.value, aliases, importers)
            if node.attr in SYSTEM_ATTRIBUTES.get(module, ()):
                found.append(f"{module}.{node.attr}")
            if node.attr in SYSTEM_NAMES:
                found.append(node.attr)
        elif isinstance(node, ast.Name) and node.id in SYSTEM_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.alias) and (node.asname or node.name).split(".")[-1] in SYSTEM_NAMES:
            found.append((node.asname or node.name).split(".")[-1])
        elif isinstance(node, ast.Call):
            module = named_module(node, aliases, importers)
            if module and module.split(".")[0] in SYSTEM_MODULES:
                found.append(f"import {module.split('.')[0]}")
            if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
                module, name = named_module(node.args[0], aliases, importers), node.args[1]
                if isinstance(name, ast.Constant) and name.value in SYSTEM_ATTRIBUTES.get(module, ()):
                    found.append(f"{module}.{name.value}")
    return sorted(set(found)) + [word for word in FORBIDDEN_TEXTS if word in text]


def test_no_module_outside_the_package_has_system_specific_code():
    modules = modules_outside_the_package()
    assert len(modules) >= 15 and SOURCE / "__main__.py" in modules  # the scan sees the program
    found = []
    for path in modules:
        name = str(path.relative_to(SOURCE))
        found += [f"{name}: {item}" for item in system_specific(path.read_text()) if item not in EXCEPTIONS.get(name, ())]
    assert found == []


@pytest.mark.parametrize("source, found", [
    # The usual ways.
    ("import fcntl", ["import fcntl"]),
    ("from ctypes import CDLL", ["import ctypes"]),
    ("import sys\nif sys.platform == 'linux':\n    pass", ["sys.platform"]),
    # The ways a text scan does not see.
    ("import os, fcntl", ["import fcntl"]),
    ("import os\nif os.name == 'nt':\n    pass", ["os.name"]),
    ("x = __import__('sys').platform", ["sys.platform"]),
    ("import platform\nprint(platform.system())", ["import platform", "platform.system"]),
    ("import platform as p\np.uname()", ["import platform", "platform.uname"]),
    ("import sys as s\ns.platform", ["sys.platform"]),
    ("from sys import platform as where", ["sys.platform"]),
    ("from os import name", ["os.name"]),
    ("import sys\ngetattr(sys, 'platform')", ["sys.platform"]),
    ("import importlib\nimportlib.import_module('msvcrt')", ["import msvcrt"]),
    ("lock = __import__('fcntl.x')", ["import fcntl"]),
    # The ways of the review of P2.
    ("from importlib import import_module\nimport_module('fcntl')", ["import fcntl"]),
    ("from importlib import import_module as load\nload('msvcrt')", ["import msvcrt"]),
    ("import os\nos.uname()", ["os.uname"]),
    ("import sysconfig\nsysconfig.get_platform()", ["sysconfig.get_platform"]),
    ("from PySide6.QtCore import QSysInfo\nQSysInfo.productType()", ["QSysInfo"]),
    ("import PySide6.QtCore as core\ncore.QSysInfo.kernelType()", ["QSysInfo"]),
    ("import sys\ns = sys\ns.platform", ["sys.platform"]),
    ("import sys\ns = sys\nt = s\nt.platform", ["sys.platform"]),
    ("s = __import__('os')\ns.name", ["os.name"]),
    ("from sys import *", ["from sys import *"]),
    ("open('/proc/self/stat')", ["/proc"]),
    # Not system-specific: the package of the program, and the same words on other things.
    ("from . import platform\nplatform.shell(None)\nplatform.system", []),
    ("import os\nos.environ['A']\nos.path.join('a', 'b')", []),
    ("import sys\nsys.argv\nthing.platform\nperson.name", []),
])
def test_the_scan_finds_each_way_to_write_a_system_test(source, found):
    assert system_specific(source) == found


def test_the_scan_finds_each_forbidden_text():
    """The check of the test above works on real code: the Linux module has its system code, where it belongs."""
    found = system_specific((PACKAGE / "linux.py").read_text())
    assert {"import fcntl", "import ctypes"} <= set(found)
    assert [word for word in FORBIDDEN_TEXTS if word not in found] == []


# ----- the set-up of Qt on Linux -----

def test_the_wayland_plugin_is_the_default_and_a_choice_of_the_person_stays(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    linux.prepare_environment()
    # Wayland first; the X11 plugin when no Wayland compositor answers (then the plain shell).
    assert linux.os.environ["QT_QPA_PLATFORM"] == "wayland;xcb"
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    linux.prepare_environment()
    assert linux.os.environ["QT_QPA_PLATFORM"] == "offscreen"


def test_a_plugin_that_is_not_wayland_gives_one_warning(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    linux.prepare_app(SimpleNamespace(platformName=lambda: "wayland"))
    assert caplog.records == []
    linux.prepare_app(SimpleNamespace(platformName=lambda: "xcb"))
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.WARNING, "the Qt platform is xcb, not wayland: the widget cannot be an overlay")]


def test_the_engine_gets_the_import_path_of_the_layer_shell_module():
    paths = []
    engine = SimpleNamespace(addImportPath=paths.append)
    assert linux.prepare_engine(engine) is None
    assert paths == [str(linux.IMPORT_PATH)]
    assert re.fullmatch(r"the QML module \S+ \(package \S+\)", linux.SHELL_NEEDS)


# ----- the window shell on Linux -----

LAYERSHELL_QMLDIR = Path("/usr/lib/qt6/qml/org/kde/layershell/qmldir")
needs_layershell = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(), reason="org.kde.layershell is not installed")
WITH_LAYER = {"wl_compositor", "xdg_wm_base", "zwlr_layer_shell_v1"}
PLAIN = ("a normal window: not above other windows, it can take the focus, the compositor places it, and a drag "
         "does not save its place")


def never():
    raise AssertionError("the globals of the compositor are not needed here")


@pytest.fixture
def engine(app):
    """A QML engine with the import path of the program (the layer shell module loads in it)."""
    from PySide6.QtQml import QQmlEngine
    made = QQmlEngine()
    linux.prepare_engine(made)
    yield made
    del made


@pytest.fixture
def bare_engine(app, monkeypatch):
    """A QML engine in which the layer shell module does not load. (In this process the module can be loaded
    already, and Qt then finds it in every engine: so the check gives False here. The check itself is tested in a
    process of its own.)"""
    from PySide6.QtQml import QQmlEngine
    monkeypatch.setattr(linux, "layer_module_loads", lambda engine: False)
    made = QQmlEngine()
    yield made
    del made


def records(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records]


@needs_layershell
def test_wayland_with_the_module_and_the_protocol_gives_the_layer_shell(engine, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert linux.shell(engine, {}, "wayland", lambda: WITH_LAYER) == "layer"
    assert linux.shell(engine, {}, "wayland-egl", lambda: WITH_LAYER) == "layer"
    assert records(caplog) == []


@pytest.mark.parametrize("name", ["xcb", "offscreen", "cocoa", "windows", ""])
def test_a_platform_that_is_not_wayland_gives_the_plain_shell(engine, caplog, name):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert linux.shell(engine, {}, name, never) == "plain"
    assert records(caplog) == []


def test_wayland_without_the_module_gives_the_plain_shell(bare_engine, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert linux.shell(bare_engine, {}, "wayland", never) == "plain"
    assert records(caplog) == [(logging.WARNING, f"the layer shell needs {linux.SHELL_NEEDS}: the plain shell, {PLAIN}")]


@needs_layershell
def test_wayland_with_the_module_and_a_compositor_without_the_protocol_gives_the_plain_shell(engine, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert linux.layer_module_loads(engine) is True
    assert linux.shell(engine, {}, "wayland", lambda: {"wl_compositor", "xdg_wm_base"}) == "plain"
    assert records(caplog) == [(logging.WARNING, f"the compositor has no zwlr_layer_shell_v1: the plain shell, {PLAIN}")]


@needs_layershell
def test_when_the_globals_cannot_be_read_the_module_and_the_platform_decide(engine, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert linux.shell(engine, {}, "wayland", lambda: None) == "layer"
    assert records(caplog) == [(logging.INFO, "the globals of the compositor could not be read: the layer shell")]


CHECK = """
import sys
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine
from bellwether.platform import linux
app = QGuiApplication([])
engine = QQmlEngine()
if sys.argv[1] == "path":
    linux.prepare_engine(engine)
print(linux.layer_module_loads(engine))
"""


@needs_layershell
@pytest.mark.parametrize("given, loads", [("path", "True"), ("none", "False")])
def test_the_module_loads_only_with_the_import_path_of_the_program(given, loads):
    """In a new process: the Qt of the wheel finds the system module only through the import path of the program."""
    import subprocess
    done = subprocess.run([sys.executable, "-c", CHECK, given], capture_output=True, text=True, timeout=60,
                          cwd=SOURCE.parent, env={**linux.os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert (done.returncode, done.stdout.strip()) == (0, loads), done.stderr[-1000:]


@pytest.mark.parametrize("value", ["layer", "plain"])
def test_the_variable_chooses_the_shell_before_every_other_rule(bare_engine, caplog, value):
    caplog.set_level(logging.INFO, logger="bellwether")
    for platform_name in ("wayland", "xcb"):
        assert linux.shell(bare_engine, {"BELLWETHER_SHELL": value}, platform_name, never) == value
    assert records(caplog) == []


@pytest.mark.parametrize("value", ["Plain", "LAYER", "x11", " plain", "layer-shell" * 10])
def test_another_value_of_the_variable_is_ignored_with_one_log_line(bare_engine, caplog, value):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert linux.shell(bare_engine, {"BELLWETHER_SHELL": value}, "xcb", never) == "plain"
    assert records(caplog) == [(logging.WARNING, f"BELLWETHER_SHELL={value[:40]!r} is not layer or plain: ignored")]


def test_an_empty_variable_is_the_same_as_no_variable(bare_engine, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert linux.shell(bare_engine, {"BELLWETHER_SHELL": ""}, "xcb", never) == "plain"
    assert records(caplog) == []


def test_without_arguments_the_shell_reads_the_environment_and_the_platform_of_the_application(
        engine, caplog, monkeypatch):
    monkeypatch.delenv("BELLWETHER_SHELL", raising=False)
    assert linux.shell(engine) == "plain"  # the tests run off screen
    monkeypatch.setenv("BELLWETHER_SHELL", "layer")
    assert linux.shell(engine) == "layer"


@pytest.mark.skipif(not linux.os.environ.get("WAYLAND_DISPLAY"), reason="no Wayland compositor")
def test_the_globals_of_the_real_compositor_are_read_on_a_connection_of_our_own():
    names = linux.wayland_globals()
    assert names is not None and {"wl_compositor", "wl_seat"} <= names
    assert linux.wayland_globals() == names  # the connection was closed and a new one works


def test_a_library_without_a_function_or_no_library_gives_none_and_no_search_of_the_library(monkeypatch):
    import ctypes.util
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: pytest.fail("find_library starts ldconfig"))
    assert linux.wayland_globals(libraries=("libc.so.6",)) is None  # a library with no wl_display_connect
    assert linux.wayland_globals(libraries=("libbellwether-not-there.so",)) is None
    assert linux.wayland_globals(libraries=()) is None


def test_a_compositor_that_does_not_answer_gives_none_within_the_time_limit(tmp_path):
    """A socket that takes the connection and never answers: the read ends after its time limit."""
    import socket
    import time
    path = tmp_path / "wl"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    try:
        began = time.monotonic()
        assert linux.wayland_globals({"WAYLAND_DISPLAY": str(path)}, timeout=0.3) is None
        assert 0.25 <= time.monotonic() - began < 2
    finally:
        server.close()


def test_the_globals_are_none_without_a_compositor_or_with_a_socket_given_to_us():
    assert linux.wayland_globals({"WAYLAND_DISPLAY": "p2-no-such-compositor"}) is None
    assert linux.wayland_globals({"WAYLAND_DISPLAY": "wayland-0", "WAYLAND_SOCKET": "7"}) is None
