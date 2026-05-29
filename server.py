"""
OpsPilot - AI Coding Agent Control Center
Web dashboard on port 5016, manages multiple Claude Code agents via tmux.
"""
import asyncio
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
LOGS_DIR = BASE_DIR / "logs"
FRONTEND_DIR = BASE_DIR / "frontend"

for d in [STATE_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="OpsPilot - Agent Control Center")

ws_clients: list[WebSocket] = []
log_buffer: list[dict] = []
MAX_LOGS = 500


def add_log(level: str, source: str, message: str):
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "ts": datetime.now().isoformat(),
        "level": level,
        "source": source,
        "message": message,
    }
    log_buffer.append(entry)
    if len(log_buffer) > MAX_LOGS:
        log_buffer.pop(0)
    with open(LOGS_DIR / "events.log", "a") as f:
        f.write(f"[{entry['time']}] [{level}] [{source}] {message}\n")


def load_agents() -> dict:
    """Load agent registry from disk."""
    path = STATE_DIR / "agents.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_agents(agents: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "agents.json", "w") as f:
        json.dump(agents, f, indent=2, ensure_ascii=False)


def load_projects() -> dict:
    path = STATE_DIR / "projects.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_projects(projects: dict):
    with open(STATE_DIR / "projects.json", "w") as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)


def load_tasks() -> dict:
    """Load task registry. Keyed by project name."""
    path = STATE_DIR / "tasks.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_tasks(tasks: dict):
    with open(STATE_DIR / "tasks.json", "w") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)


def get_tmux_status(session_name: str) -> dict:
    """Check if a tmux session exists and get its windows."""
    try:
        result = subprocess.run(
            ["tmux", "list-windows", "-t", session_name, "-F", "#{window_index}:#{window_name}:#{window_active}"],
            capture_output=True, text=True, timeout=5
        )
        # Exit code non-zero means session doesn't exist
        if result.returncode != 0 or "can't find session" in result.stderr.lower() or "no server running" in result.stderr.lower():
            return {"running": False, "windows": [], "active_window": None}
        windows = []
        active_window = None
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split(":", 2)
                if len(parts) == 3:
                    windows.append({"index": parts[0], "name": parts[1], "active": parts[2] == "1"})
                    if parts[2] == "1":
                        active_window = parts[0]
        return {"running": True, "windows": windows, "active_window": active_window}
    except Exception:
        return {"running": False, "windows": [], "active_window": None}


async def broadcast(data: dict):
    disconnected = []
    for ws in ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_clients.remove(ws)


# ── REST API ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = FRONTEND_DIR / "dashboard.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>OpsPilot Dashboard</h1><p>dashboard.html not found</p>")


@app.get("/api/state")
async def get_state():
    return await _build_state()


@app.post("/api/git/pull")
async def git_pull():
    """Pull latest code from GitHub."""
    import subprocess as _sp
    try:
        r = _sp.run(["git", "pull", "origin", "main"], capture_output=True, text=True, cwd=str(BASE_DIR), timeout=30)
        add_log("info", "update", f"git pull: {r.stdout.strip() or r.stderr.strip()}")
        if "Already up to date" in r.stdout or "Already up-to-date" in r.stdout:
            return {"status": "ok", "message": "Already up to date"}
        return {"status": "ok", "message": r.stdout.strip() or "Updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/version")
async def check_version():
    """Check current version and compare with latest GitHub release."""
    import subprocess as _sp
    info = {
        "current_commit": "",
        "current_short": "",
        "latest_commit": "",
        "latest_short": "",
        "update_available": False,
        "commits_behind": 0,
    }
    try:
        # Get current commit
        r = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(BASE_DIR), timeout=5)
        if r.returncode == 0:
            info["current_commit"] = r.stdout.strip()
            info["current_short"] = info["current_commit"][:7]
        # Get latest from remote (without pulling)
        r2 = _sp.run(["git", "ls-remote", "origin", "HEAD"], capture_output=True, text=True, timeout=10)
        if r2.returncode == 0 and r2.stdout.strip():
            info["latest_commit"] = r2.stdout.split()[0]
            info["latest_short"] = info["latest_commit"][:7]
        if info["current_commit"] and info["latest_commit"] and info["current_commit"] != info["latest_commit"]:
            # Count commits behind
            r3 = _sp.run(
                ["git", "rev-list", "--count", f"{info['current_commit']}..{info['latest_commit']}"],
                capture_output=True, text=True, timeout=5
            )
            if r3.returncode == 0:
                info["commits_behind"] = int(r3.stdout.strip())
            info["update_available"] = info["commits_behind"] > 0
    except Exception:
        pass
    return info


@app.post("/api/agents")
async def register_agent(data: dict):
    """Register or update an agent."""
    agents = load_agents()
    name = data.get("name", "unnamed")
    agents[name] = {
        "name": name,
        "project": data.get("project", ""),
        "tmux_session": data.get("tmux_session", ""),
        "tmux_window": data.get("tmux_window", "0"),
        "status": data.get("status", "idle"),
        "task": data.get("task", ""),
        "last_active": datetime.now().isoformat(),
        "items_processed": data.get("items_processed", 0),
        **(data.get("meta", {})),
    }
    save_agents(agents)
    add_log("info", name, f"Agent registered: {data.get('status', 'idle')}")
    await broadcast(await _build_state())
    return {"status": "ok", "agent": agents[name]}


@app.post("/api/agents/{name}/status")
async def update_agent_status(name: str, data: dict):
    agents = load_agents()
    if name not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    agents[name].update({
        "status": data.get("status", agents[name]["status"]),
        "task": data.get("task", agents[name].get("task", "")),
        "last_active": datetime.now().isoformat(),
        "items_processed": data.get("items_processed", agents[name].get("items_processed", 0)),
    })
    if "message" in data:
        agents[name]["message"] = data["message"]
    save_agents(agents)
    add_log("info", name, f"Status: {data.get('status')} - {data.get('message', '')}")
    await broadcast(await _build_state())
    return {"status": "ok"}


@app.post("/api/projects")
async def upsert_project(data: dict):
    projects = load_projects()
    name = data.get("name", "unnamed")
    # Merge with existing if present
    existing = projects.get(name, {})
    projects[name] = {
        "name": name,
        "path": data.get("path", existing.get("path", "")),
        "status": data.get("status", existing.get("status", "active")),
        "description": data.get("description", existing.get("description", "")),
        "agents": data.get("agents", existing.get("agents", [])),
        "kanban_status": data.get("kanban_status", existing.get("kanban_status", "in_progress")),
        "updated": datetime.now().isoformat(),
    }
    save_projects(projects)
    add_log("info", "project", f"Project updated: {name}")
    await broadcast(await _build_state())
    return {"status": "ok"}


# ── Task & Step Management ────────────────────────

@app.post("/api/tasks")
async def create_task(data: dict):
    """Create a new task for a project."""
    project_name = data.get("project", "")
    tasks = load_tasks()

    task_id = str(int(time.time() * 1000))
    steps_raw = data.get("steps", [])
    # Support both step formats: ["name", ...] or [{"name": "...", "status": "..."}, ...]
    steps = []
    for s in steps_raw:
        if isinstance(s, str):
            steps.append({"name": s, "status": "pending", "started_at": None, "completed_at": None, "duration_seconds": 0})
        else:
            steps.append({
                "name": s.get("name", ""),
                "status": s.get("status", "pending"),
                "started_at": s.get("started_at"),
                "completed_at": s.get("completed_at"),
                "duration_seconds": s.get("duration_seconds", 0),
            })

    task = {
        "id": task_id,
        "project": project_name,
        "title": data.get("title", "Untitled Task"),
        "description": data.get("description", ""),
        "status": "queued",  # queued, running, completed, failed
        "steps": steps,
        "current_step": 0,
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
    }
    tasks[task_id] = task
    save_tasks(tasks)
    add_log("info", "task", f"Task created: {task['title']} for {project_name} ({len(steps)} steps)")
    await broadcast(await _build_state())
    return {"status": "ok", "task": task}


@app.post("/api/tasks/{task_id}/start")
async def start_task(task_id: str):
    """Mark a task as running and start its first step."""
    tasks = load_tasks()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    task["status"] = "running"
    task["started_at"] = datetime.now().isoformat()
    if task["steps"]:
        task["steps"][0]["status"] = "running"
        task["steps"][0]["started_at"] = datetime.now().isoformat()
        task["current_step"] = 0
    save_tasks(tasks)
    add_log("info", "task", f"Task started: {task['title']}")
    await broadcast(await _build_state())
    return {"status": "ok", "task": task}


@app.post("/api/tasks/{task_id}/steps/{step_index}/complete")
async def complete_step(task_id: str, step_index: int, data: dict = None):
    """Mark a step as completed and advance to the next."""
    tasks = load_tasks()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    steps = task["steps"]
    if step_index >= len(steps):
        raise HTTPException(status_code=400, detail="Invalid step index")

    now = datetime.now().isoformat()
    step = steps[step_index]
    step["status"] = "completed"
    step["completed_at"] = now
    if step.get("started_at"):
        try:
            start = datetime.fromisoformat(step["started_at"])
            step["duration_seconds"] = int((datetime.now() - start).total_seconds())
        except Exception:
            pass

    # Start next step if exists
    next_idx = step_index + 1
    if next_idx < len(steps):
        steps[next_idx]["status"] = "running"
        steps[next_idx]["started_at"] = now
        task["current_step"] = next_idx
    else:
        # All steps done
        task["status"] = "completed"
        task["completed_at"] = now
        task["current_step"] = len(steps)

    save_tasks(tasks)
    add_log("info", "task", f"Step {step_index+1}/{len(steps)} completed: {step['name']}")
    await broadcast(await _build_state())
    return {"status": "ok", "task": task, "completed_step": step}


@app.post("/api/tasks/{task_id}/steps/{step_index}/fail")
async def fail_step(task_id: str, step_index: int):
    """Mark a step as failed."""
    tasks = load_tasks()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    step = task["steps"][step_index]
    step["status"] = "failed"
    step["completed_at"] = datetime.now().isoformat()
    if step.get("started_at"):
        try:
            step["duration_seconds"] = int((datetime.now() - datetime.fromisoformat(step["started_at"])).total_seconds())
        except Exception:
            pass
    save_tasks(tasks)
    add_log("error", "task", f"Step failed: {step['name']}")
    await broadcast(await _build_state())
    return {"status": "ok", "step": step}


@app.post("/api/tasks/{task_id}/status")
async def update_task_status(task_id: str, data: dict):
    """Update task status."""
    tasks = load_tasks()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    task["status"] = data.get("status", task["status"])
    if data.get("status") == "completed":
        task["completed_at"] = datetime.now().isoformat()
    save_tasks(tasks)
    add_log("info", "task", f"Task status: {task['status']}")
    await broadcast(await _build_state())
    return {"status": "ok", "task": task}


# ── Tmux Control ──────────────────────────────────

@app.post("/api/tmux/kill")
async def kill_tmux_session(data: dict):
    """Kill a tmux session."""
    session = data.get("session", "")
    if not session:
        raise HTTPException(status_code=400, detail="session required")
    try:
        subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True, text=True, timeout=5)
        add_log("info", "tmux", f"Session killed: {session}")
        # Update agent status
        agents = load_agents()
        for name, a in agents.items():
            if a.get("tmux_session") == session:
                a["status"] = "stopped"
        save_agents(agents)
        await broadcast(await _build_state())
        return {"status": "ok", "session": session}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tmux/window")
async def create_tmux_window(data: dict):
    """Create a new window in an existing tmux session."""
    session = data.get("session", "")
    window_name = data.get("window_name", "dev2")
    cwd = data.get("cwd", "")
    if not session:
        raise HTTPException(status_code=400, detail="session required")
    try:
        cmd = ["tmux", "new-window", "-t", session, "-n", window_name]
        if cwd:
            cmd += ["-c", cwd]
        subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        add_log("info", "tmux", f"New window {window_name} in session {session}")
        return {"status": "ok", "session": session, "window": window_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tmux/resume")
async def resume_tmux_session(data: dict):
    """Resume or create a tmux session. If it exists, return status. If not, re-create it."""
    session = data.get("session", "")
    project_dir = data.get("project_dir", "")
    if not session:
        raise HTTPException(status_code=400, detail="session required")

    # Ensure project dir exists
    if project_dir:
        os.makedirs(project_dir, exist_ok=True)

    status = get_tmux_status(session)
    if status["running"]:
        return {"status": "already_running", "session": session, "tmux": status}

    # Re-create the session
    try:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-n", "dev", "-c", project_dir or str(BASE_DIR)],
            capture_output=True, text=True, timeout=5
        )
        time.sleep(1)

        # Auto-start Claude Code with resume
        resume_id = data.get("resume_id", "")
        if resume_id:
            claude_cmd = f"claude --resume {resume_id}"
        else:
            claude_cmd = "claude --resume"

        subprocess.run(
            ["tmux", "send-keys", "-t", f"{session}:dev", claude_cmd, "Enter"],
            capture_output=True, text=True, timeout=5
        )

        add_log("info", "tmux", f"Session {session} resumed, Claude Code starting with --resume")
        return {"status": "resumed", "session": session, "tmux": get_tmux_status(session)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/claude/sessions")
async def list_claude_sessions(project_dir: str = ""):
    """List Claude Code sessions, optionally filtered by project directory."""
    import glob as _glob
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    sessions = []
    try:
        for f in sorted(_glob.glob(os.path.join(sessions_dir, "*.json")), reverse=True):
            try:
                data = json.loads(Path(f).read_text())
                sid = data.get("sessionId", "")
                cwd = data.get("cwd", "")
                status = data.get("status", "unknown")
                started = data.get("startedAt", "")
                updated = data.get("updatedAt", "")
                # Filter by project dir if specified
                if project_dir and project_dir not in cwd:
                    continue
                sessions.append({
                    "id": sid,
                    "cwd": cwd,
                    "status": status,
                    "started_at": started,
                    "updated_at": updated,
                })
            except Exception:
                pass
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@app.get("/api/fs/list")
async def list_directory(path: str = ""):
    """List subdirectories for the path picker."""
    import os as _os
    target = path or str(Path.home() / "Documents" / "Projects")
    target = _os.path.expanduser(target)
    if not _os.path.isdir(target):
        return {"path": target, "parent": str(Path(target).parent), "dirs": [], "error": "Not a directory"}
    try:
        items = []
        for name in sorted(_os.listdir(target)):
            full = _os.path.join(target, name)
            if _os.path.isdir(full) and not name.startswith('.'):
                items.append({"name": name, "path": full})
        parent = str(Path(target).parent) if target != "/" else "/"
        return {"path": target, "parent": parent, "dirs": items}
    except PermissionError:
        return {"path": target, "parent": str(Path(target).parent), "dirs": [], "error": "Permission denied"}


@app.post("/api/tmux/send")
async def tmux_send_keys(data: dict):
    """Send keys to a tmux session/window."""
    session = data.get("session", "")
    window = data.get("window", "0")
    keys = data.get("keys", "")
    if not session or not keys:
        raise HTTPException(status_code=400, detail="session and keys required")
    target = f"{session}:{window}"
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", target, keys, "Enter"],
            capture_output=True, text=True, timeout=5
        )
        add_log("info", "tmux", f"Sent to {target}: {keys[:100]}")
        return {"status": "ok", "target": target}
    except Exception as e:
        add_log("error", "tmux", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tmux/session")
async def create_tmux_session(data: dict):
    """Create a new tmux session with a Claude Code agent."""
    session_name = data.get("name", "odineye")
    project_dir = data.get("project_dir", "")
    initial_prompt = data.get("prompt", "")

    # Check if session exists
    existing = get_tmux_status(session_name)
    if existing["running"]:
        return {"status": "exists", "session": session_name, "tmux": existing}

    try:
        # Ensure project directory exists
        if project_dir:
            os.makedirs(project_dir, exist_ok=True)

        # Create detached session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-n", "dev", "-c", project_dir or str(BASE_DIR)],
            capture_output=True, text=True, timeout=5
        )
        # Send initial Claude Code command
        if initial_prompt:
            time.sleep(1)  # Wait for shell to init
            escaped = initial_prompt.replace("'", "'\\''")
            subprocess.run(
                ["tmux", "send-keys", "-t", f"{session_name}:dev", "claude", "Enter"],
                capture_output=True, text=True, timeout=5
            )
            time.sleep(2)  # Wait for Claude Code to start
            subprocess.run(
                ["tmux", "send-keys", "-t", f"{session_name}:dev", escaped, "Enter"],
                capture_output=True, text=True, timeout=5
            )

        add_log("info", "tmux", f"Session {session_name} created, Claude Code started")
        return {"status": "created", "session": session_name, "tmux": get_tmux_status(session_name)}
    except Exception as e:
        add_log("error", "tmux", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tmux/capture")
async def tmux_capture(data: dict):
    """Capture pane content from a tmux session."""
    session = data.get("session", "")
    window = data.get("window", "0")
    lines = int(data.get("lines", 50))
    return _capture_tmux(session, window, lines)


@app.get("/api/tmux/live/{session}")
async def tmux_live(session: str, window: str = "0", lines: int = 80):
    """GET endpoint to capture tmux pane content (for live view)."""
    return _capture_tmux(session, window, lines)


def _capture_tmux(session: str, window: str, lines: int) -> dict:
    target = f"{session}:{window}"
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", target, "-p", "-S", f"-{lines}"],
            capture_output=True, text=True, timeout=5
        )
        # Strip ANSI escape codes for clean display
        import re
        clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', result.stdout)
        return {"status": "ok", "content": clean, "target": target}
    except Exception as e:
        return {"status": "error", "content": str(e), "target": target}


# Cache for live terminal outputs
_tmux_cache: dict = {}

async def _capture_all_tmux_sessions():
    """Periodically capture all tmux sessions for live display."""
    agents = load_agents()
    for name, agent in agents.items():
        session = agent.get("tmux_session", "")
        if session:
            window = agent.get("tmux_window", "0")
            cap = _capture_tmux(session, window, 80)
            _tmux_cache[session] = cap
    return _tmux_cache


@app.post("/api/tmux/confirm")
async def tmux_confirm(data: dict):
    """Send confirmation (Enter, Y, or custom key) to a tmux session. Used to handle Claude Code prompts."""
    session = data.get("session", "odineye")
    window = data.get("window", "0")
    # "yes" sends "1" then Enter (selects first option), "enter" just presses Enter
    action = data.get("action", "enter")
    target = f"{session}:{window}"
    key_map = {"enter": "Enter", "yes": "1", "no": "2", "y": "y", "n": "n", "escape": "Escape", "yes_allow_all": "2"}
    key = key_map.get(action, action)
    needs_enter = action in ("yes", "y", "no", "n", "yes_allow_all")
    try:
        cmd = ["tmux", "send-keys", "-t", target, key]
        if needs_enter:
            cmd.append("Enter")
        subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        add_log("info", "tmux", f"Confirmation sent to {target}: {action} ({key})")
        return {"status": "ok", "target": target, "action": action}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/log")
async def add_log_entry(data: dict):
    add_log(
        data.get("level", "info"),
        data.get("source", "system"),
        data.get("message", "")
    )
    await broadcast(await _build_state())
    return {"status": "ok"}


# ── WebSocket ─────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    add_log("info", "ws", f"Client connected ({len(ws_clients)} total)")
    try:
        # Send initial state
        await websocket.send_json(await _build_state())
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json(await _build_state())
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)


async def _build_state() -> dict:
    agents = load_agents()
    projects = load_projects()
    for name, agent in agents.items():
        session = agent.get("tmux_session", "")
        if session:
            agent["tmux"] = get_tmux_status(session)
    # Include live terminal captures
    await _capture_all_tmux_sessions()
    # Find active task per project
    all_tasks = load_tasks()
    project_tasks = {}
    for tid, t in all_tasks.items():
        pn = t.get("project", "")
        if pn not in project_tasks:
            project_tasks[pn] = []
        project_tasks[pn].append(t)
    return {
        "agents": agents,
        "projects": projects,
        "tasks": all_tasks,
        "project_tasks": project_tasks,
        "logs": log_buffer[-100:],
        "terminals": _tmux_cache,
        "time": datetime.now().isoformat(),
    }


@app.on_event("startup")
async def startup():
    add_log("info", "system", "OpsPilot Control Center starting on port 5016")
    asyncio.create_task(_periodic_broadcast())


# ── Auto-detection of Claude Code progress ──────────

# Track which completions we've already processed to avoid double-counting
_seen_completions: set = set()


async def _auto_detect_progress():
    """Scan tmux output for Claude Code task completion patterns and auto-update steps."""
    tasks = load_tasks()
    agents = load_agents()
    changed = False

    for tid, task in tasks.items():
        if task.get("status") != "running":
            continue

        project_name = task.get("project", "")
        # Find the tmux session for this project's agent
        proj_agents = [a for a in agents.values() if a.get("project") == project_name]
        if not proj_agents:
            continue
        session = proj_agents[0].get("tmux_session", "")
        if not session:
            continue

        # Capture terminal output
        cap = _capture_tmux(session, "0", 100)
        content = cap.get("content", "")

        # Pattern: ✔ <step_name>  (Claude Code completion checkmark)
        import re as _re
        completed_items = _re.findall(r'✔\s+(.+?)(?:\n|$)', content)

        steps = task.get("steps", [])
        for step_idx, step in enumerate(steps):
            if step.get("status") not in ("running", "pending"):
                continue

            step_name = step.get("name", "")
            for item in completed_items:
                # Fuzzy match: check if the completed item contains step name keywords
                item_lower = item.lower().strip()
                step_lower = step_name.lower().strip()

                # Try direct match or keyword match
                match = (
                    step_lower in item_lower or
                    item_lower in step_lower or
                    any(kw in item_lower for kw in step_lower.split() if len(kw) > 2)
                )

                if match:
                    dedup_key = f"{tid}:{step_idx}:{item}"
                    if dedup_key in _seen_completions:
                        continue
                    _seen_completions.add(dedup_key)

                    # Auto-complete this step
                    now = datetime.now().isoformat()
                    step["status"] = "completed"
                    step["completed_at"] = now
                    if step.get("started_at"):
                        try:
                            start = datetime.fromisoformat(step["started_at"])
                            step["duration_seconds"] = int((datetime.now() - start).total_seconds())
                        except Exception:
                            pass

                    # Start next step
                    next_idx = step_idx + 1
                    if next_idx < len(steps):
                        steps[next_idx]["status"] = "running"
                        steps[next_idx]["started_at"] = now
                        task["current_step"] = next_idx
                    else:
                        task["status"] = "completed"
                        task["completed_at"] = now
                        task["current_step"] = len(steps)

                    add_log("info", "auto-detect", f"{project_name}: step {step_idx+1}/{len(steps)} '{step_name}' → completed (auto)")
                    changed = True
                    break

    if changed:
        save_tasks(tasks)


async def _periodic_broadcast():
    while True:
        await asyncio.sleep(10)
        try:
            await _auto_detect_progress()
            if ws_clients:
                await broadcast(await _build_state())
        except Exception:
            pass


if __name__ == "__main__":
    add_log("info", "system", "Booting OpsPilot...")
    uvicorn.run(app, host="0.0.0.0", port=5016, log_level="info")
