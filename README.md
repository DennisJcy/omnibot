<div align="center">

# 🤖 Omnibot

### Browser Infrastructure for AI Agents

[![Version](https://img.shields.io/badge/version-1.6.21-blue?style=flat-square)](https://github.com/DennisJcy/omnibot/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![npm](https://img.shields.io/badge/npm-%40omniaibot%2Fomnibot-CB3837?style=flat-square&logo=npm&logoColor=white)](https://www.npmjs.com/package/@omniaibot/omnibot)

[![SkillHub](https://img.shields.io/badge/SkillHub-omnibot-00A8E0?style=flat-square&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNOCAwTDAgNFYxMkw4IDE2TDE2IDEyVjRMOCAwWiIgZmlsbD0id2hpdGUiLz48L3N2Zz4=)](https://skillhub.cn/skills/omnibot)
[![ClawHub](https://img.shields.io/badge/ClawHub-omnibot--skills-FF6B35?style=flat-square&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNOCAxQzQuMTMgMSAxIDQuMTMgMSA4QzEgMTEuODcgNC4xMyAxNSA4IDE1QzExLjg3IDE1IDE1IDExLjg3IDE1IDhDMTUgNC4xMyAxMS44NyAxIDggMVpNOCAzQzkuNjYgMyAxMSA0LjM0IDExIDZDMTEgNy42NiA5LjY2IDkgOCA5QzYuMzQgOSA1IDcuNjYgNSA2QzUgNC4zNCA2LjM0IDMgOCAzWiIgZmlsbD0id2hpdGUiLz48L3N2Zz4=)](https://clawhub.ai/dennisjcy/skills/omnibot-skills)

[![Chrome Web Store](https://img.shields.io/badge/Chrome%20Web%20Store-Browser%20Extension-4285F4?style=flat-square&logo=google-chrome&logoColor=white)](https://chromewebstore.google.com/detail/fojlpefamkmjbboafmjkkaejohagbdgn)

**Connect AI agents to a real Chromium browser.**<br>
Read pages. Click buttons. Fill forms. Navigate. Extract content. Collect evidence.<br>
All through a local daemon and CLI — no headless hacks, no fragile selectors.

[Getting Started](#-quick-start) · [How It Works](#-how-it-works) · [Features](#-features) · [Development](#-development) · [Documentation](#-documentation) · [Sponsor](#-sponsor)

🌐 **[中文](./README_zh.md)**

</div>

---

## 💎 Sponsor

<div align="center">

[![ShareLLM](https://img.shields.io/badge/Sponsored%20by-ShareLLM-7C3AED?style=for-the-badge&labelColor=0F0F1A)](https://www.sharellm.net/)

Thanks to [**ShareLLM**](https://www.sharellm.net/) for sponsoring this project!

ShareLLM is a platform for **authentic AI models, verified & shared** — share your unused AI quota, or access verified models at a discount. Every model is checked for authenticity, so you never get watered-down outputs.

</div>

## 🚀 What Is Omnibot?

Omnibot bridges the gap between AI agents and the real web. It gives agents like **Hermes**, **Claude Code**, **Codex**, **OpenCode**, and others the ability to see and interact with a live Chromium browser — the same way a human does.

```
┌──────────────┐         ┌──────────────┐         ┌──────────────────┐
│   AI Agent   │ ──CLI──▶│  Omnibot     │ ──WS──▶ │  Chromium        │
│  (Hermes,    │         │  Daemon      │         │  Extension       │
│   Claude...) │         │  :18765      │         │  (Real Browser)  │
└──────────────┘         └──────────────┘         └──────────────────┘
```

No Puppeteer. No Playwright. No headless browser pretending to be real.<br>
**A real browser. Real cookies. Real extensions. Real user sessions.**

## 🎬 See It In Action

<table>
<tr>
<td width="50%" align="center" valign="top">

### WeChat Official Account Analytics
**Hermes auto-analyzes WeChat backend data & trends**

[![WeChat Analytics](https://img.youtube.com/vi/xZ-_0TInCRE/maxresdefault.jpg)](https://youtu.be/xZ-_0TInCRE)

*Hermes agent auto-logs into WeChat Official Account backend, extracts user growth, article reads, user demographics, and generates a complete data analysis report.*

</td>
<td width="50%" align="center" valign="top">

### X (Twitter) AI News Aggregator
**Hermes auto-browses X for latest AI news**

[![X AI News](https://img.youtube.com/vi/PknnOhAE6bI/maxresdefault.jpg)](https://youtu.be/PknnOhAE6bI)

*Hermes agent auto-browses X (Twitter), searches and filters the latest AI news, and organizes it into a structured news briefing.*

</td>
</tr>
<tr>
<td width="50%" align="center" valign="top">

### Court Document Analysis
**Hermes searches & analyzes homicide verdicts**

[![Court Analysis](https://img.youtube.com/vi/PQQNDbzgXgQ/maxresdefault.jpg)](https://youtu.be/PQQNDbzgXgQ)

*Hermes agent searches court records for homicide cases, reads 8 full case files, and generates a comprehensive analysis report including offender profiles, motive analysis, and crime patterns.*

</td>
<td width="50%" align="center" valign="top">

### Toutiao Auto-Publishing
**Hermes publishes articles to Toutiao**

[![Toutiao Publishing](https://img.youtube.com/vi/elUxHLp1C4Q/maxresdefault.jpg)](https://youtu.be/elUxHLp1C4Q)

*Hermes agent auto-logs into Toutiao, fills in title, body text, inserts images, sets cover and ad revenue, previews and publishes the article with one click.*

</td>
</tr>
</table>

<div align="center">

**More use cases waiting for you to explore!**

</div>

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🔍 Observe
- Read rendered page content as clean text/Markdown
- Snapshot the full accessibility tree with interactive refs
- Capture screenshots of full pages or specific visual regions
- Inspect console logs, network traffic, and DOM state

</td>
<td width="50%" valign="top">

### 🎯 Act
- Click elements by semantic role, placeholder, or accessibility ref
- Fill forms, select options, check boxes — with event dispatch
- Navigate between pages, manage tabs and tab groups
- Drag, scroll, type, press keys — human-like interaction

</td>
</tr>
<tr>
<td width="50%" valign="top">

### ✅ Verify
- Wait for conditions: URL changes, element visibility, text appearance
- Assert element state: enabled, visible, checked, value
- Capture network logs and API evidence
- Multi-step verification with observe → act → verify loops

</td>
<td width="50%" valign="top">

### 🛡️ Reliable
- Session-token workflow isolation
- Tab-targeted commands — no accidental cross-tab mutations
- 7-tier fallback chain from semantic to raw CDP
- Built-in anti-pattern guards and safety rules

</td>
</tr>
</table>

## ⚡ Quick Start

### 1. Install the CLI

Install Omnibot CLI globally via npm (recommended):

```bash
npm install -g @omniaibot/omnibot
```

It auto-detects your platform and installs the corresponding binary. After installation, run `omnibot doctor` to verify.

### 2. Load the Browser Extension

- Open the [Omnibot extension page on Chrome Web Store](https://chromewebstore.google.com/detail/fojlpefamkmjbboafmjkkaejohagbdgn)
- Click **Add to Chrome** and complete the installation
- Click the Omnibot extension icon in the top-right corner of your browser
- Confirm the extension shows **Connected**

By default, the extension connects to the local WebSocket service at `127.0.0.1:18765`.

Extension popup settings:
- **WebSocket Address**: `ws://127.0.0.1:18765`
- Connection status auto-refreshes
- If connection fails, run `omnibot doctor` first to check daemon status

### 3. Verify the Connection

No need to manually start the daemon. Running any browser command will auto-start the local daemon, and the browser extension will connect via WebSocket to `127.0.0.1:18765`.

```bash
omnibot doctor
omnibot tabs
```

`doctor` checks daemon and extension health. `tabs` lists available browser tabs.

If `doctor` shows the extension is not connected, open Chrome/Edge, load or reload the browser extension, and keep at least one HTTP/HTTPS tab open.

### 4. Install Agent Skills

Omnibot v2 uses skills instead of MCP prompt injection:

```bash
omnibot skills install --agent hermes --profile nuwa
omnibot skills install --agent opencode
omnibot skills install --agent claude
omnibot skills install --agent codex
```

View built-in skill paths:

```bash
omnibot skills path
```

Omnibot comes with built-in skill configurations for popular AI agents. Select your agent from the quick start page to get the install command.

The skill files are maintained in the dedicated open-source repo [**DennisJcy/Omnibot-skills**](https://github.com/DennisJcy/Omnibot-skills) — the single source of truth for the Omnibot skill across all agents.

### 5. Try It

```bash
omnibot snapshot -i                                   # accessibility tree with @eN refs
omnibot read --screens 5 https://example.com          # clean Markdown of the page
omnibot navigate 'https://example.com'
omnibot execute-js "return document.title"
omnibot wait "return document.readyState === 'complete'" --timeout 10
omnibot screenshot -o /tmp/omnibot.png
```

## 🔄 How It Works

Every browser operation follows a disciplined loop:

```
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │ Observe  │ ───▶ │   Act    │ ───▶ │  Verify  │──┐
  │          │      │  (once)  │      │          │  │
  └──────────┘      └──────────┘      └──────────┘  │
       ▲                                              │
       └──────────── retry with fallback ─────────────┘
```

1. **Observe** — snapshot the page, read content, check current state
2. **Act** — perform one operation using the best available pattern
3. **Verify** — confirm the expected state change with evidence

If verification fails, the agent re-observes and tries the next fallback tier. No blind retries. No guessing.

## 🧩 Native Command Router

Omnibot always picks the narrowest native command for the job:

| Intent | Native Command | Not This |
|--------|---------------|----------|
| Read page content | `read`, `get text` | ~~`execute-js`~~ |
| Click a button | `find --action click`, `click @eN` | ~~`querySelector().click()`~~ |
| Fill a form | `fill`, `type` | ~~`element.value = "..."`~~ |
| Wait for state | `wait` | ~~`sleep 3`~~ |
| Scroll | `scroll`, `scrollintoview` | ~~`window.scrollTo()`~~ |

**Native first. JavaScript is a fallback, not a shortcut.**

## 🏗️ Architecture

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

**Key design principles:**
- **Reliability > Convenience** — every action is verified
- **Explicit State > Implicit State** — no hidden assumptions
- **Pattern > Command** — start from the task, not the API
- **Fallback is allowed, but never first**

## 🛠️ Development

### Run From Source With uv

[uv](https://docs.astral.sh/uv/) manages the Python project:

```bash
uv sync
uv run omnibot --help
uv run omnibot start
uv run omnibot skills install --agent opencode
```

To run the daemon from the current source (instead of a globally installed packaged binary), stop any existing daemon first, then start it explicitly:

```bash
uv run omnibot stop
uv run python -m omnibot --api-port 18764 --ws-port 18765 daemon run
```

> **Note**: A globally installed npm daemon may shadow the source code. Always verify with `ps` that the process listening on `18764` is the source daemon before testing new actions.

### Repository Layout

| Path | Description |
| --- | --- |
| `src/omnibot/cli.py` | CLI command tree (daemon, tabs, snapshot, read, click, …) |
| `src/omnibot/daemon.py` | Local daemon: keeps the browser session and schedules actions |
| `src/omnibot/actions.py` | Reusable browser actions (snapshot, read, execute-js, batch, wait, …) |
| `src/omnibot/TMWebDriver.py` | Core bridge: WebSocket (`:18765`) / HTTP long-poll (`:18766`) sessions |
| `src/omnibot/simphtml.py` | In-browser HTML optimization for LLM-friendly output |
| `src/omnibot/skills/` | Built-in agent skills (`omnibot/SKILL.md`) |
| `browser-extension/` | Chromium extension (background, content, popup) |
| `build_ext.py` | Extension packager for distribution |

### Build the Browser Extension

For development, load the unpacked extension:

1. Open `chrome://extensions/` in Chrome or any Chromium browser
2. Enable **Developer mode**
3. Click **Load unpacked** and select the `browser-extension/` folder

To build the distributable extension (output to `dist/omnibot/`):

```bash
python3 build_ext.py
```

### Build Standalone Binaries

The published binaries are compiled with Nuitka (`--mode=standalone`, ~80–90 MB per platform) by the **GitHub Actions pipeline** (`.github/workflows/build-release.yml`) on native runners — no cross-compilation, no remote build machine:

| Platform | Runner | Build |
| --- | --- | --- |
| Linux x64 | `ubuntu-latest` | Nuitka native compile |
| macOS ARM64 | `macos-latest` (Apple Silicon) | Nuitka native compile |
| Windows x64 | `windows-latest` (MSVC preinstalled) | Nuitka native compile |
| Browser extension | `ubuntu-latest` | `build_ext.py` |

Pushing a `v*` tag automatically builds all platforms and publishes the GitHub Release, npm packages, and (if configured) the Edge Add-ons Store submission.

Build docs: see [`doc/build.md`](./doc/build.md) for the full Nuitka pipeline and normalization steps.

### Tests

```bash
# Unit tests (no browser needed)
uv run python -m pytest tests/unit -q

# Pre-release gate (unit + feature matrix + full workflow)
python3 tests/release/preflight.py
```

### Release

Releases are fully automated by the GitHub Actions pipeline (`.github/workflows/build-release.yml`): push a `v<major>.<minor>.<patch>` tag, and the pipeline builds all platforms, creates the GitHub Release, and publishes the npm packages (`@omniaibot/omnibot`, `@omniaibot/linux-x64`, `@omniaibot/macos-arm64`, `@omniaibot/win-x64`) plus the Edge Add-ons Store release when `EDGE_API_KEY` is configured. The version must be synced across all 8 locations (`pyproject.toml`, `cli.py` fallback, three platform `package.json` files, `npm-packages/cli/package.json` + its `optionalDependencies`, and `browser-extension/manifest.json`).

## 📚 Documentation

| Resource | Description |
|----------|-------------|
| [DennisJcy/Omnibot-skills](https://github.com/DennisJcy/Omnibot-skills) | Open-source repo for the Omnibot agent skill: SKILL.md, command reference, operation patterns |
| [doc/build.md](./doc/build.md) | Full build guide: Nuitka, Docker, platform scripts |
| [docs/product-overview.md](./docs/product-overview.md) | Product overview and design |
| [docs/product-roadmap.md](./docs/product-roadmap.md) | Feature roadmap and status |
| [AGENTS.md](./AGENTS.md) | Developer conventions, commands, and release checklist |
| [src/omnibot/skills/omnibot/SKILL.md](./src/omnibot/skills/omnibot/SKILL.md) | Agent execution specification (the omnibot skill) |

## 🤝 Compatible Agents

Omnibot works with any agent system that can execute CLI commands:

- 🧠 **Hermes** — native integration
- 🟠 **Claude Code** — via skill file
- 📦 **Codex** — via skill file
- 🔓 **OpenCode** — via skill file
- 🔧 **Any CLI-capable agent** — via `omnibot` commands

## 📋 Example Workflow

```bash
# Set workflow context
export OMNIBOT_SESSION_TOKEN=research

# Open a new tab
omnibot open "https://github.com"

# Snapshot the page with interactive refs
omnibot snapshot -i --tab-id $TAB_ID

# Click the search box and type
omnibot find placeholder "Search GitHub" --action type \
  --action-value "omnibot" --tab-id $TAB_ID

# Press Enter
omnibot press Enter --tab-id $TAB_ID

# Wait for results
omnibot wait --text "repositories" --tab-id $TAB_ID

# Read the results
omnibot read --tab-id $TAB_ID
```

## 📄 License

MIT. See [LICENSE](./LICENSE) for details.

---

<div align="center">

**Built for agents that need to see the web — not just fetch it.**

[⭐ Star on GitHub](https://github.com/DennisJcy/omnibot) · [📖 Read the Skill Spec](./src/omnibot/skills/omnibot/SKILL.md)

</div>
