# JARVIS — AI Model Handoff Document

> **Purpose:** This file contains everything another AI model (GPT-4, Claude, Gemini, etc.) needs to understand, run, and continue developing this project. Read it top-to-bottom before making any changes.

---

## 1. Project Overview

**JARVIS** is a fully local, zero-telemetry AI assistant built on Python + Ollama. It runs entirely on `127.0.0.1` with no external network calls. The UI is a browser-based SPA served by FastAPI at `http://127.0.0.1:8765`.

### Core Principles
- **Privacy absolute** — all traffic bound to localhost, zero telemetry
- **Local-first** — Ollama for inference, no cloud APIs
- **Discrete by default** — tool calls and internal JSON hidden from chat; shown only on explicit request
- **Modal architecture** — tools scoped to modes (GENERAL, DEV, VISION, OS_AUTO, GAMING)
- **Hot-reloadable plugins** — drop a `.py` file in `plugins/`, hit Reload

### Hardware Target
- **CPU:** Intel i7-4790 (4C/8T, Haswell, AVX2)
- **RAM:** 8 GB total
- **GPU:** AMD Radeon R5 240 + Intel HD 4600 — **NO CUDA, CPU-only inference**
- **OS:** Windows 10/11
- **Python:** 3.13 (Microsoft Store install)

> [!IMPORTANT]
> This hardware is very constrained. Keep models ≤3GB, `num_ctx` at 2048, `num_predict` at 512. No Docker (eats 2-4GB RAM). No Electron (200MB overhead). The web UI is served directly by FastAPI.

---

## 2. How to Run

### Quick Start
```batch
cd jarvis
start_jarvis.bat
```
Or manually:
```bash
cd jarvis
python main.py
```
Then open `http://127.0.0.1:8765` in any browser.

### Prerequisites
1. **Python 3.13+** with pip
2. **Ollama** running on `http://127.0.0.1:11434` with at least one model pulled
3. Python packages:
   ```
   pip install fastapi uvicorn httpx pydantic mss Pillow pywin32
   ```

### Installed Ollama Models
- `qwen2.5-coder:1.5b` (986 MB) — primary default, best speed/quality ratio
- `qwen35-fast:latest` (3.3 GB) — user's custom model
- `qwen3.5:4b` (3.3 GB)

---

## 3. File Map

```
jarvis/
├── main.py                  # FastAPI server — all API routes, SSE chat streaming
├── start_jarvis.bat         # One-click Windows launcher
├── HANDOFF.md               # This file
├── README.md                # Brief project readme
├── test_core.py             # Unit tests: AST sandbox, plugin discovery
├── test_server.py           # Integration tests: server startup, API
│
├── core/
│   ├── config.py            # Pydantic Config: HOST, PORT, OLLAMA_URL, PREFERRED_MODELS
│   ├── llm.py               # OllamaEngine: model selection, SSE stream_chat()
│   ├── plugins.py           # BasePlugin ABC, PluginManager, modal tool scoping
│   └── sandbox.py           # AST security scanner + isolated subprocess executor
│
├── plugins/
│   ├── sys_info.py          # get_system_info (GENERAL)
│   ├── file_manager.py      # list_workspace_files (DEV)
│   ├── dev_tools.py         # get_git_status, search_workspace_code (DEV)
│   ├── os_tools.py          # inspect_windows, control_media, launch_application (OS_AUTO)
│   └── vision_tools.py      # take_screenshot (VISION) — mss→PIL fallback chain
│
└── static/
    ├── index.html           # Full SPA: chat, Monaco editor, screenshots, running apps
    └── screenshots/         # Auto-created dir for captured PNGs
```

---

## 4. Architecture

### Modal Tool System
Tools are scoped by mode. When mode is `DEV`, the LLM sees `GENERAL` + `DEV` tools only.

| Mode     | Tools Available                                           |
|----------|-----------------------------------------------------------|
| GENERAL  | `get_system_info`                                         |
| DEV      | `list_workspace_files`, `get_git_status`, `search_workspace_code` |
| VISION   | `take_screenshot`                                         |
| OS_AUTO  | `inspect_windows`, `control_media`, `launch_application`  |
| GAMING   | *(empty — future phase)*                                  |

### Plugin Contract
Every plugin extends `BasePlugin` from `core/plugins.py`:

```python
from core.plugins import BasePlugin, PluginMetadata, ParamSpec

class MyPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_tool_name",           # unique tool name
            description="What it does",     # shown to LLM
            version="1.0.0",
            mode="DEV",                     # GENERAL|DEV|VISION|OS_AUTO|GAMING
            parameters=[
                ParamSpec(name="query", type="string", description="Search term", required=True)
            ]
        )

    async def execute(self, query: str, **kwargs) -> dict:
        # Do work, return a dict
        return {"result": "..."}
```

Drop the file in `plugins/`, click Reload in the UI (or `POST /api/plugins/reload`). It's auto-discovered.

### AST Sandbox
`core/sandbox.py` scans code via Python's `ast` module before execution:
- **Blocked imports:** `os`, `sys`, `subprocess`, `shutil`, `socket`, `ctypes`, `pty`, `multiprocessing`, `pickle`, `importlib`, `webbrowser`
- **Blocked calls:** `eval()`, `exec()`, `open()`, `compile()`, `__import__()`, `globals()`, `locals()`
- Execution runs in an isolated subprocess with `-I` flag and stripped environment

### LLM Integration
`core/llm.py` wraps the Ollama `/api/chat` endpoint with SSE streaming:
- Auto-selects the best available model from `PREFERRED_MODELS` list
- Passes tool schemas via Ollama's `tools` parameter
- `temperature: 0.2`, `num_ctx: 2048`, `num_predict: 512`
- 180-second HTTP timeout for slow CPU inference

### Small Model Tool-Call Workaround
`qwen2.5-coder:1.5b` does **NOT** reliably use Ollama's native `tools` wire format. Instead it outputs:
````
```json
{"name": "tool_name", "arguments": {"key": "value"}}
```
````
The server has a regex fallback parser (`_extract_json_tool_calls()` in `main.py`) that catches these blocks and dispatches them. Additional mitigations:
- **Dedup set** (`executed_signatures`): prevents the model from re-triggering the same tool call in a loop
- **Tools only on first pass**: second LLM iteration gets no tools, forcing a natural summary
- **JSON buffering**: leading `{` or ` ``` ` tokens are buffered and suppressed from the chat stream so users don't see raw tool JSON

### Discrete Operation
- `httpx` and `uvicorn.access` loggers are suppressed to WARNING
- Internal activity is logged to an in-memory `deque(maxlen=100)` accessible via `GET /api/logs`
- Chat stream hides tool execution by default; user toggles "Activity: Visible" button or asks "show me what you did"
- When user asks about logs/activity, the frontend auto-fetches `/api/logs` and renders the last 8 entries in the tool-trace div

---

## 5. API Reference

All endpoints are on `http://127.0.0.1:8765`.

| Method | Endpoint                | Description                                      |
|--------|-------------------------|--------------------------------------------------|
| GET    | `/`                     | Serves `static/index.html`                       |
| GET    | `/api/status`           | System status: model, mode, plugins, modes_map   |
| GET    | `/api/logs`             | Internal activity log (last 100 entries)          |
| GET    | `/api/apps`             | Running desktop apps via `inspect_windows` plugin |
| GET    | `/api/screenshots`      | List of recent screenshot URLs (last 10)          |
| POST   | `/api/chat`             | SSE streaming chat with tool dispatch             |
| POST   | `/api/mode`             | Switch active mode `{"mode": "DEV"}`              |
| POST   | `/api/sandbox/run`      | Execute sandboxed Python `{"code": "...", "timeout_sec": 5}` |
| POST   | `/api/plugins/reload`   | Hot-reload all plugins from `plugins/` dir        |
| POST   | `/api/screenshot`       | Capture screen via vision plugin                  |
| POST   | `/api/screenshot/upload`| Upload base64 screenshot `{"image_base64": "..."}` |
| GET    | `/static/*`             | Static file serving (index.html, screenshots)     |

### Chat SSE Event Types
The `POST /api/chat` endpoint returns `text/event-stream` with these event types:

```
data: {"type": "mode_info", "mode": "DEV"}
data: {"type": "token", "token": "Hello"}
data: {"type": "tool_start", "tool": "get_git_status", "args": {}}
data: {"type": "tool_result", "tool": "get_git_status", "result": {...}}
data: {"type": "error", "content": "Something went wrong"}
data: {"type": "done"}
```

---

## 6. Frontend (static/index.html)

Single-page app using Tailwind CSS (CDN) and Monaco Editor (CDN).

### Layout
- **Left panel:** Chat stream with SSE streaming, user input, mode indicator
- **Right panel:** Tabbed workspace with 3 tabs:
  - **CODE SANDBOX** — Monaco Python editor + execution console (AST guarded)
  - **SCREENSHOTS** — Capture button, preview image, thumbnail gallery
  - **RUNNING APPS** — Live process list with refresh, active window label, app count

### Key UI Features
- **Mode selector** in header — click to switch modes, updates available tools
- **Model selector** dropdown — populated from Ollama's available models
- **Activity toggle** — "Activity: Hidden/Visible" shows/hides tool trace in chat bubbles
- **Tab switching** — auto-refreshes data when switching to Screenshots or Running Apps tabs
- **Discrete tool handling** — if user asks "show me what you did", frontend auto-fetches `/api/logs`

---

## 7. Known Limitations & Gotchas

### Screenshot Capture in Headless Sessions
Both `mss` and `PIL.ImageGrab` fail with "BitBlt: Access is denied" when JARVIS runs in a headless or sandboxed session (like from an IDE terminal or remote agent). **Fix:** Launch JARVIS from an interactive desktop session via `start_jarvis.bat`. The plugin has a graceful fallback chain and returns an informative error.

### win32gui.EnumWindows
`win32gui.EnumWindows()` throws error 1400 ("Invalid window handle") in certain session contexts. **Fix:** The `inspect_windows` plugin uses `tasklist /FI "STATUS eq RUNNING" /FO CSV` subprocess instead, which works universally.

### Small Model Tool Calling
`qwen2.5-coder:1.5b` outputs tool calls as markdown JSON blocks instead of using Ollama's native tool format. The server's regex parser handles this, but be aware:
- The model may try to call the same tool 2-3 times — the dedup set prevents this
- Tools are only provided on the first LLM iteration to force summarization on the second
- Very complex multi-tool chains may not work reliably with 1.5B models

### FastAPI Deprecation Warning
`@app.on_event("startup")` shows a deprecation warning. Cosmetic only. Can be migrated to the lifespan context manager pattern if desired.

### PowerShell Dollar Sign Escaping
When running commands via PowerShell programmatically, `$variable` references get eaten. Use Python scripts or avoid `$` in PowerShell one-liners when automating.

---

## 8. Future Roadmap

These phases were discussed and agreed upon but are **not yet implemented**:

### Phase 2: Offline Voice Engine
- **Wakeword + STT:** Vosk (offline speech recognition)
- **TTS:** pyttsx3 (offline text-to-speech)
- **Input mode:** Hybrid push-to-talk + wakeword activation
- Packages `vosk` and `pyttsx3` are already pip-installed

### Phase 3: Persistent Memory
- **Database:** SQLite + FTS5 for full-text search
- **Features:** Rolling session summaries, conversation recall, fact extraction
- Keep it file-based, no external DB servers

### Phase 4: Gaming Mode Plugins
- **Input simulation:** PyDirectInput for keyboard/mouse, vgamepad for controller
- **Use cases:** Game automation, macro recording, overlay integration
- Must respect the two-tier safety model (auto-read, guarded-mutate)

### Phase 5: Emergency Kill-Switch
- Global hotkey (e.g., Ctrl+Shift+Escape) to immediately halt all mutating actions
- Two-tier safety: read operations auto-execute, write/mutate operations require confirmation

---

## 9. Dependencies

```
# Core
fastapi
uvicorn
httpx
pydantic

# Sandbox/Vision
mss
Pillow

# Windows OS Tools
pywin32

# Already installed for future phases
vosk
pyttsx3
```

**Python version:** 3.13+ (Microsoft Store install)
**Ollama:** Must be running on port 11434

---

## 10. Testing

```bash
# Unit tests (AST sandbox, plugin discovery)
cd jarvis
python -m pytest test_core.py -v

# Server integration tests
python -m pytest test_server.py -v
```

### What the tests cover:
- `test_core.py`: AST blocks `import os`, safe code executes correctly, plugin discovery loads all plugins
- `test_server.py`: Server startup, `/api/status` returns correct data, UI serves successfully

---

## 11. Quick Reference for Continuing Development

### Adding a new plugin
1. Create `plugins/my_plugin.py`
2. Define a class extending `BasePlugin` with `metadata` property and `execute()` method
3. Set `mode` in metadata to scope it (GENERAL/DEV/VISION/OS_AUTO/GAMING)
4. Click Reload in UI or `POST /api/plugins/reload`

### Adding a new API endpoint
1. Add route in `main.py` using FastAPI decorators
2. For discrete logging: call `log_activity("event_name", detail)` inside the handler
3. Restart the server (kill and re-run `python main.py`)

### Adding a new right-panel tab
1. Add a tab button in the `right-tab-btn` row with `data-tab="newtab"`
2. Add a `tab-action-newtab` div for the action bar
3. Add a `panel-newtab` div for the content
4. The `switchTab()` JS function handles show/hide automatically
5. Add auto-load logic in `switchTab()` if the tab needs data fetching

### Changing the LLM model
- Pull a new model: `ollama pull model-name`
- Add it to `PREFERRED_MODELS` in `core/config.py`
- Or select it from the dropdown in the UI

---

*Generated for AI model handoff. Last updated: 2026-11-24.*
