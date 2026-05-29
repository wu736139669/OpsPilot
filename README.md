# OpsPilot — AI Coding Agent Control Center

一个**给 AI 编程 Agent 用的任务调度中心**。人类派发开发任务，AI Agent 自动拆步骤、执行、汇报，全程可视化。

## 为什么需要 OpsPilot？

如果你在用 Claude Code / Cursor / Codex 等 AI 编程工具管理多个项目，你会遇到这些问题：

- 每个项目要手动开 tmux、手动启动 AI Agent
- AI Agent 执行到一半弹确认框，你得切到对应终端去点
- 多个项目并行开发，不知道各自进度
- 任务步骤不透明，不知道 Agent 在做什么

OpsPilot 解决的就是这些——一个 Web 控制台，同时管理多个 AI 编程 Agent。

## 快速开始

```bash
# 1. 克隆
git clone <repo-url> OpsPilot
cd OpsPilot

# 2. 安装依赖 (只需要 FastAPI)
pip3 install fastapi uvicorn websockets

# 3. 启动
python3 server.py

# 4. 打开浏览器
open http://localhost:5016
```

> 前置要求：Python 3.9+、tmux、Claude Code CLI (`claude` 命令可用)

## 使用方式

### 方式一：Web 仪表盘（推荐）

打开 `http://localhost:5016`，在 Web 界面上：
1. 点 **+ New** 创建项目
2. 用目录浏览器选择项目路径
3. 输入任务描述
4. 系统自动创建 tmux 会话、启动 Claude Code、拆步骤执行
5. 遇到确认弹窗直接在 Web 上点击确认

### 方式二：API 调用

```bash
# 创建项目
curl -X POST http://localhost:5016/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"MyProject","path":"/path/to/project"}'

# 派发任务
curl -X POST http://localhost:5016/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"project":"MyProject","title":"Build a REST API","steps":["DB schema","API routes","Tests","Deploy"]}'
```

### 方式三：让 AI Agent 自己管理

如果你在别的项目里用 Claude Code，可以让它同时管理 OpsPilot：

> 用 API 调 OpsPilot 创建新项目，然后在 tmux 里启动一个 Claude Code 实例去写代码，进度回报给 OpsPilot。

## 架构

```
┌─────────────────────────────────────────────────┐
│                 OpsPilot :5016                    │
│  ┌──────────┬──────────────┬─────────────────┐  │
│  │ Projects │  Task Steps  │  Live Terminal  │  │
│  │ 列表     │  步骤进度     │  + 确认按钮     │  │
│  └──────────┴──────────────┴─────────────────┘  │
│              REST API + WebSocket                 │
└─────────────────────┬───────────────────────────┘
                      │ tmux send-keys / capture-pane
          ┌───────────┼───────────┐
          ▼           ▼           ▼
     ┌─────────┐ ┌─────────┐ ┌─────────┐
     │ tmux    │ │ tmux    │ │ tmux    │
     │ session │ │ session │ │ session │
     │ proj-1  │ │ proj-2  │ │ proj-3  │
     │ Claude  │ │ Claude  │ │ Claude  │
     │ Code    │ │ Code    │ │ Code    │
     └─────────┘ └─────────┘ └─────────┘
```

## 配置

环境变量（可选）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPSPILOT_PORT` | `5016` | Web 服务端口 |
| `OPSPILOT_PROJECTS_DIR` | `~/Documents/Projects` | 项目默认目录 |

## License

MIT
