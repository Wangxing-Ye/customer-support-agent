# Customer Support Agent Version 0.10

## About

This project is a simple **customer support agent**: users can type or use the microphone, and the assistant answers using an **OpenAI** model with **RAG** from **RAGFlow** and tool calling via **LangGraph**.

<table width="100%">
  <tr>
    <td width="50%" valign="top">
      <img src="frontend/assets/Screenshot%201.png" alt="Screenshot 1" width="100%" />
    </td>
    <td width="25%" valign="top">
      <img src="frontend/assets/Screenshot%202.png" alt="Screenshot 2" width="100%" />
    </td>
    <td width="25%" valign="top">
      <img src="frontend/assets/Screenshot%203.png" alt="Screenshot 3" width="100%" />
    </td>
  </tr>
</table>

**Backend** (`backend/app.py`): FastAPI service with:

- **`POST /auth/token`** — issues a short-lived JWT for the web UI.
- **`POST /chat`** — LangGraph agent with tools (RAG retrieval, placeholder product/order/ticket helpers). The placeholder `place_order` helper now returns an order number and UTC date/time in its confirmation text. User messages are limited to **50 words**. If the first RAG retrieval is empty, the backend retries once with a **branded prefix** (`RAG_BRAND_PREFIX` + question) before injecting context.
- **LangGraph role** — orchestrates the chat workflow as a state graph: `agent` node (LLM reasoning) -> conditional `tools` node (when tool calls are requested) -> back to `agent` until completion, keeping tool-calling logic structured and extensible.
- **`POST /transcribe`** — uploads recorded audio; **OpenAI Whisper** returns text.
- **`POST /tts`** — **OpenAI speech** (MP3) for assistant replies when using the **microphone path** only (keyboard input does not trigger TTS).

**Frontend** (`frontend/`): **npm** + HTML/CSS/**vanilla ES modules** (`frontend/src/`). The current header subtitle in `frontend/index.html` is: *Simple Customer Support by OpenAI, RAGFlow and LangGraph*. **Vite** drives local development (`npm run dev`) and bundles production assets (`npm run build` → `frontend/dist`); deployed sites serve static files only. **marked** + **DOMPurify** for bot Markdown, JWT + CORS-aware API calls, mic recording via **MediaRecorder**, and typing indicators.

## Build and run locally

Complete [Installation](#installation) once: Python venv and **`pip install -r requirements.txt`**, **`cd frontend && npm install`**, and a **`.env`** in the project root with at least **`OPENAI_API_KEY`**, **`JWT_SECRET`**, and (if you override it) **`CORS_ORIGINS`** matching how you open the UI.

### Development — backend + frontend (two terminals)

**Terminal 1 — backend (FastAPI on port 8000)**

```bash
cd customer-support-agent
source venv/bin/activate          # Windows: venv\Scripts\activate
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend (Vite dev server on port 3000)**

```bash
cd customer-support-agent/frontend
npm run dev
```

Open **http://localhost:3000**. The browser loads the SPA from Vite and calls the API at **http://localhost:8000** (see **`frontend/src/config.js`**).

### Production build — backend + static frontend preview

Use this to smoke-test the same **`frontend/dist`** bundle you would deploy.

**Terminal 1 — backend** (same as above).

**Terminal 2 — build and serve the production bundle**

```bash
cd customer-support-agent/frontend
npm run build
npm run preview
```

Open **http://localhost:4173** (default **`vite preview`** port). If **`CORS_ORIGINS`** is set explicitly in **`.env`**, include **`http://localhost:4173`** (see [Environment variables](#3-environment-variables)).

## Installation

### Prerequisites

- Python **3.10+** (project uses a virtual environment).
- **Node.js** **18+** and **npm** (for `frontend/` — install, Vite dev server, and production build).
- **OpenAI API key** (chat, Whisper, TTS as configured).
- **RAGFlow** RAG system (dataset IDs and API key).
- **Docker** + **Docker Compose v2** Run RAGFlow locally via the official images (see below).

### 1. Clone and virtualenv

```bash
cd customer-support-agent
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. RAGFlow (Docker)

[RAGFlow](https://github.com/infiniflow/ragflow) provides Docker Compose definitions. Use it when you want retrieval against datasets managed in RAGFlow’s UI.

**Resource hints (typical):** CPU ≥ 4 cores, RAM ≥ 16 GB, disk ≥ ~50 GB for images/data — see the [upstream Docker README](https://github.com/infiniflow/ragflow/blob/main/docker/README.md).

**Linux — Elasticsearch needs a higher map count:**

```bash
sudo sysctl -w vm.max_map_count=262144
# Optional: persist in /etc/sysctl.conf → vm.max_map_count=262144
```

**Install and start (outline):**

```bash
git clone https://github.com/infiniflow/ragflow.git
cd ragflow/docker
# Pin a stable release, e.g. (see https://github.com/infiniflow/ragflow/releases):
git checkout -f v0.25.1
docker compose -f docker-compose.yml up -d
```

**Logs (until services are healthy):**

```bash
docker compose -f docker-compose.yml logs -f
```

**Port for this project:** this repo expects the RAGFlow HTTP API base at **`RAGFLOW_URL`** (e.g. **`http://127.0.0.1:8888`** in [production](#deployment-production)). Map the container port that serves the API to host port **8888** in `docker-compose.yml` (or your override), or set **`RAGFLOW_URL`** to whatever host/port you publish.

After RAGFlow is up, open its web UI (per upstream docs), create a **dataset / knowledge base**, note the **dataset id(s)** and **API key**, and put them in **`KNOWLEDGE_BASE_ID`** and **`RAGFLOW_API_KEY`** in this project’s `.env`.

**Retrieval tuning:** Hybrid search can be sensitive to query casing. This API lowercases and collapses whitespace for RAGFlow `question` only (see `RAGFLOW_RETRIEVAL_LOWERCASE`). An empty first hit can trigger a second retrieval with **`RAG_BRAND_PREFIX`** prepended (see **`RAG_BRAND_RETRY_SKIP_SUBSTRINGS`** to skip when the user already named related entities). You can also lower **`RAGFLOW_SIMILARITY_THRESHOLD`**, toggle **`RAGFLOW_KEYWORD`**, or make keyword search case-insensitive in RAGFlow / Elasticsearch analyzers for your dataset.

### 3. Environment variables

Create a **`.env`** file in the project root (do not commit secrets). Typical variables:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Chat, Whisper, TTS |
| `JWT_SECRET` | Strong random string for signing UI tokens |
| `CORS_ORIGINS` | Comma-separated browser `Origin` values. **Local:** include **`http://localhost:3000`** (`npm run dev`) and **`http://localhost:4173`** (`npm run preview`) if you use both; defaults in code cover common localhost ports (see `backend/app.py`). **Production:** include your site origin(s) (see [Deployment (production)](#deployment-production)). If you set this variable explicitly, list every origin you need — it replaces the defaults entirely. |
| `RAGFLOW_URL` | RAGFlow base URL (no trailing slash), e.g. `http://127.0.0.1:8888` if Docker maps API to port **8888** |
| `RAGFLOW_API_KEY` | RAGFlow API key |
| `KNOWLEDGE_BASE_ID` | Dataset UUID(s), comma-separated |
| `RAGFLOW_SIMILARITY_THRESHOLD` | Optional (default `0.2`) |
| `RAGFLOW_KEYWORD` | Optional hybrid keyword flag |
| `RAGFLOW_RETRIEVAL_LOWERCASE` | Optional (default `true`). For RAGFlow `question` only: collapse whitespace and lowercase. User chat text is unchanged. Set `false` to send the message with trim only (no lowercasing / collapse). |
| `RAG_BRAND_PREFIX` | Optional (default `ABC`). Prepended on the second retrieval query when the first returns empty. Set empty to disable branded-prefix retry. |
| `RAG_BRAND_RETRY_SKIP_SUBSTRINGS` | Optional (default ` `). Comma-separated substrings (case-insensitive): if the user message contains any of these, or contains **`RAG_BRAND_PREFIX`** as lowercase text, branded-prefix retry is skipped. Set to empty to skip only when the brand prefix appears in the message. |
| `WHISPER_MODEL` | Optional (default `whisper-1`) |
| `TTS_MODEL` | Optional (default `tts-1`) |
| `TTS_VOICE` | Optional (default `alloy`) |
| `JWT_EXPIRE_MINUTES` | Optional token lifetime |

### 4. Run the API

For running **backend and frontend together**, see [Build and run locally](#build-and-run-locally).

```bash
source venv/bin/activate
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 5. Run the frontend

For the **combined workflow** with the API, see [Build and run locally](#build-and-run-locally).

**Layout:** `frontend/index.html` loads **`frontend/src/main.js`** (ES modules). Shared images live under **`frontend/public/assets/`** (served as `/assets/…` in dev and in the built site). Runtime API URLs are set in **`frontend/src/config.js`**.

Install dependencies and start **Vite** (default dev URL **`http://localhost:3000`**):

```bash
cd frontend
npm install
npm run dev
```

Ensure **`CORS_ORIGINS`** in `.env` includes the origin you use (**`http://localhost:3000`** for dev, **`http://localhost:4173`** for `npm run preview`), unless you rely on the API’s built-in default list.

| Script | Purpose |
|--------|---------|
| `npm run dev` | Development server with hot reload (uses **Vite**). |
| `npm run build` | Production bundle → **`frontend/dist/`** (hashed JS/CSS; copies **`public/`**). |
| `npm run preview` | Serve **`frontend/dist`** locally to smoke-test the production build. |

**Production:** deploy the contents of **`frontend/dist`** behind any static host or CDN. **No Node.js is required on the server** for serving those files.

**Vite is optional** in the sense that you do not need a Node process in production — only **`npm install`** / **`npm run build`** on a machine that has Node. For **day-to-day development**, use `npm run dev` so imports like **`marked`** and **`dompurify`** resolve; the raw `frontend/src` tree is not meant to be opened without a bundler-aware dev server.

### 6. Quick check

- Page load should obtain a JWT via `POST /auth/token`.
- Typed messages hit `POST /chat` (no TTS playback).
- Mic flow: record → `POST /transcribe` → `POST /chat` → `POST /tts` and browser audio playback.

## Deployment (production)

Deploy the web app and API behind your own domain(s). A common setup is static frontend assets on HTTPS (port 443) and FastAPI on a dedicated backend port or behind a reverse proxy.

**RAGFlow** commonly runs on the **same server** as the backend (for example on **8888**). Point **`RAGFLOW_URL`** at loopback (e.g. **`http://127.0.0.1:8888`**) so retrieval stays on-machine; only expose RAGFlow beyond localhost if you intentionally need remote admin access.

### Architecture

| Piece | URL / role |
|-------|------------|
| **Web UI** | `https://<your-domain>` (default HTTPS port 443) — static assets from **`frontend/dist`** (built with `npm run build`) or equivalent |
| **API** | `https://<your-api-host>:<port>` — `POST /auth/token`, `/chat`, `/transcribe`, `/tts` |
| **RAGFlow** | `http://127.0.0.1:8888` (same host as API; HTTP to localhost — not browser-facing) |

The UI and API are **different origins** (different ports), so the browser performs **cross-origin** requests. The API must allow the page origin via **`CORS_ORIGINS`**.


## Future Plan

- **Product features** — richer tool calling, conversation history, customer profiles, and service ticketing.

## License

This project is released under the [MIT License](LICENSE).

---

## 简体中文版本 Version 0.10

### 项目简介

本项目是一个简单的 **客服智能代理**：用户可以通过键盘输入或麦克风提问，助手使用 **OpenAI** 模型回复，结合来自 **RAGFlow** 的 **RAG**（检索增强生成），并通过 **LangGraph** 实现工具调用。

**后端**（`backend/app.py`）：基于 FastAPI，主要接口包括：

- **`POST /auth/token`** —— 为 Web 前端签发短期 JWT。
- **`POST /chat`** —— 基于 LangGraph 的 Agent（含工具：RAG 检索、示例产品目录/下单/工单辅助）。其中占位的 `place_order` 会在确认文本中返回订单号与 UTC 日期时间。单条用户消息限制 **50 个词**。若首次 RAG 检索为空，后端会用 **品牌化前缀**（**`RAG_BRAND_PREFIX`** + 问题）再重试一次，然后再注入上下文。
- **LangGraph 作用** —— 作为对话流程编排器（状态图）：`agent` 节点负责模型推理，若触发工具调用则进入条件 `tools` 节点执行，再回到 `agent` 继续，直到流程结束；让工具调用逻辑更清晰、可扩展。
- **`POST /transcribe`** —— 上传录音音频；由 **OpenAI Whisper** 返回转写文本。
- **`POST /tts`** —— 使用 **OpenAI speech**（MP3）合成语音；仅在**麦克风链路**下对助手回复触发（键盘输入不会触发 TTS）。

**前端**（`frontend/`）：使用 **npm** + HTML/CSS/**原生 ES modules**（`frontend/src/`）。当前 `frontend/index.html` 的头部副标题为：*Simple Customer Support by OpenAI, RAGFlow and LangGraph*。本地开发由 **Vite** 驱动（`npm run dev`），生产构建输出（`npm run build` → `frontend/dist`）；部署时仅需静态文件。机器人 Markdown 渲染使用 **marked** + **DOMPurify**，并包含 JWT 与 CORS 感知的 API 调用、`MediaRecorder` 录音及 typing 指示。

## 本地构建与运行

先完整执行一次 [安装](#installation)：创建 Python venv 并 **`pip install -r requirements.txt`**，在 **`frontend`** 下 **`npm install`**，并在项目根目录创建 **`.env`**（至少包含 **`OPENAI_API_KEY`**、**`JWT_SECRET`**，以及你覆盖时的 **`CORS_ORIGINS`**，其值需与前端访问来源一致）。

### 开发模式 —— 后端 + 前端（两个终端）

**终端 1 —— 后端（FastAPI，端口 8000）**

```bash
cd customer-support-agent
source venv/bin/activate          # Windows: venv\Scripts\activate
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

**终端 2 —— 前端（Vite dev server，端口 3000）**

```bash
cd customer-support-agent/frontend
npm run dev
```

打开 **http://localhost:3000**。浏览器会从 Vite 加载 SPA，并调用 **http://localhost:8000** 的 API（见 **`frontend/src/config.js`**）。

### 生产构建本地验证 —— 后端 + 静态前端预览

用于冒烟测试你将部署的同一份 **`frontend/dist`** 产物。

**终端 1 —— 后端**（同上）。

**终端 2 —— 构建并启动生产包预览**

```bash
cd customer-support-agent/frontend
npm run build
npm run preview
```

打开 **http://localhost:4173**（默认 **`vite preview`** 端口）。若你在 **`.env`** 中显式设置了 **`CORS_ORIGINS`**，请确保包含 **`http://localhost:4173`**（见 [环境变量](#3-environment-variables)）。

## 安装

### 前置条件

- Python **3.10+**（项目使用虚拟环境）。
- **Node.js 18+** 与 **npm**（用于 `frontend/` 的依赖安装、Vite 开发与生产构建）。
- **OpenAI API key**（用于聊天、Whisper、TTS）。
- 使用到 RAG，需要安装并设置 **RAGFlow**（dataset ID 与 API key）。
- 本地用官方镜像运行 RAGFlow，需要 **Docker** + **Docker Compose v2**。

### 1. 克隆与虚拟环境

```bash
cd customer-support-agent
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. RAGFlow（Docker）

[RAGFlow](https://github.com/infiniflow/ragflow) 提供 Docker Compose 编排。若你希望对 RAGFlow UI 中维护的数据集做检索，可使用该方式。

**资源建议（典型）：** CPU >= 4 核、内存 >= 16 GB、磁盘约 >= 50 GB（镜像/数据）—— 参见[上游 Docker README](https://github.com/infiniflow/ragflow/blob/main/docker/README.md)。

**Linux：Elasticsearch 需要更高 map count：**

```bash
sudo sysctl -w vm.max_map_count=262144
# 可选：持久化到 /etc/sysctl.conf -> vm.max_map_count=262144
```

**安装与启动（示例流程）：**

```bash
git clone https://github.com/infiniflow/ragflow.git
cd ragflow/docker
# 固定到稳定版本，例如（查看 https://github.com/infiniflow/ragflow/releases）:
git checkout -f v0.25.1
docker compose -f docker-compose.yml up -d
```

**日志查看（直到服务健康）：**

```bash
docker compose -f docker-compose.yml logs -f
```

**本项目端口说明：** 本仓库默认期望 RAGFlow HTTP API 基址为 **`RAGFLOW_URL`**（例如生产环境中的 **`http://127.0.0.1:8888`**）。请在 `docker-compose.yml`（或覆盖文件）将提供 API 的容器端口映射到主机 **8888**，或将 **`RAGFLOW_URL`** 改为你的实际发布地址。

RAGFlow 启动后，按上游文档打开 Web UI，创建**数据集/知识库**，记录 **dataset id(s)** 与 **API key**，并填入本项目 `.env` 的 **`KNOWLEDGE_BASE_ID`** 和 **`RAGFLOW_API_KEY`**。

**检索调优：** 混合检索可能对查询大小写敏感。本 API 仅对发给 RAGFlow 的 `question` 做小写与空白归一（见 **`RAGFLOW_RETRIEVAL_LOWERCASE`**）。首次检索为空时可用 **`RAG_BRAND_PREFIX`** 做第二次检索；若用户消息已包含品牌或 **`RAG_BRAND_RETRY_SKIP_SUBSTRINGS`** 中的实体则跳过（见环境变量表）。也可调低 **`RAGFLOW_SIMILARITY_THRESHOLD`**、调整 **`RAGFLOW_KEYWORD`**，或在 RAGFlow / Elasticsearch 侧为数据集配置不区分大小写的分析器。

### 3. 环境变量

在项目根目录创建 **`.env`**（不要提交密钥）。常见变量如下：

| 变量 | 用途 |
|------|------|
| `OPENAI_API_KEY` | 聊天、Whisper、TTS |
| `JWT_SECRET` | 用于签名前端令牌的高强度随机字符串 |
| `CORS_ORIGINS` | 浏览器 `Origin` 列表（逗号分隔）。**本地：** 若同时使用 `npm run dev` 与 `npm run preview`，请包含 **`http://localhost:3000`** 与 **`http://localhost:4173`**；代码中也提供常见 localhost 端口默认值（见 `backend/app.py`）。**生产：** 请包含你的站点来源（见 [生产部署](#deployment-production)）。若你显式设置该变量，它会完全覆盖默认值。 |
| `RAGFLOW_URL` | RAGFlow 基础 URL（不带尾斜杠），例如 Docker 将 API 映射到 **8888** 时为 `http://127.0.0.1:8888` |
| `RAGFLOW_API_KEY` | RAGFlow API 密钥 |
| `KNOWLEDGE_BASE_ID` | 数据集 UUID（多个用逗号分隔） |
| `RAGFLOW_SIMILARITY_THRESHOLD` | 可选（默认 `0.2`） |
| `RAGFLOW_KEYWORD` | 可选，混合关键词检索开关 |
| `RAGFLOW_RETRIEVAL_LOWERCASE` | 可选（默认 `true`）。仅对 RAGFlow 检索查询：折叠空白并小写；用户聊天原文不变。设为 `false` 则仅首尾 trim，不做小写与折叠。 |
| `RAG_BRAND_PREFIX` | 可选（默认 `ABC`）。首次检索为空时，第二次检索在问题前附加此前缀。留空则关闭品牌化前缀重试。 |
| `RAG_BRAND_RETRY_SKIP_SUBSTRINGS` | 可选（默认 ` `）。逗号分隔子串（不区分大小写）：用户消息若包含任一则跳过品牌化前缀重试；若消息已包含 **`RAG_BRAND_PREFIX`** 的小写形式也会跳过。留空则仅在消息含品牌前缀时跳过。 |
| `WHISPER_MODEL` | 可选（默认 `whisper-1`） |
| `TTS_MODEL` | 可选（默认 `tts-1`） |
| `TTS_VOICE` | 可选（默认 `alloy`） |
| `JWT_EXPIRE_MINUTES` | 可选，令牌有效期（分钟） |

### 4. 运行 API

如需**后端与前端联调**，见 [本地构建与运行](#build-and-run-locally)。

```bash
source venv/bin/activate
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 5. 运行前端

如需与 API 一起跑完整流程，见 [本地构建与运行](#build-and-run-locally)。

**目录关系：** `frontend/index.html` 加载 **`frontend/src/main.js`**（ES modules）。公共图片位于 **`frontend/public/assets/`**（开发与构建后均以 `/assets/...` 访问）。运行时 API URL 在 **`frontend/src/config.js`** 中解析。

安装依赖并启动 **Vite**（默认开发地址 **`http://localhost:3000`**）：

```bash
cd frontend
npm install
npm run dev
```

确保 `.env` 中 **`CORS_ORIGINS`** 包含你实际使用的前端来源（开发 `http://localhost:3000`，预览 `http://localhost:4173`），除非你依赖 API 内置默认来源列表。

| 脚本 | 用途 |
|------|------|
| `npm run dev` | 开发服务器 + 热更新（Vite） |
| `npm run build` | 生产构建输出到 **`frontend/dist/`**（哈希 JS/CSS，并复制 **`public/`**） |
| `npm run preview` | 本地服务 **`frontend/dist`**，用于生产包冒烟测试 |

**生产环境：** 将 **`frontend/dist`** 内容部署到任意静态主机或 CDN。**服务器端不需要 Node.js 进程**来提供这些静态文件。

这里说 **Vite 可选**，指的是生产环境不需要常驻 Node 进程；你只需要在有 Node 的机器执行 **`npm install`** / **`npm run build`**。但**日常开发**仍建议使用 `npm run dev`，这样像 **`marked`**、**`dompurify`** 这类依赖才能正确解析；`frontend/src` 原始目录并不面向无打包器直接打开。

### 6. 快速自检

- 页面加载后应通过 `POST /auth/token` 获取 JWT。
- 键盘输入消息走 `POST /chat`（不播放 TTS）。
- 麦克风链路：录音 -> `POST /transcribe` -> `POST /chat` -> `POST /tts`，最后浏览器播放音频。

## 生产部署

请按你的域名和网络拓扑部署前后端。常见方式是：前端静态资源通过 HTTPS（443）对外服务，FastAPI 后端放在独立端口或反向代理后。

**RAGFlow** 常见部署方式是与后端在**同一台服务器**（例如 **8888** 端口）。建议将 **`RAGFLOW_URL`** 指向本机回环（如 **`http://127.0.0.1:8888`**）以保证检索留在本机；仅在确有远程管理需求时对外暴露 RAGFlow。

### 架构

| 组件 | URL / 角色 |
|------|------------|
| **Web UI** | `https://<your-domain>`（默认 HTTPS 443）—— 提供 **`frontend/dist`** 静态资源（或等效产物） |
| **API** | `https://<your-api-host>:<port>` —— `POST /auth/token`、`/chat`、`/transcribe`、`/tts` |
| **RAGFlow** | `http://127.0.0.1:8888`（与 API 同机；仅本机 HTTP，不面向浏览器） |

UI 与 API 属于**不同 Origin**（端口不同），浏览器会发起跨域请求。API 必须通过 **`CORS_ORIGINS`** 放行页面来源。


## 未来计划

- **产品能力** —— 丰富工具调用、会话历史、客户资料以及服务工单等功能。

## 许可证

本项目使用 [MIT License](LICENSE) 开源发布。
