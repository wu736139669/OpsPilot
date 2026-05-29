# OpsPilot — AI Coding Agent Control Center

> 一个给 AI 编程 Agent 用的"任务调度中心"。人类派发任务，AI Agent 领任务、拆步骤、执行、汇报，全程可视化。

## 一键启动

```bash
pip3 install fastapi uvicorn websockets
python3 server.py
# 打开 http://localhost:5016
```

端口默认 5016，可通过 `OPSPILOT_PORT` 环境变量修改。

## 概念模型

```
人类(你)                OpsPilot(控制中心)           Claude Code(tmux里)
  │                         │                           │
  ├─ 新建项目+派发任务 ──→  │                           │
  │                         ├─ 创建 tmux session ────→  │
  │                         ├─ 发送任务指令 ──────────→  │
  │                         │                           ├─ 拆步骤
  │                         │                           ├─ 写代码
  │                         │                           ├─ 弹确认框
  │                         │  ← 检测到确认弹窗 ──────── │
  │  ← 显示确认按钮 ─────── │                           │
  ├─ 点击确认 ────────────→ │  ──→ 发送确认 ──────────→  │
  │                         │                           ├─ 继续执行
  │                         │  ← 步骤完成通知 ────────── │
  │  ← 步骤进度更新 ─────── │                           │
  │                         │                           ├─ 全部完成
```

## 给 AI Agent 的启动说明

如果你是一个 AI Coding Agent（比如 Claude Code），进入这个项目后：

1. 阅读本文件了解项目结构
2. `python3 server.py` 启动控制中心
3. 控制中心提供 Web 仪表盘 + REST API + WebSocket
4. 通过 `/api/tmux/session` 创建新的 tmux 会话并启动另一个 Claude Code 实例
5. 通过 `/api/tmux/send` 向 tmux 中的 Agent 发送指令
6. 通过 `/api/tmux/capture` 捕获 Agent 的输出
7. 通过 `/api/tasks` 管理任务和步骤进度

## 项目结构

```
OpsPilot/
├── server.py              # FastAPI 主程序 (仪表盘 + API + WebSocket)
├── frontend/
│   └── dashboard.html     # 单页 Web 仪表盘
├── config.json             # 用户配置 (可选，自动生成)
├── start.sh               # 启动脚本
├── state/                 # 运行时状态 (自动生成)
│   ├── agents.json        # Agent 注册表
│   ├── projects.json      # 项目注册表
│   └── tasks.json         # 任务和步骤
├── logs/                  # 事件日志
└── CLAUDE.md              # 本文件
```

## 核心 API

| 端点 | 方法 | 用途 |
|------|------|------|
| `/` | GET | Web 仪表盘 |
| `/ws` | WS | 实时状态推送 (每 10s) |
| `/api/state` | GET | 当前完整状态 |
| `/api/projects` | POST | 注册/更新项目 |
| `/api/agents` | POST | 注册/更新 Agent |
| `/api/tasks` | POST | 创建任务 (含步骤列表) |
| `/api/tasks/{id}/start` | POST | 启动任务 |
| `/api/tasks/{id}/steps/{n}/complete` | POST | 完成一个步骤 |
| `/api/tmux/session` | POST | 创建 tmux 会话 + 启动 Claude Code |
| `/api/tmux/send` | POST | 向 tmux 会话发送按键 |
| `/api/tmux/confirm` | POST | 发送确认 (yes/no/enter/escape) |
| `/api/tmux/capture` | POST | 捕获 tmux 窗格内容 |
| `/api/tmux/live/{session}` | GET | 获取实时终端内容 |
| `/api/fs/list` | GET | 浏览目录 (路径选择器) |

## 如何让 AI Agent 管理多个项目

1. 在仪表盘点 "+ New" 或调用 `/api/projects` 创建项目
2. 系统自动创建对应的 tmux session 并在其中启动 Claude Code
3. 通过仪表盘的终端面板或 API 向特定项目的 Agent 发送指令
4. 每个项目独立运行，互不干扰
5. 仪表盘左侧显示所有项目，点击切换查看

## 配置

可选的环境变量：
- `OPSPILOT_PORT`: Web 服务端口 (默认 5016)
- `OPSPILOT_PROJECTS_DIR`: 项目默认存放目录 (默认 ~/Documents/Projects)
