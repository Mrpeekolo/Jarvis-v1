import subprocess
from pathlib import Path
from core.plugins import BasePlugin, PluginMetadata, ParamSpec

WORKSPACE_ROOT = Path("c:/Users/Lil spooky/test").resolve()

class GitStatusPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="get_git_status",
            description="Checks the current git branch, staged/unstaged changes in the workspace.",
            version="1.0.0",
            mode="DEV",
            parameters=[]
        )

    async def execute(self, **kwargs):
        try:
            res = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=str(WORKSPACE_ROOT),
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode != 0:
                return {"note": "Not a git repository or git error", "stderr": res.stderr.strip()}
            return {"git_status": res.stdout.strip() or "Clean working tree"}
        except Exception as e:
            return {"error": f"Git command failed: {str(e)}"}

class SearchCodePlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="search_workspace_code",
            description="Searches for a text pattern or symbol across workspace files.",
            version="1.0.0",
            mode="DEV",
            parameters=[
                ParamSpec(name="query", type="string", description="Word, function name, or keyword to search for")
            ]
        )

    async def execute(self, query: str, **kwargs):
        matches = []
        for file in WORKSPACE_ROOT.rglob("*.py"):
            if "node_modules" in str(file) or ".git" in str(file) or "__pycache__" in str(file):
                continue
            try:
                content = file.read_text(encoding="utf-8", errors="ignore")
                for line_no, line in enumerate(content.splitlines(), start=1):
                    if query.lower() in line.lower():
                        matches.append({
                            "file": str(file.relative_to(WORKSPACE_ROOT)),
                            "line": line_no,
                            "match": line.strip()[:100]
                        })
                        if len(matches) >= 15:
                            break
            except Exception:
                pass
            if len(matches) >= 15:
                break

        return {"query": query, "matches": matches}
