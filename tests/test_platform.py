"""The platform package: the interface that each system gives, the choice of the module, and the rule that only the
package has system-specific code."""
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

# A text that names a system-specific mechanism. Outside bellwether/platform/ no module has one.
FORBIDDEN = ("sys.platform", "import fcntl", "from fcntl", "import ctypes", "from ctypes", "prctl", "/proc", "busctl",
             "systemd-run", "XDG_", ".desktop")
# path relative to bellwether/ → the forbidden texts that it may have, with the reason. Empty: no exception.
EXCEPTIONS: dict[str, tuple[str, ...]] = {}


def modules_outside_the_package():
    return sorted(path for path in SOURCE.rglob("*.py") if PACKAGE not in path.parents)


def test_no_module_outside_the_package_has_system_specific_code():
    modules = modules_outside_the_package()
    assert len(modules) >= 15 and SOURCE / "__main__.py" in modules  # the scan sees the program
    found = []
    for path in modules:
        name = str(path.relative_to(SOURCE))
        text = path.read_text()
        found += [f"{name}: {word}" for word in FORBIDDEN if word in text and word not in EXCEPTIONS.get(name, ())]
    assert found == []


def test_the_scan_finds_each_forbidden_text():
    """The check of the test above works: each text is found in the Linux module, where it belongs."""
    text = "\n".join(path.read_text() for path in PACKAGE.rglob("*.py"))
    assert [word for word in FORBIDDEN if word not in text and not word.startswith("from ")] == []


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
