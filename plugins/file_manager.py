from pathlib import Path
from core.plugins import BasePlugin, PluginMetadata, ParamSpec

WORKSPACE_ROOT = Path("c:/Users/Lil spooky/test").resolve()

class WorkspaceFilePlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="list_workspace_files",
            description="Lists files in the local workspace directory.",
            version="1.0.0",
            mode="DEV",
            parameters=[
                ParamSpec(
                    name="subfolder",
                    type="string",
                    description="Optional relative subfolder path within workspace (e.g. 'jarvis' or '.')",
                    required=False
                )
            ]
        )

    async def execute(self, subfolder: str = ".", **kwargs):
        target = (WORKSPACE_ROOT / subfolder).resolve()
        if not str(target).startswith(str(WORKSPACE_ROOT)):
            return {"error": "Access denied: Path is outside workspace root."}
        
        if not target.exists():
            return {"error": f"Path does not exist: {subfolder}"}

        items = []
        for p in target.iterdir():
            items.append({
                "name": p.name,
                "is_dir": p.is_dir(),
                "size_bytes": p.stat().st_size if p.is_file() else 0
            })
        return {"path": str(target), "files": items[:50]}
