# OpsPilot — AI Coding Agent Control Center

> A task orchestration center for AI coding agents. Humans assign tasks, AI agents break them into steps, execute, and report progress — all visualized in real time.

## Quick Start

```bash
pip3 install fastapi uvicorn websockets
python3 server.py
# Open http://localhost:5016
```

Default port is 5016, configurable via `OPSPILOT_PORT` environment variable.

## Concept Model

```
Human (You)              OpsPilot (Control Center)        Claude Code (in tmux)
  │                           │                                │
  ├─ Create project+task ───→ │                                │
  │                           ├─ Create tmux session ────────→ │
  │                           ├─ Send task instructions ─────→ │
  │                           │                                ├─ Break into steps
  │                           │                                ├─ Write code
  │                           │                                ├─ Pop up confirmation
  │                           │  ← Detect confirmation ──────  │
  │  ← Show confirm button ── │                                │
  ├─ Click confirm ─────────→ │ ──→ Send confirmation ───────→ │
  │                           │                                ├─ Continue
  │                           │  ← Step completion notice ───  │
  │  ← Step progress update ─ │                                │
  │                           │                                ├─ All done
```

## For AI Agents

If you are an AI Coding Agent (e.g., Claude Code) entering this project:

1. Read this file to understand the project structure
2. Run `python3 server.py` to start the control center
3. The control center provides a Web dashboard + REST API + WebSocket
4. Use `/api/tmux/session` to create tmux sessions and launch separate Claude Code instances
5. Use `/api/tmux/send` to send commands to agents in tmux
6. Use `/api/tmux/capture` to capture agent output
7. Use `/api/tasks` to manage tasks and step progress

## Project Structure

```
OpsPilot/
├── server.py              # FastAPI main (dashboard + API + WebSocket)
├── frontend/
│   └── dashboard.html     # Single-page web dashboard
├── start.sh               # Startup script
├── state/                 # Runtime state (auto-generated)
│   ├── agents.json        # Agent registry
│   ├── projects.json      # Project registry
│   └── tasks.json         # Tasks and steps
├── logs/                  # Event logs
├── CLAUDE.md              # This file
└── README.md
```

## Core API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Web dashboard |
| `/ws` | WS | Real-time state push (every 10s) |
| `/api/state` | GET | Full current state |
| `/api/projects` | POST | Register/update project |
| `/api/agents` | POST | Register/update agent |
| `/api/tasks` | POST | Create task (with step list) |
| `/api/tasks/{id}/start` | POST | Start a task |
| `/api/tasks/{id}/steps/{n}/complete` | POST | Complete a step |
| `/api/tmux/session` | POST | Create tmux session + launch Claude Code |
| `/api/tmux/send` | POST | Send keystrokes to tmux session |
| `/api/tmux/confirm` | POST | Send confirmation (yes/no/enter/escape) |
| `/api/tmux/capture` | POST | Capture tmux pane content |
| `/api/tmux/kill` | POST | Kill a tmux session |
| `/api/tmux/resume` | POST | Resume or re-create a tmux session |
| `/api/tmux/window` | POST | Create new window in a session |
| `/api/tmux/live/{session}` | GET | Get live terminal content |
| `/api/claude/sessions` | GET | List Claude Code sessions for a project |
| `/api/fs/list` | GET | Browse directories (path picker) |

## Managing Multiple Projects

1. Click "+ New" in the dashboard or call `/api/projects` to create a project
2. The system auto-creates a tmux session and launches Claude Code
3. Send commands to specific project agents via the terminal panel or API
4. Each project runs independently without interference
5. The dashboard left sidebar shows all projects — click to switch

## Configuration

Optional environment variables:
- `OPSPILOT_PORT`: Web server port (default: 5016)
- `OPSPILOT_PROJECTS_DIR`: Default project directory (default: ~/Documents/Projects)
