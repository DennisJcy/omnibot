# Omnibot Product Roadmap

Last updated: 2026-07-08

This document is the current product-status source of truth. Historical implementation plans in `docs/superpowers/plans/` remain useful for design intent and task history, but their unchecked boxes may not reflect the current codebase.

The comparison baseline for the next roadmap phase is the Codex Chrome plugin surface: skill docs plus a browser runtime that exposes tabs, visibility, screenshots, Playwright-style locators, developer evidence, and clear cleanup/documentation flows. Omnibot remains CLI-first, but its commands, JSON contracts, and packaged skills should be shaped so they can also support SDK and MCP-style agent runtimes later.

## Product Direction

Omnibot lets AI agents read, inspect, debug, and operate the user's real Chromium browser: real tabs, real login state, real extension environment, and explicit tab targeting through a local daemon plus CLI.

Near-term product priorities:

- Keep the local real-browser workflow stable and explicit.
- Make common browser automation tasks possible without raw JavaScript.
- Provide clear fallback tiers when semantic or ref-based operations fail.
- Preserve agent-friendly stdout while keeping diagnostics on stderr.
- Package skills and docs so agents can reliably discover the correct workflow.
- Close Chrome plugin parity gaps in visibility launch, visual evidence, and documentation discovery.

## Status Legend

- Done: implemented in CLI/action/daemon surface and covered by unit or E2E contracts.
- Partial: command surface exists, but production behavior has known limits or only a foundational path is implemented.
- Experimental: available for targeted testing, not yet a default production workflow.
- Planned: not implemented or only represented by design notes.

## Done

### Runtime And Distribution

- Local daemon and CLI v2 runtime: `omnibot doctor`, `status`, `start`, `stop`, `run`, daemon auto-start, and local ports `18764`/`18765`.
- Browser extension transport: WebSocket primary path, HTTP long-poll fallback, tab/session tracking, extension reconnect behavior, and tab update broadcasting.
- npm packaging: platform packages, CLI package, packaged skills path/install commands, and version checks.
- Explicit tab targeting: page-state commands require `--tab-id`; no implicit default target for browser state changes.

### Reading And Page Understanding

- `read`: clean rendered page reading with `--screens`, URL temporary-tab mode, tab-targeted mode, and JSON/text output.
- `snapshot`: accessibility tree snapshot, `@eN` refs, interactive filtering, compact/depth/url options, selector scoping, rich text editor controls, popup/modal controls, and combobox option probing.
- `get`: title, URL, text, HTML, value, attribute, count, box, and style reads.
- `is`: visible, enabled, and checked state checks.
- `find`: semantic locators for role, text, label, placeholder, alt, title, testid, and nth, with subactions such as click, fill, type, hover, focus, check, uncheck, and text.

### User-Like Browser Operations

- Ref/selector operations: `click`, `dblclick`, `fill`, `type`, `press`, `hover`, `focus`, `select`, `check`, `uncheck`, `scroll`, `scrollintoview`, and element-level `drag`.
- Upload: CDP `DOM.setFileInputFiles`, DOM nodeId fallback, and JS `DataTransfer` fallback are implemented and unit-covered.
- Navigation and tab lifecycle: `navigate`, `open`, `goto`, `close`, `tab list/new/close`, `window new`, `frame`, `back`, `forward`, `reload`, and `pushstate`.
- Wait and batch: selector/text/URL/load/function/fixed-time waits, hidden/visible state, and JSON/file batch commands.

### Debugging And Evidence

- Screenshots: normal/full/annotated screenshots, PNG/JPEG options, base64/file output paths.
- Console: logs, errors command path, and clear.
- Dialogs: JavaScript dialog logs, clear, accept/dismiss, and prompt text handling.
- Network: extension-backed capture start/stop/clear/logs/summary.
- Raw CDP: `cdp <method> <params-json>` for last-resort inspection.

### Fallback And Advanced Operation Surfaces

- CUA coordinate mouse: `mouse click`, `mouse move`, `mouse scroll`, and `mouse drag` command surface backed by CDP input events.
- DomCUA: `dom visible`, `dom click`, `dom dblclick`, and `dom scroll` for visible DOM node-id fallback workflows.
- Clipboard: `clipboard read` and `clipboard write` through page context.
- Viewport: `viewport get` and `viewport set` via page state/CDP emulation.
- Assets: `assets list` and `assets export`; export writes asset metadata into a zip when an output path is provided.
- Browser/session metadata: `browser list/current/claim/release`, `session name/list`.

## Partial Or Experimental

### Human Verification

- `verify inspect` detects and extracts metadata for NetEase Yidun captcha widgets.
- It does not solve captchas, does not provide a production-grade bypass workflow, and requires visual cross-checking for state and coordinate mapping.

### Mouse Drag Realism

- `mouse drag --fast` is the stable linear path.
- The default realistic drag trajectory is available but experimental; timing, jitter, and success rates still need production validation.

### Console And Network Capture Completeness

- Console and network command surfaces exist and have extension-backed capture paths.
- `console errors` currently shares the console log collection path; callers should verify level filtering in output.
- Network and dialog capture require a current browser extension; older extensions return explicit upgrade/reload errors.

### Record, Replay, And Trace

- `record start/stop`, `replay`, and `trace start/stop` are exposed and have basic payload/file shapes.
- Automatic capture of every CLI action into `recorded_actions` / `trace_events` is not yet wired as a complete product workflow.
- Replay supports a limited action set and should be treated as a foundation, not stable browser-flow automation.

### Visibility Modes

- `visibility status` and `visibility set` model visible, background, dedicated-profile, and headless modes.
- `visibility launch` currently returns `status: planned` for dedicated/headless launch; it does not yet spawn or attach a separate browser profile.

### Assets Export

- `assets list/export` collect resource metadata from the page.
- Full offline page mirroring, binary asset download, and HAR-quality archive export are not implemented.

## Chrome Plugin Parity Priorities

### P0: Real Visibility Launch, Dedicated Profile, And Headless

Goal: replace planned-only `visibility launch` with real browser startup and attach behavior. This closes the largest gap with the Chrome plugin's visibility model while preserving Omnibot's explicit local daemon architecture.

Target modes:

| Mode | Use case | Login state | Browser shape |
| --- | --- | --- | --- |
| `visible` | Work in the user's real browser and let them watch when requested. | Existing user login. | Current extension-connected Chrome/Edge/Brave/Arc window. |
| `background` | Default agent work that should not foreground tabs. | Existing user login. | Current extension-connected browser, not actively shown. |
| `dedicated-profile` | Clean automation profile for tests, demos, and repeatable agent workflows. | Separate profile. | Omnibot-launched Chromium browser with remote debugging. |
| `headless` | CI/e2e and visual verification without user UI. | Separate profile. | Omnibot-launched headless Chromium with remote debugging. |

Planned CLI:

```bash
omnibot visibility status
omnibot visibility set background
omnibot visibility set visible

omnibot visibility launch dedicated-profile \
  --browser chrome \
  --user-data-dir /tmp/omnibot-profile \
  --url https://example.com

omnibot visibility launch headless \
  --browser chromium \
  --user-data-dir /tmp/omnibot-headless \
  --url https://example.com \
  --window-size 1280x720
```

Implementation plan:

1. Add launch parser options: `--browser`, `--url`, `--user-data-dir`, `--window-size`, `--headless=new|old|false`, and optional `--remote-debugging-port`.
2. Add `browser_launcher.py` to locate browsers, allocate ports, build launch arguments, spawn processes, and record owned process metadata.
3. Extend `devtools.py` to discover CDP targets through `/json/version` and `/json/list`, attach to target WebSockets, and create `cdp-client:<targetId>` tab ids.
4. Extend `state.py` to persist visibility runtime state: mode, browser, pid, debugging port, user data dir, owned flag, and created timestamp.
5. Extend `TMWebDriver`/CDP plumbing so launched CDP tabs initially support `tabs`, `goto`, `get title/url`, `screenshot`, `cdp`, `close`, and cleanup.
6. Update `doctor` to report owned launched browser health separately from extension health.
7. Update `tabs` to list both extension-backed tabs and Omnibot-owned CDP tabs without mixing transport sessions and page targets.
8. Keep extension-connected user tabs as the only default for existing login state; headless and dedicated profiles must be documented as separate login contexts.

First release acceptance:

- `visibility launch dedicated-profile --url <fixture>` returns a controllable tab id.
- `visibility launch headless --url <fixture>` works on macOS and CI-supported Linux.
- `tabs`, `get url`, `get title`, `screenshot`, `goto`, and `close` work for launched tabs.
- Stopping or cleaning up Omnibot-owned browsers never closes pre-existing user tabs.

Tests:

- Unit tests for command parsing and browser argument construction.
- Unit tests for state persistence and process ownership metadata.
- Integration tests for CDP target discovery against a launched browser.
- E2E fixture for headless `goto -> get title -> screenshot -> close`.
- Safety test proving cleanup only terminates Omnibot-owned pids.

### P1: Agent Runtime And Playwright-Style API Surface

Goal: keep CLI-first behavior while making Omnibot's JSON contracts suitable for a future JS/Python/MCP runtime similar to the Chrome plugin's `browser -> tab -> playwright/cua/dev/clipboard` model.

Planned scope:

- Stable JSON contracts for tab handles, screenshot evidence, errors, and capability discovery.
- Future SDK wrapper over existing commands instead of bypassing CLI/daemon logic.
- Locator-style abstractions can build on `find`, `snapshot`, `get`, `click`, `fill`, and `wait`.

Initial parity targets:

- `browser.tabs.list/new/get`.
- `tab.goto/back/forward/reload/close/title/url/screenshot`.
- `tab.dev.logs`.
- `tab.clipboard.read/write`.
- Locator equivalents for role, text, label, placeholder, testid, CSS selector, count, visible/enabled/checked, click, fill, type, press, and wait.

### P2: Screenshot And Visual Evidence Enhancement

Goal: match Chrome plugin screenshot capabilities: viewport, full page, crop, element screenshot, and evidence-friendly output that agents can directly include in final responses.

Planned CLI:

```bash
omnibot screenshot --tab-id <TAB_ID> -o /tmp/page.png
omnibot screenshot --tab-id <TAB_ID> --full -o /tmp/full.png
omnibot screenshot --tab-id <TAB_ID> --crop 10,20,300,200 -o /tmp/crop.png
omnibot screenshot --tab-id <TAB_ID> --selector "#submit" -o /tmp/submit.png
omnibot screenshot --tab-id <TAB_ID> --ref @e4 -o /tmp/ref.png
omnibot screenshot --tab-id <TAB_ID> --element @e4 --annotate
omnibot screenshot --tab-id <TAB_ID> --markdown
```

JSON contract:

```json
{
  "status": "success",
  "format": "png",
  "path": "/abs/path.png",
  "visual_path": "/abs/path.png",
  "markdown": "![screenshot](/abs/path.png)",
  "mode": "element",
  "clip": {"x": 10, "y": 20, "width": 300, "height": 200, "scale": 1},
  "tab_id": "edge-client:123",
  "url": "https://example.com"
}
```

Implementation plan:

1. Extend screenshot CLI args: `--crop x,y,w,h`, `--selector`, `--ref`, `--element`, `--markdown`, and an explicit pixel mode if needed.
2. Add a shared clip parser that validates positive width/height and returns CSS-pixel coordinates.
3. Resolve `@eN` through the workflow token's `RefMap`; resolve selectors through `getBoundingClientRect()`.
4. Scroll element targets into view before measuring when needed.
5. Use CDP `Page.captureScreenshot` `clip` for crop and element screenshots; use `Page.getLayoutMetrics` for full-page screenshots.
6. Keep current `--annotate` behavior and extend it so element screenshots can also return an annotated viewport artifact when useful.
7. Extend `output.py` default naming to include mode and format, for example `~/.omnibot/screenshots/<timestamp>-element.png`.
8. Return `markdown` and `visual_path` whenever a file path exists so agents can embed the screenshot directly.
9. Update skill docs to say screenshots are visual evidence, not text extraction; prefer `read`/`get` for text.

Tests:

- Parser tests for `--crop`, `--selector`, `--ref`, `--element`, and `--markdown`.
- Unit tests for clip parsing and invalid crop inputs.
- Action contract tests proving screenshot params include expected CDP clip fields.
- E2E fixture for viewport, full-page, crop, selector element, and `@eN` element screenshots.
- Output test verifying `markdown` uses an absolute path.

### P3: Docs And Skills Doctor

Goal: match Chrome plugin's documentation discoverability. Agents should not guess command syntax after failure; they should discover a topic, read the relevant packaged docs, and get repair guidance.

Planned CLI:

```bash
omnibot docs list
omnibot docs show screenshot
omnibot docs show visibility
omnibot docs show network
omnibot docs search "file upload"

omnibot skills doctor
omnibot skills doctor --agent codex
omnibot skills doctor --json
```

Topic registry:

| Topic | Source |
| --- | --- |
| `runtime` | `references/runtime-and-status.md` |
| `tabs` | `references/session-and-tabs.md` |
| `read` | `references/operation-patterns.md#read` |
| `click` | `references/operation-patterns.md#click` |
| `fill` | `references/operation-patterns.md#fill` |
| `screenshot` | `references/debugging-and-evidence.md#screenshot` |
| `network` | `references/debugging-and-evidence.md#network-capture` |
| `fallback` | `references/fallback-operations.md` |
| `anti-patterns` | `references/anti-patterns.md` |
| `visibility` | `references/session-and-tabs.md#visibility` |

`skills doctor` checks:

1. Packaged skills directory exists and contains `SKILL.md` plus required references.
2. Installed agent skill directories exist for requested agents.
3. Installed skill metadata version matches packaged skill metadata version.
4. Packaged docs mention current CLI commands and avoid removed runnable commands.
5. Command docs and examples include `OMNIBOT_SESSION_TOKEN` and explicit `--tab-id` where required.
6. Version surfaces are aligned enough for release: package version, skill metadata, and command reference are not stale.
7. Output includes direct repair commands such as `omnibot skills install --agent codex` and `omnibot docs show <topic>`.

JSON contract:

```json
{
  "status": "warning",
  "packaged_skills_dir": "/abs/path",
  "installed": [
    {"agent": "codex", "path": "/abs/path", "status": "outdated"}
  ],
  "topics": ["runtime", "tabs", "screenshot"],
  "recommendations": [
    "Run: omnibot skills install --agent codex"
  ]
}
```

Implementation plan:

1. Add `docs.py` with a topic registry, markdown reader, heading extractor, and simple full-text search.
2. Add `docs` parser tree in `cli.py`; keep it daemon-free.
3. Extend `skill_installer.py` with diagnostics instead of only copy/install behavior.
4. Add `skills doctor` under the existing `skills` command.
5. Add command failure routing guidance in packaged skill docs: parser error -> command help -> `omnibot docs show <topic>`.
6. Add release/preflight checks for docs and installed skill consistency.

Tests:

- `docs list` includes every topic in the registry.
- `docs show screenshot` prints the screenshot guidance.
- `docs search` returns matching topic names and file paths.
- `skills doctor` reports missing, installed, and outdated skill states.
- Contract tests prevent removed commands from reappearing in runnable examples.

## Later Planned Or Not Implemented

### Browser Capability Gaps

- Download management and file chooser event workflow.
- PDF export, full page archive, and full HAR export.
- Google Workspace document export similar to Chrome plugin `content.exportGsuite`.
- Persistent cookie/storage/state vault and auth profile management.
- Robust cross-origin iframe introspection beyond current best-effort behavior.

### Safety And Policy Gaps

- Runtime-level confirmation workflow for uploads, form submissions, deletes, purchases, sensitive data transmission, permissions, extension installs, and other browser-side effects.
- Structured risk classification returned by actions before irreversible browser operations.
- Policy controls for teams and managed environments.

### Debugging And Observability Gaps

- Trace viewer/dashboard.
- Record/replay as a durable no-code macro workflow.
- Profiler, Web Vitals, React/Vue component introspection, and performance timelines.
- Streaming event feed for long-running operations.

### Product And Platform Gaps

- Remote multi-user daemon as a supported product mode.
- Cloud browser providers, Lightpanda, iOS/Appium, and mobile automation.
- Team dashboard, policy administration, billing/payment integration, and hosted account management.
- AI-assisted captcha solving. Current scope is inspection only.

## Suggested Next Milestones

### M1: Visibility Launch Foundation

- Implement real `visibility launch dedicated-profile` and `visibility launch headless`.
- Support `tabs`, `goto`, `get title/url`, `screenshot`, `cdp`, and `close` for launched CDP tabs.
- Update `doctor`, `tabs`, skill docs, and release tests to distinguish extension-backed user tabs from Omnibot-owned CDP tabs.

### M2: Screenshot Evidence Parity

- Add crop, selector, and `@eN` element screenshots.
- Return `visual_path` and markdown output for agent final responses.
- Add E2E visual fixture coverage for viewport, full, crop, selector, and ref screenshots.

### M3: Docs And Skills Doctor

- Add `omnibot docs list/show/search`.
- Add `omnibot skills doctor`.
- Wire docs consistency checks into release preflight.

### M4: Agent Runtime And Locator Facade

- Define stable JSON contracts for browser, tab, screenshot, error, and capability objects.
- Build a thin SDK/MCP layer over current CLI/daemon actions.
- Add Playwright-style locator facades only after contracts stabilize.

### M5: Product Expansion

- Add download/file chooser, Google Workspace export, and runtime safety confirmation.
- Revisit remote daemon, hosted/team workflows, policy controls, and cloud browser providers only after local real-browser automation remains stable across release gates.
