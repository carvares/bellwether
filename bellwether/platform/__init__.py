"""Everything that depends on the operating system, behind one interface.

The rest of the program calls only the members of this package. `load` picks the module of the system one time, at
the import of this package. Only Linux has a module today: on any other system the import fails with a clear
ImportError (the macOS and the Windows modules come with their own tasks, see the design of the port).
"""
from __future__ import annotations

import importlib
import sys
from types import ModuleType

# The value of sys.platform → the module of this package for that system.
MODULES = {"linux": "linux"}


def load(name: str) -> ModuleType:
    """The module of the system `name` (a value of sys.platform)."""
    module = MODULES.get(name)
    if module is None:
        raise ImportError(f"bellwether does not run on this system ({name!r}): it runs on {', '.join(MODULES)}")
    return importlib.import_module(f"{__name__}.{module}")


_system = load(sys.platform)

config_home = _system.config_home
state_home = _system.state_home
cache_home = _system.cache_home
runtime_dir = _system.runtime_dir
lock = _system.lock
COMMANDS = _system.COMMANDS
raise_app = _system.raise_app
start_app = _system.start_app
clean_environment = _system.clean_environment
find_executables = _system.find_executables
spawn_child = _system.spawn_child
process_host = _system.process_host
