import platform
from core.plugins import BasePlugin, PluginMetadata, ParamSpec

class SystemInfoPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="get_system_info",
            description="Returns current host operating system, CPU architecture, and Python runtime info.",
            version="1.0.0",
            parameters=[]
        )

    async def execute(self, **kwargs):
        return {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version()
        }
