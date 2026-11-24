from abc import ABC, abstractmethod
import importlib
import inspect
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger("jarvis.plugins")

class ParamSpec(BaseModel):
    name: str
    type: str  # "string", "number", "boolean", "object"
    description: str
    required: bool = True

class PluginMetadata(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    mode: str = "GENERAL"  # "GENERAL", "DEV", "VISION", "OS_AUTO", "GAMING"
    parameters: List[ParamSpec] = []

class BasePlugin(ABC):
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        pass

    def to_tool_schema(self) -> Dict[str, Any]:
        properties = {}
        required = []
        for p in self.metadata.parameters:
            properties[p.name] = {
                "type": p.type,
                "description": p.description
            }
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

class PluginManager:
    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, BasePlugin] = {}
        self.active_mode: str = "GENERAL"

    def reload(self) -> List[str]:
        self.plugins.clear()
        if not self.plugin_dir.exists():
            return []

        for py_file in self.plugin_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            module_name = f"plugins.{py_file.stem}"
            try:
                mod = importlib.import_module(module_name)
                importlib.reload(mod)
                for _, cls in inspect.getmembers(mod, inspect.isclass):
                    if issubclass(cls, BasePlugin) and cls is not BasePlugin:
                        instance = cls()
                        self.plugins[instance.metadata.name] = instance
            except Exception as e:
                logger.error(f"Error loading plugin {module_name}: {e}")

        return list(self.plugins.keys())

    def get_tool_schemas_for_mode(self, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        target_mode = mode or self.active_mode
        # In any specific mode, include both GENERAL tools and mode-specific tools
        schemas = []
        for p in self.plugins.values():
            if p.metadata.mode in ("GENERAL", target_mode):
                schemas.append(p.to_tool_schema())
        return schemas

    async def execute(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self.plugins:
            return {"error": f"Plugin '{name}' not found."}
        try:
            return await self.plugins[name].execute(**args)
        except Exception as e:
            return {"error": f"Plugin '{name}' failed: {str(e)}"}
