import asyncio
import json
import logging
import re
import time
from collections import deque
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import cfg
from core.plugins import PluginManager
from core.llm import llm_engine
from core.sandbox import run_sandboxed

# Keep logs discrete: suppress noisy httpx/httpcore request logs
logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger("jarvis.server")
logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
plugins_dir = BASE_DIR / "plugins"
static_dir = BASE_DIR / "static"
screenshots_dir = static_dir / "screenshots"
screenshots_dir.mkdir(parents=True, exist_ok=True)

plugin_mgr = PluginManager(plugins_dir)
activity_logs = deque(maxlen=100)

def log_activity(event: str, detail: Any):
    activity_logs.append({
        "timestamp": time.strftime("%H:%M:%S"),
        "event": event,
        "detail": detail
    })

app = FastAPI(title="JARVIS Discrete Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatPayload(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    mode: Optional[str] = None

class ModePayload(BaseModel):
    mode: str

class CodeExecPayload(BaseModel):
    code: str
    timeout_sec: Optional[int] = 5

@app.on_event("startup")
def on_startup():
    loaded = plugin_mgr.reload()
    log_activity("startup", f"Loaded {len(loaded)} plugins: {loaded}")
    logger.info(f"JARVIS online on http://{cfg.HOST}:{cfg.PORT} ({len(loaded)} plugins)")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/api/status")
async def get_status():
    available_models = await llm_engine.get_available_models()
    active_model = await llm_engine.select_best_model()

    modes_map = {}
    for p in plugin_mgr.plugins.values():
        m = p.metadata.mode
        modes_map.setdefault(m, []).append(p.metadata.name)

    return {
        "status": "online",
        "active_model": active_model,
        "available_models": available_models,
        "active_mode": plugin_mgr.active_mode,
        "available_modes": ["GENERAL", "DEV", "VISION", "OS_AUTO", "GAMING"],
        "modes_map": modes_map,
        "active_plugins": list(plugin_mgr.plugins.keys()),
        "host": cfg.HOST,
        "port": cfg.PORT
    }

class ScreenshotUploadPayload(BaseModel):
    image_base64: str

@app.get("/api/logs")
async def get_logs():
    return {"logs": list(activity_logs)}

@app.get("/api/apps")
async def get_running_apps():
    res = await plugin_mgr.execute("inspect_windows", {})
    return {
        "active_window": res.get("active_window", "None"),
        "apps": res.get("running_user_apps", [])
    }

@app.post("/api/screenshot")
async def capture_screenshot():
    res = await plugin_mgr.execute("take_screenshot", {})
    log_activity("screenshot", res.get("status", "unknown"))
    return res

@app.post("/api/screenshot/upload")
async def upload_screenshot(payload: ScreenshotUploadPayload):
    import base64
    data = payload.image_base64
    if "," in data:
        data = data.split(",", 1)[1]
    img_bytes = base64.b64decode(data)
    ts = int(time.time())
    filename = f"screen_{ts}.png"
    (screenshots_dir / filename).write_bytes(img_bytes)
    (screenshots_dir / "latest.png").write_bytes(img_bytes)
    log_activity("screenshot_upload", filename)
    return {
        "status": "captured",
        "image_url": f"/static/screenshots/{filename}",
        "latest_url": "/static/screenshots/latest.png"
    }

@app.get("/api/screenshots")
async def list_screenshots():
    files = sorted(
        [f.name for f in screenshots_dir.glob("screen_*.png")],
        reverse=True
    )[:10]
    return {"screenshots": [f"/static/screenshots/{name}" for name in files]}

@app.post("/api/mode")
async def set_mode(payload: ModePayload):
    valid_modes = {"GENERAL", "DEV", "VISION", "OS_AUTO", "GAMING"}
    m = payload.mode.upper().strip()
    if m not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Choose from: {valid_modes}")
    plugin_mgr.active_mode = m
    log_activity("mode_change", m)
    return {"status": "success", "active_mode": plugin_mgr.active_mode}

@app.post("/api/plugins/reload")
async def reload_plugins():
    loaded = plugin_mgr.reload()
    log_activity("plugins_reload", loaded)
    return {"status": "reloaded", "plugins": loaded, "mode": plugin_mgr.active_mode}

@app.post("/api/sandbox/run")
async def execute_code(payload: CodeExecPayload):
    timeout = payload.timeout_sec or cfg.SANDBOX_TIMEOUT_SEC
    result = await run_sandboxed(payload.code, timeout_sec=timeout)
    log_activity("sandbox_run", {"success": result["success"], "violation": result.get("violation")})
    return result

def _extract_json_tool_calls(text: str) -> List[Dict[str, Any]]:
    calls = []
    # Match fenced ```json ... ``` blocks or raw JSON objects containing "name"
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not blocks and text.strip().startswith("{") and text.strip().endswith("}"):
        blocks = [text.strip()]
    for block in blocks:
        try:
            parsed = json.loads(block)
            name = parsed.get("name") or parsed.get("function")
            args = parsed.get("arguments") or parsed.get("parameters") or {}
            if not isinstance(args, dict):
                args = {}
            if name and name in plugin_mgr.plugins:
                calls.append({"function": {"name": name, "arguments": args}})
        except json.JSONDecodeError:
            pass
    return calls

@app.post("/api/chat")
async def chat_stream(payload: ChatPayload):
    latest_msg = payload.messages[-1].content if payload.messages else ""
    mode_switch_match = re.search(r"\b(switch to|set mode to|enable)\s+(dev|vision|os|gaming|general)\b", latest_msg, re.IGNORECASE)
    if mode_switch_match:
        target = mode_switch_match.group(2).upper()
        if target == "OS":
            target = "OS_AUTO"
        plugin_mgr.active_mode = target

    active_mode = (payload.mode or plugin_mgr.active_mode).upper()
    tools = plugin_mgr.get_tool_schemas_for_mode(active_mode)

    history = [
        {
            "role": "system",
            "content": (
                f"You are JARVIS, a discrete, local AI assistant. CURRENT MODE: [{active_mode}]. "
                "Be direct, concise, and helpful. "
                "Do NOT narrate or explain your internal tool usage unless the user explicitly asks what you are doing. "
                "When a tool returns data, summarize the answer naturally for the user."
            )
        }
    ]
    for m in payload.messages:
        history.append({"role": m.role, "content": m.content})

    async def event_stream():
        yield f"data: {json.dumps({'type': 'mode_info', 'mode': active_mode})}\n\n"

        current_history = list(history)
        executed_signatures = set()
        max_tool_iterations = 2

        for iteration in range(max_tool_iterations):
            tool_calls = []
            accumulated_content = ""
            buffering_potential_json = True
            buffer = ""

            # Only provide tools on the first pass so the model summarizes cleanly on the second pass
            pass_tools = tools if iteration == 0 else None

            async for chunk in llm_engine.stream_chat(
                messages=current_history,
                model=payload.model,
                tools=pass_tools
            ):
                if chunk.get("type") == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': chunk.get('content')})}\n\n"
                    return

                msg = chunk.get("message", {})
                content = msg.get("content", "")

                if content:
                    accumulated_content += content
                    if buffering_potential_json:
                        buffer += content
                        stripped = buffer.lstrip()
                        if len(stripped) >= 3:
                            # If it looks like a raw JSON tool call block, keep it hidden from chat tokens
                            if stripped.startswith("```") or stripped.startswith("{"):
                                pass
                            else:
                                buffering_potential_json = False
                                yield f"data: {json.dumps({'type': 'token', 'token': buffer})}\n\n"
                                buffer = ""
                    else:
                        yield f"data: {json.dumps({'type': 'token', 'token': content})}\n\n"

                if "tool_calls" in msg:
                    tool_calls.extend(msg["tool_calls"])

                if chunk.get("done", False):
                    break

            # Fallback tool parser for small models formatting calls as JSON
            if not tool_calls and accumulated_content:
                tool_calls = _extract_json_tool_calls(accumulated_content)

            # If we buffered text that turned out NOT to be a tool call, flush it to user
            if buffering_potential_json and buffer and not tool_calls:
                yield f"data: {json.dumps({'type': 'token', 'token': buffer})}\n\n"

            if not tool_calls:
                break

            ran_any_tool = False
            for t in tool_calls:
                func = t.get("function", {})
                name = func.get("name")
                args = func.get("arguments", {})
                if not isinstance(args, dict):
                    args = {}

                sig = f"{name}:{json.dumps(args, sort_keys=True)}"
                if sig in executed_signatures:
                    continue
                executed_signatures.add(sig)
                ran_any_tool = True

                log_activity("tool_call", {"tool": name, "args": args})
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': name, 'args': args})}\n\n"
                res = await plugin_mgr.execute(name, args)
                log_activity("tool_result", {"tool": name, "result": res})
                yield f"data: {json.dumps({'type': 'tool_result', 'tool': name, 'result': res})}\n\n"

                current_history.append({
                    "role": "assistant",
                    "content": accumulated_content or f"Running {name}..."
                })
                current_history.append({
                    "role": "user",
                    "content": f"[Tool Output for {name}]: {json.dumps(res)}\n\nSummarize this result concisely for the user without mentioning internal tools or JSON."
                })

            if not ran_any_tool:
                break

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "JARVIS API is running. UI not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=cfg.HOST, port=cfg.PORT, reload=False, log_level="warning")
