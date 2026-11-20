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
    "app_icon_file": ("function", ("desktop_dirs", "icon_dirs")),
    "SHELL_NEEDS": ("text", None),
    "prepare_environment": ("function", ()),
    "prepare_app": ("function", ("app",)),
    "prepare_engine": ("function", ("engine",)),
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
SYSTEM_ATTRIBUTES = {"sys": ("platform",), "os": ("name",), "platform": ("system", "uname")}
# A text that names a system-specific mechanism: a call of the kernel, a file system, a program, the XDG rules.
FORBIDDEN_TEXTS = ("prctl", "/proc", "busctl", "systemd-run", "XDG_", ".desktop")
# path relative to bellwether/ → the findings that it may have, with the reason. Empty: no exception.
EXCEPTIONS: dict[str, tuple[str, ...]] = {}


def modules_outside_the_package():
    return sorted(path for path in SOURCE.rglob("*.py") if PACKAGE not in path.parents)


def named_module(node, aliases):
    """The module that the expression `node` names: a name that an import gave, `__import__("m")` or
    `importlib.import_module("m")`. None for anything else."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
        call = node.func
        if (isinstance(call, ast.Name) and call.id == "__import__") or (
                isinstance(call, ast.Attribute) and call.attr == "import_module"):
            return node.args[0].value if isinstance(node.args[0].value, str) else None
    return None


def system_specific(text):
    """The system-specific parts of the source `text`: "import <module>" for a system module (by an import statement
    or by a call), "<module>.<attribute>" for an attribute that tells the system (as an attribute, through an alias,
    `from <module> import <attribute>` or `getattr`), and each forbidden text."""
    tree = ast.parse(text)
    found = []
    aliases = {}  # a name of the module → the module that an absolute import bound to it
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
                found.append(f"import {alias.name.split('.')[0]}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".")[0]
            found.append(f"import {root}")
            found += [f"{root}.{a.name}" for a in node.names if a.name in SYSTEM_ATTRIBUTES.get(root, ())]
    found = [item for item in found if not item.startswith("import ") or item[7:] in SYSTEM_MODULES]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            module = named_module(node.value, aliases)
            if node.attr in SYSTEM_ATTRIBUTES.get(module, ()):
                found.append(f"{module}.{node.attr}")
        elif isinstance(node, ast.Call):
            module = named_module(node, aliases)
            if module and module.split(".")[0] in SYSTEM_MODULES:
                found.append(f"import {module.split('.')[0]}")
            if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
                module, name = named_module(node.args[0], aliases), node.args[1]
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
    assert linux.os.environ["QT_QPA_PLATFORM"] == "wayland"
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


def test_the_engine_gets_the_import_path_and_loads_only_with_the_layer_shell_module():
    paths = []
    engine = SimpleNamespace(addImportPath=paths.append)
    ready = linux.prepare_engine(engine)
    assert paths == [str(linux.IMPORT_PATH)]
    assert ready == (linux.IMPORT_PATH / "org" / "kde" / "layershell" / "qmldir").is_file()
    assert re.fullmatch(r"the QML module \S+ \(package \S+\)", linux.SHELL_NEEDS)
