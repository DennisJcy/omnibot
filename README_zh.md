<div align="center">

# 🤖 Omnibot

### 面向 AI Agent 的浏览器基础设施

[![Version](https://img.shields.io/badge/version-1.6.21-blue?style=flat-square)](https://github.com/DennisJcy/omnibot/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![npm](https://img.shields.io/badge/npm-%40omniaibot%2Fomnibot-CB3837?style=flat-square&logo=npm&logoColor=white)](https://www.npmjs.com/package/@omniaibot/omnibot)

[![SkillHub](https://img.shields.io/badge/SkillHub-omnibot-00A8E0?style=flat-square&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNOCAwTDAgNFYxMkw4IDE2TDE2IDEyVjRMOCAwWiIgZmlsbD0id2hpdGUiLz48L3N2Zz4=)](https://skillhub.cn/skills/omnibot)
[![ClawHub](https://img.shields.io/badge/ClawHub-omnibot--skills-FF6B35?style=flat-square&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNOCAxQzQuMTMgMSAxIDQuMTMgMSA4QzEgMTEuODcgNC4xMyAxNSA4IDE1QzExLjg3IDE1IDE1IDExLjg3IDE1IDhDMTUgNC4xMyAxMS44NyAxIDggMVpNOCAzQzkuNjYgMyAxMSA0LjM0IDExIDZDMTEgNy42NiA5LjY2IDkgOCA5QzYuMzQgOSA1IDcuNjYgNSA2QzUgNC4zNCA2LjM0IDMgOCAzWiIgZmlsbD0id2hpdGUiLz48L3N2Zz4=)](https://clawhub.ai/dennisjcy/skills/omnibot-skills)

[![Chrome Web Store](https://img.shields.io/badge/Chrome%20Web%20Store-Browser%20Extension-4285F4?style=flat-square&logo=google-chrome&logoColor=white)](https://chromewebstore.google.com/detail/fojlpefamkmjbboafmjkkaejohagbdgn)

**让 AI Agent 连接真实的 Chromium 浏览器。**<br>
读页面、点按钮、填表单、导航、提取内容、收集证据。<br>
全部通过本地 daemon 和 CLI 完成 —— 无 headless 黑科技，无脆弱的选择器。

[快速开始](#-快速开始) · [工作原理](#-工作原理) · [功能特性](#-功能特性) · [开发](#-开发) · [文档](#-文档) · [赞助](#-赞助)

🌐 **[English](./README.md)**

</div>

---

## 💎 赞助

<div align="center">

[![ShareLLM](https://img.shields.io/badge/Sponsored%20by-ShareLLM-7C3AED?style=for-the-badge&labelColor=0F0F1A)](https://www.sharellm.net/)

感谢 [**ShareLLM**](https://www.sharellm.net/) 赞助本项目！

ShareLLM 是一个"真实 AI 模型，验证后共享"的平台 —— 你可以分享自己闲置的 AI 额度，也可以折扣使用经过验证的模型。每个模型都会做真实性校验，杜绝"缩水版"模型。

</div>

## 🚀 Omnibot 是什么？

Omnibot 在 AI Agent 与真实网页之间架起桥梁，让 **Hermes**、**Claude Code**、**Codex**、**OpenCode** 等 agent 像人类一样查看并操作一个真实运行的 Chromium 浏览器。

```
┌──────────────┐         ┌──────────────┐         ┌──────────────────┐
│   AI Agent   │ ──CLI──▶│  Omnibot     │ ──WS──▶ │  Chromium        │
│  (Hermes,    │         │  Daemon      │         │  Extension       │
│   Claude...) │         │  :18765      │         │  (Real Browser)  │
└──────────────┘         └──────────────┘         └──────────────────┘
```

没有 Puppeteer，没有 Playwright，没有假装真实的 headless 浏览器。<br>
**真实浏览器、真实 Cookie、真实扩展、真实用户会话。**

## 🎬 实际效果演示

<table>
<tr>
<td width="50%" align="center" valign="top">

### 微信公众号数据分析
**Hermes 自动分析公众号后台数据与趋势**

[![WeChat Analytics](https://img.youtube.com/vi/xZ-_0TInCRE/maxresdefault.jpg)](https://youtu.be/xZ-_0TInCRE)

*Hermes 自动登录公众号后台，提取用户增长、文章阅读量、用户画像等数据，生成完整的数据分析报告。*

</td>
<td width="50%" align="center" valign="top">

### X（Twitter）AI 资讯聚合
**Hermes 自动浏览 X 获取最新 AI 资讯**

[![X AI News](https://img.youtube.com/vi/PknnOhAE6bI/maxresdefault.jpg)](https://youtu.be/PknnOhAE6bI)

*Hermes 自动浏览 X（Twitter），搜索并筛选最新 AI 资讯，整理成结构化新闻简报。*

</td>
</tr>
<tr>
<td width="50%" align="center" valign="top">

### 裁判文书分析
**Hermes 检索并分析命案判决书**

[![Court Analysis](https://img.youtube.com/vi/PQQNDbzgXgQ/maxresdefault.jpg)](https://youtu.be/PQQNDbzgXgQ)

*Hermes 检索命案裁判文书，通读 8 份完整案卷，生成包含犯罪人画像、作案动机与犯罪模式分析的综合报告。*

</td>
<td width="50%" align="center" valign="top">

### 头条自动发文
**Hermes 向今日头条发布文章**

[![Toutiao Publishing](https://img.youtube.com/vi/elUxHLp1C4Q/maxresdefault.jpg)](https://youtu.be/elUxHLp1C4Q)

*Hermes 自动登录头条，填写标题与正文、插入图片、设置封面与广告分成，预览后一键发布。*

</td>
</tr>
</table>

<div align="center">

**更多使用场景等你探索！**

</div>

## ✨ 功能特性

<table>
<tr>
<td width="50%" valign="top">

### 🔍 观察
- 将渲染后的页面内容读取为干净的文本 / Markdown
- 抓取完整可访问性树快照，带交互引用
- 截取整页或指定视觉区域的截图
- 查看控制台日志、网络流量和 DOM 状态

</td>
<td width="50%" valign="top">

### 🎯 操作
- 按语义角色、占位符或可访问性引用点击元素
- 填写表单、选择选项、勾选复选框 —— 带事件派发
- 页面间导航，管理标签页与标签页分组
- 拖拽、滚动、输入、按键 —— 类人交互

</td>
</tr>
<tr>
<td width="50%" valign="top">

### ✅ 验证
- 等待条件成立：URL 变化、元素可见、文本出现
- 断言元素状态：可用、可见、选中、取值
- 采集网络日志与 API 证据
- 观察 → 操作 → 验证 的多步闭环

</td>
<td width="50%" valign="top">

### 🛡️ 可靠
- 会话令牌工作流隔离
- 标签页级命令定位 —— 杜绝跨标签页误操作
- 从语义层到原始 CDP 的 7 级回退链
- 内置反模式防护与安全规则

</td>
</tr>
</table>

## ⚡ 快速开始

### 1. 安装 CLI

通过 npm 全局安装（推荐）：

```bash
npm install -g @omniaibot/omnibot
```

自动检测平台并安装对应二进制。安装后运行 `omnibot doctor` 验证。

### 2. 加载浏览器扩展

- 打开 [Chrome Web Store 上的 Omnibot 扩展页面](https://chromewebstore.google.com/detail/fojlpefamkmjbboafmjkkaejohagbdgn)
- 点击**添加到 Chrome** 完成安装
- 点击浏览器右上角的 Omnibot 扩展图标
- 确认扩展显示 **Connected**

默认情况下，扩展连接本地 WebSocket 服务 `127.0.0.1:18765`。

扩展弹窗设置：
- **WebSocket 地址**：`ws://127.0.0.1:18765`
- 连接状态自动刷新
- 连接失败时先运行 `omnibot doctor` 检查 daemon 状态

### 3. 检查连接

无需手动启动 daemon。运行任意浏览器命令时，omnibot CLI 会自动启动本地 daemon，浏览器扩展会通过 WebSocket 连接到 `127.0.0.1:18765`。

```bash
omnibot doctor
omnibot tabs
```

`doctor` 检查 daemon 与扩展的健康状态，`tabs` 列出可用的浏览器标签页。

如果 `doctor` 显示扩展未连接，请打开 Chrome/Edge，加载或重新加载浏览器扩展，并保持至少一个 HTTP/HTTPS 标签页打开。

### 4. 安装 Agent Skills

omnibot v2 使用 skill 而非 MCP prompt 注入：

```bash
omnibot skills install --agent hermes --profile nuwa
omnibot skills install --agent opencode
omnibot skills install --agent claude
omnibot skills install --agent codex
```

查看内置 skills 路径：

```bash
omnibot skills path
```

omnibot 为常见 AI agent 内置了 skill 配置，按 agent 选择安装命令即可。

skill 文件在独立的开源仓库 [**DennisJcy/Omnibot-skills**](https://github.com/DennisJcy/Omnibot-skills) 中维护 —— 它是 Omnibot skill 在所有 agent 上的唯一发布源。

### 5. 上手体验

```bash
omnibot snapshot -i                                   # 可访问性树，带 @eN 引用
omnibot read --screens 5 https://example.com          # 页面的干净 Markdown
omnibot navigate 'https://example.com'
omnibot execute-js "return document.title"
omnibot wait "return document.readyState === 'complete'" --timeout 10
omnibot screenshot -o /tmp/omnibot.png
```

## 🔄 工作原理

每个浏览器操作都遵循一个严格的闭环：

```
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │ Observe  │ ───▶ │   Act    │ ───▶ │  Verify  │──┐
  │          │      │  (once)  │      │          │  │
  └──────────┘      └──────────┘      └──────────┘  │
       ▲                                              │
       └──────────── retry with fallback ─────────────┘
```

1. **观察** — 快照页面、读取内容、检查当前状态
2. **操作** — 用最优模式执行一次操作
3. **验证** — 用证据确认期望的状态变化

验证失败时，agent 重新观察并尝试下一级回退。不盲目重试，不猜测。

## 🧩 原生命令路由

omnibot 始终为任务选择最精准的原生命令：

| 意图 | 原生命令 | 不要用 |
|--------|---------------|----------|
| 读取页面内容 | `read`、`get text` | ~~`execute-js`~~ |
| 点击按钮 | `find --action click`、`click @eN` | ~~`querySelector().click()`~~ |
| 填写表单 | `fill`、`type` | ~~`element.value = "..."`~~ |
| 等待状态 | `wait` | ~~`sleep 3`~~ |
| 滚动 | `scroll`、`scrollintoview` | ~~`window.scrollTo()`~~ |

**原生优先，JavaScript 只是回退手段，不是捷径。**

## 🏗️ 架构

```
Agent Skill (SKILL.md)
    │
    ▼
omnibot CLI  ──────────────────────────────┐
    │                                       │
    ▼                                       ▼
Local Daemon (:18765)              Chromium Extension
    │                                       │
    ├── Session management                  ├── DOM access
    ├── Command routing                     ├── Accessibility tree
    ├── Tab tracking                        ├── Network interception
    └── Workflow isolation                  └── Visual region detection
```

**核心设计原则：**
- **可靠性 > 便利性** — 每个操作都会被验证
- **显式状态 > 隐式状态** — 不做隐藏假设
- **模式 > 命令** — 从任务出发，而不是从 API 出发
- **回退可用，但绝不优先**

## 🛠️ 开发

### 使用 uv 从源码运行

[uv](https://docs.astral.sh/uv/) 管理 Python 项目：

```bash
uv sync
uv run omnibot --help
uv run omnibot start
uv run omnibot skills install --agent opencode
```

要从**当前源码**启动 daemon（而不是全局安装的打包二进制），先停止现有 daemon，再显式启动：

```bash
uv run omnibot stop
uv run python -m omnibot --api-port 18764 --ws-port 18765 daemon run
```

> **注意**：全局 npm 安装的 daemon 可能会遮蔽源码。测试新 action 前，请用 `ps` 确认监听 `18764` 的进程是源码 daemon。

### 仓库结构

| 路径 | 说明 |
| --- | --- |
| `src/omnibot/cli.py` | CLI 命令树（daemon、tabs、snapshot、read、click 等） |
| `src/omnibot/daemon.py` | 本地 daemon：保持浏览器会话与动作调度 |
| `src/omnibot/actions.py` | 可复用浏览器动作（snapshot、read、execute-js、batch、wait 等） |
| `src/omnibot/TMWebDriver.py` | 核心桥接层：WebSocket（`:18765`）/ HTTP 长轮询（`:18766`）会话 |
| `src/omnibot/simphtml.py` | 浏览器内 HTML 优化，产出 LLM 友好内容 |
| `src/omnibot/skills/` | 内置 agent skills（`omnibot/SKILL.md`） |
| `browser-extension/` | Chromium 扩展（background、content、popup） |
| `build_ext.py` | 扩展打包脚本 |

### 构建浏览器扩展

开发时直接加载未打包的扩展：

1. 在 Chrome 或其他 Chromium 浏览器中打开 `chrome://extensions/`
2. 开启**开发者模式**
3. 点击**加载已解压的扩展程序**，选择 `browser-extension/` 文件夹

构建可分发扩展包（输出到 `dist/omnibot/`）：

```bash
python3 build_ext.py
```

### 编译独立可执行文件

发布用二进制由 Nuitka 编译（`--mode=standalone`，每个平台约 80–90 MB），由 **GitHub Actions 流水线**（`.github/workflows/build-release.yml`）在原生 runner 上构建——无交叉编译，无远程构建机：

| 平台 | Runner | 构建方式 |
| --- | --- | --- |
| Linux x64 | `ubuntu-latest` | Nuitka 原生编译 |
| macOS ARM64 | `macos-latest`（Apple Silicon） | Nuitka 原生编译 |
| Windows x64 | `windows-latest`（自带 MSVC） | Nuitka 原生编译 |
| 浏览器扩展 | `ubuntu-latest` | `build_ext.py` |

推送 `v*` tag 后自动构建全平台并发布 GitHub Release、npm 包和（若配置）Edge Add-ons Store 提交。

完整 Nuitka 流水线与归一化步骤见 [`doc/build.md`](./doc/build.md)。

### 测试

```bash
# 单元测试（无需浏览器连接）
uv run python -m pytest tests/unit -q

# 发版前测试（单元 + feature matrix + full workflow）
python3 tests/release/preflight.py
```

### 发布

发布完全由 GitHub Actions 流水线（`.github/workflows/build-release.yml`）自动化：推送 `v<major>.<minor>.<patch>` tag 后，流水线自动构建全平台、创建 GitHub Release、发布 npm 包（`@omniaibot/omnibot`、`@omniaibot/linux-x64`、`@omniaibot/macos-arm64`、`@omniaibot/win-x64`），并在配置了 `EDGE_API_KEY` 时发布 Edge Add-ons Store。版本号必须在全部 8 个位置保持一致（`pyproject.toml`、`cli.py` 的 fallback 版本、三个平台 `package.json`、`npm-packages/cli/package.json` 及其 `optionalDependencies`、`browser-extension/manifest.json`）。

## 📚 文档

| 资源 | 说明 |
|----------|-------------|
| [DennisJcy/Omnibot-skills](https://github.com/DennisJcy/Omnibot-skills) | Omnibot agent skill 开源仓库：SKILL.md、命令参考、操作模式 |
| [doc/build.md](./doc/build.md) | 编译构建指南：Nuitka、Docker、各平台脚本 |
| [docs/product-overview.md](./docs/product-overview.md) | 产品概览与设计 |
| [docs/product-roadmap.md](./docs/product-roadmap.md) | 功能路线图与状态 |
| [AGENTS.md](./AGENTS.md) | 开发者约定、命令与发版检查清单 |
| [src/omnibot/skills/omnibot/SKILL.md](./src/omnibot/skills/omnibot/SKILL.md) | Agent 执行规范（omnibot skill） |

## 🤝 兼容的 Agent

omnibot 兼容任何能执行 CLI 命令的 agent 系统：

- 🧠 **Hermes** — 原生集成
- 🟠 **Claude Code** — 通过 skill 文件
- 📦 **Codex** — 通过 skill 文件
- 🔓 **OpenCode** — 通过 skill 文件
- 🔧 **任意支持 CLI 的 agent** — 通过 `omnibot` 命令

## 📋 示例工作流

```bash
# 设置工作流上下文
export OMNIBOT_SESSION_TOKEN=research

# 打开新标签页
omnibot open "https://github.com"

# 抓取带交互引用的页面快照
omnibot snapshot -i --tab-id $TAB_ID

# 点击搜索框并输入
omnibot find placeholder "Search GitHub" --action type \
  --action-value "omnibot" --tab-id $TAB_ID

# 按回车
omnibot press Enter --tab-id $TAB_ID

# 等待结果出现
omnibot wait --text "repositories" --tab-id $TAB_ID

# 读取结果
omnibot read --tab-id $TAB_ID
```

## 📄 许可证

MIT。详见 [LICENSE](./LICENSE)。

---

<div align="center">

**为需要看见网页的 Agent 而生 —— 不只是抓取它。**

[⭐ Star on GitHub](https://github.com/DennisJcy/omnibot) · [📖 阅读 Skill 规范](./src/omnibot/skills/omnibot/SKILL.md)

</div>
