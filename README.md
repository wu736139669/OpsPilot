# OpsPilot — AI Coding Agent Control Center

A **task orchestration center for AI coding agents**. Assign development tasks, let AI agents break them into steps, execute, and report progress — all visualized in a web dashboard.

## Why OpsPilot?

If you use Claude Code, Cursor, Codex, or other AI coding tools across multiple projects, you face these problems:

- Manually opening tmux sessions and launching AI agents for each project
- Switching terminals to approve confirmation prompts mid-execution
- No visibility into which project is doing what
- Opaque task progress — you don't know what step the agent is on

OpsPilot solves all of this with a single web console for managing multiple AI coding agents simultaneously.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/wu736139669/OpsPilot.git
cd OpsPilot

# 2. Install dependencies (only FastAPI needed)
pip3 install fastapi uvicorn websockets

# 3. Start
python3 server.py

# 4. Open browser
open http://localhost:5016
```

> Prerequisites: Python 3.9+, tmux, Claude Code CLI (`claude` command available)

## Usage

### Option 1: Web Dashboard (Recommended)

Open `http://localhost:5016` and:
1. Click **+ New** to create a project
2. Use the directory browser to pick a project path
3. Enter a task description
4. The system auto-creates a tmux session, launches Claude Code, and tracks steps
5. Click confirm buttons directly in the browser when prompts appear

### Option 2: API

```bash
# Create a project
curl -X POST http://localhost:5016/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"MyProject","path":"/path/to/project"}'

# Assign a task
curl -X POST http://localhost:5016/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"project":"MyProject","title":"Build a REST API","steps":["DB schema","API routes","Tests","Deploy"]}'
```

### Option 3: Let Another AI Agent Manage It

If you're in a different project with Claude Code, you can have it manage OpsPilot via API — create projects, spawn agents, and track progress programmatically.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 OpsPilot :5016                    │
│  ┌──────────┬──────────────┬─────────────────┐  │
│  │ Projects │  Task Steps  │  Live Terminal  │  │
│  │ List     │  + Progress  │  + Controls     │  │
│  └──────────┴──────────────┴─────────────────┘  │
│          REST API + WebSocket                     │
└─────────────────────┬───────────────────────────┘
                      │ tmux send-keys / capture-pane
          ┌───────────┼───────────┐
          ▼           ▼           ▼
     ┌─────────┐ ┌─────────┐ ┌─────────┐
     │ tmux    │ │ tmux    │ │ tmux    │
     │ Session │ │ Session │ │ Session │
     │ proj-1  │ │ proj-2  │ │ proj-3  │
     │ Claude  │ │ Claude  │ │ Claude  │
     │ Code    │ │ Code    │ │ Code    │
     └─────────┘ └─────────┘ └─────────┘
```

## Features

- **Multi-project management** — Run multiple Claude Code agents in parallel, each in its own tmux session
- **Task step tracking** — Auto-detect `✔` completion marks and update progress in real time
- **Remote confirmation** — Detect Claude Code permission prompts and let you approve from the browser
- **Live terminal view** — See agent output in real time with auto-refresh
- **Session management** — Resume, kill, or create new Claude Code sessions per project
- **Directory picker** — Browse and select project directories visually
- **Claude Code session history** — List and resume previous Claude Code sessions

## API Reference

See [CLAUDE.md](CLAUDE.md) for the full API table.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPSPILOT_PORT` | `5016` | Web server port |
| `OPSPILOT_PROJECTS_DIR` | `~/Documents/Projects` | Default projects directory |

## License

MIT
