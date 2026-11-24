import csv
import subprocess
import win32gui
import win32con
import win32api
from core.plugins import BasePlugin, PluginMetadata, ParamSpec

VK_CODES = {
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "play_pause": 0xB3,
    "next_track": 0xB0,
    "prev_track": 0xB1
}

SAFE_APPS = {
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe"
}

class WindowsInspectorPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="inspect_windows",
            description="Reports the active foreground window and lists running desktop applications.",
            version="1.0.0",
            mode="OS_AUTO",
            parameters=[]
        )

    async def execute(self, **kwargs):
        active_title = "None"
        try:
            active_hwnd = win32gui.GetForegroundWindow()
            if active_hwnd:
                active_title = win32gui.GetWindowText(active_hwnd) or "Interactive Desktop"
        except Exception:
            pass

        running_apps = []
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", "STATUS eq RUNNING", "/FO", "CSV"],
                text=True,
                timeout=4
            )
            reader = csv.reader(out.strip().splitlines())
            next(reader, None)
            ignored_prefixes = ("svc", "dll", "taskh", "runtim", "csrss", "dwm", "sihost", "conhost")
            for row in reader:
                if row and not row[0].lower().startswith(ignored_prefixes):
                    running_apps.append(row[0])
        except Exception as e:
            running_apps = [f"Process query error: {str(e)}"]

        return {
            "active_window": active_title,
            "running_user_apps": sorted(list(set(running_apps)))[:15]
        }

class MediaControlPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="control_media",
            description="Controls system audio: 'volume_up', 'volume_down', 'volume_mute', or 'play_pause'.",
            version="1.0.0",
            mode="OS_AUTO",
            parameters=[
                ParamSpec(
                    name="action",
                    type="string",
                    description="One of: volume_up, volume_down, volume_mute, play_pause"
                )
            ]
        )

    async def execute(self, action: str, **kwargs):
        action_key = action.lower().strip()
        vk = VK_CODES.get(action_key)
        if not vk:
            return {"error": f"Unknown media action '{action}'. Options: {list(VK_CODES.keys())}"}

        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        return {"status": "success", "executed_action": action_key}

class AppLauncherPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="launch_application",
            description="Launches a whitelisted local desktop application (e.g., 'notepad', 'calc', 'explorer').",
            version="1.0.0",
            mode="OS_AUTO",
            parameters=[
                ParamSpec(
                    name="app_name",
                    type="string",
                    description="Whitelisted app name: 'notepad', 'calc', 'explorer'"
                )
            ]
        )

    async def execute(self, app_name: str, **kwargs):
        app_key = app_name.lower().strip()
        binary = SAFE_APPS.get(app_key)
        if not binary:
            return {"error": f"App '{app_name}' not permitted. Whitelist: {list(SAFE_APPS.keys())}"}

        try:
            subprocess.Popen([binary])
            return {"status": "launched", "application": binary}
        except Exception as e:
            return {"error": f"Failed to launch {binary}: {str(e)}"}
