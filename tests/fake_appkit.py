"""A made-up AppKit and objc (the parts of pyobjc that platform/macos.py uses), for the tests on any system. Each
object records the calls it gets. The constants have the values of the macOS SDK."""
from types import SimpleNamespace

CONSTANTS = {
    "NSApplicationActivateAllWindows": 1 << 0,
    "NSApplicationActivationPolicyRegular": 0,
    "NSApplicationActivationPolicyAccessory": 1,
    "NSStatusWindowLevel": 25,
    "NSFloatingWindowLevel": 3,
    "NSWindowStyleMaskBorderless": 0,
    "NSWindowStyleMaskUtilityWindow": 1 << 4,
    "NSWindowStyleMaskNonactivatingPanel": 1 << 7,
    "NSWindowCollectionBehaviorCanJoinAllSpaces": 1 << 0,
    "NSWindowCollectionBehaviorMoveToActiveSpace": 1 << 1,
    "NSWindowCollectionBehaviorStationary": 1 << 4,
    "NSWindowCollectionBehaviorIgnoresCycle": 1 << 6,
    "NSWindowCollectionBehaviorFullScreenPrimary": 1 << 7,
    "NSWindowCollectionBehaviorFullScreenAuxiliary": 1 << 8,
}


class Recorder:
    def __init__(self, calls):
        self.calls = calls


class RunningApp(Recorder):
    def __init__(self, calls, activates=True):
        super().__init__(calls)
        self.activates = activates

    def unhide(self):
        self.calls.append(("unhide",))
        return True

    def activateWithOptions_(self, options):
        self.calls.append(("activateWithOptions_", options))
        return self.activates


class Window(Recorder):
    """A made-up NSPanel as Qt makes it for a Qt::Tool window (QNSPanel), with its state: the getter of each property
    gives it, the setter records the call and changes it."""

    SETTERS = {"setLevel_": "level", "setCollectionBehavior_": "collectionBehavior", "setStyleMask_": "styleMask",
               "setHidesOnDeactivate_": "hidesOnDeactivate", "setHasShadow_": "hasShadow", "setMovable_": "isMovable",
               "setBecomesKeyOnlyIfNeeded_": "becomesKeyOnlyIfNeeded", "_setPreventsActivation_": "preventsActivation"}

    def __init__(self, calls, class_name="QNSPanel", private=True):
        super().__init__(calls)
        self.class_name = class_name
        self.private = private  # whether it answers the private _setPreventsActivation:
        # As Qt 6.12 leaves a frameless Qt::Tool window: floating level, its own collection behaviour, a utility
        # window, hidden when the app is not active.
        self.state = {"level": 3, "collectionBehavior": (1 << 1) | (1 << 7), "styleMask": 1 << 4,
                      "hidesOnDeactivate": True, "hasShadow": False, "isMovable": True, "becomesKeyOnlyIfNeeded": False,
                      "canBecomeKeyWindow": False, "isKeyWindow": False, "isVisible": True, "isOnActiveSpace": True,
                      "preventsActivation": False}

    def className(self):
        return self.class_name

    def isKindOfClass_(self, cls):
        return cls == "NSPanel" and self.class_name.endswith("Panel")

    def respondsToSelector_(self, name):
        if name == "setBecomesKeyOnlyIfNeeded:":
            return self.class_name.endswith("Panel")
        return name == "_setPreventsActivation:" and self.private

    def __getattr__(self, name):
        if name in self.SETTERS:
            def setter(value):
                self.calls.append((name, value))
                self.state[self.SETTERS[name]] = value
            return setter
        if name in self.__dict__.get("state", {}):
            return lambda: self.state[name]
        raise AttributeError(name)


class View:
    def __init__(self, window):
        self._window = window

    def window(self):
        return self._window


class App(Recorder):
    """The made-up NSApp."""

    def __init__(self, calls, has_activate=True):
        super().__init__(calls)
        self.policy = 0
        self.active = False
        self.has_activate = has_activate

    def setActivationPolicy_(self, policy):
        self.calls.append(("setActivationPolicy_", policy))
        self.policy = policy
        return True

    def activationPolicy(self):
        return self.policy

    def isActive(self):
        return self.active

    def respondsToSelector_(self, name):
        return name == "activate" and self.has_activate

    def activate(self):
        self.calls.append(("activate",))
        self.active = True

    def activateIgnoringOtherApps_(self, flag):
        self.calls.append(("activateIgnoringOtherApps_", flag))
        self.active = True


def make_kit(running=(True,), window=None, has_activate=True):
    """A made-up kit: `running` gives the answer of each running Herdr app to its activation (empty: not running).
    `kit.calls` has every call in order; `kit.window` is the native window of every QWindow."""
    calls = []
    window = window or Window(calls)
    window.calls = calls
    app = App(calls, has_activate)
    apps = [RunningApp(calls, answer) for answer in running]

    def running_apps(bundle_id):
        calls.append(("runningApplicationsWithBundleIdentifier_", bundle_id))
        return list(apps)

    def objc_object(c_void_p):
        calls.append(("objc_object", c_void_p))
        return View(window)

    appkit = SimpleNamespace(**CONSTANTS,
                             NSRunningApplication=SimpleNamespace(runningApplicationsWithBundleIdentifier_=running_apps),
                             NSApplication=SimpleNamespace(sharedApplication=lambda: app), NSPanel="NSPanel")
    return SimpleNamespace(AppKit=appkit, objc=SimpleNamespace(objc_object=objc_object), calls=calls, app=app,
                           window=window)
