---
name: omnibot
slug: omnibot
displayName: omnibot-智能体浏览器自动化工具
version: "2.4.0"
summary: 为 AI Agent 提供浏览器基础设施，连接真实 Chromium 浏览器进行页面读取、操作、导航和调试。
license: MIT
description: Use when AI agents need to read, inspect, operate, navigate, debug, or verify browser state through the omnibot CLI and connected Chromium extension.
compatibility: Requires omnibot v2 CLI daemon and the omnibot Chromium extension connected to 127.0.0.1:18765.
allowed-tools: Bash
---

# Omnibot

Omnibot is Browser Infrastructure for AI Agents.

It connects Hermes, Claude Code, Codex, OpenCode, and other agent systems to a real Chromium browser through the local omnibot daemon and CLI.

This skill is an execution specification for agents. It is not a human command manual.

## When to Use

- Use Omnibot when browser runtime state matters: login, cookies, storage, client-side rendering, extensions, or visible user tabs.
- Use Omnibot when an agent must read rendered pages, click controls, fill forms, navigate, extract content, or collect evidence.
- Do not use Omnibot when static files or plain HTTP content already answer the task.

## Core Rules

- Reliability > Convenience.
- Explicit State > Implicit State.
- Pattern > Command.
- Observe -> Act -> Verify.
- Fallback is allowed, but never first.
- Native Omnibot commands before scripts. Do not use `execute-js` first.
- Run `omnibot <command> --help` before using uncommon or newly introduced commands, especially `batch`, `network`, `cdp`, `record`, `trace`, and `skills`.
- If a command from memory fails with parser errors, stop using that remembered syntax and re-check `omnibot --help` plus the subcommand help.
- Prefer semantic locators and `snapshot -i` refs before selectors.
- Treat snapshot refs as exact live targets even when AX names are blank. A password input is annotated as `[textbox] [type=password]`; use its ref before falling back to `input[type=password]`, and never expose the secret merely to prove the fill.
- Treat `frame` targets as tab-wide absolute descriptors. A unique id/name/title/src substring can resolve a nested descendant frame; when a selected frame snapshot contains another `[Iframe]`, inspect its `src`, target that unique substring, and re-snapshot. `frame main` is the reserved return-to-host command, not a selector for `id="main"`.
- When the user has explicitly requested a native Omnibot command and the terminal tool is available, execute it immediately; do not ask for confirmation or claim that it was not run. If dispatch genuinely fails, report the concrete tool error after one bounded retry and do not fabricate browser results.
- A multi-step browser task is incomplete until its requested final verification command has actually run. After the last mutation, always issue the concrete `get`/`is`/`wait` verification, inspect its result, and only then report completion; never stop after reporting that the mutation itself succeeded.
- For workflows with more than five meaningful browser actions, split the work into multiple bounded turns. Each turn should finish its own observe -> act -> verify cycle and report the retained tab id before the next turn; do not put a long mutation chain and all final checks into one model request.
- Raw `cdp` calls are one-shot. Do not assume `Network.enable` alone creates readable logs. For API/request evidence, use `network clear -> network start -> one action -> network stop -> network logs/summary`.
- After a failed click by ref, re-observe or use a higher-evidence fallback. Do not keep using stale `@eN` refs from a previous snapshot.
- Semantic and ref clicks automatically re-resolve the live target, scroll it into view, wait for stable geometry, and verify that it receives pointer events before clicking. Do not manually scroll merely because a known target's snapshot box is off-screen.
- Manually scroll before target discovery only when the target is not yet represented in the DOM/snapshot, such as virtualized lists, infinite feeds, collapsed regions, or lazy-rendered content. After it appears, use a normal atomic click rather than coordinate clicking.
- For shopping, checkout, payment, banking, or irreversible workflows: Do not click final submit/pay/place-order controls unless the user explicitly confirms that final action in the current turn.
- Prefer condition-based `wait` over shell sleep.
- Timeout values for commands that expose a timeout option, such as `wait`, are seconds, not milliseconds. Use `--timeout 5` for a five-second wait; never convert milliseconds into a raw CLI timeout value. `dialog logs` and `dialog clear` do not accept `--timeout`.
- `wait --load` is valid without a value and defaults to the `load` lifecycle state. Use `--load domcontentloaded` or `--load networkidle` only when that specific state is required. A successful load wait proves only the browser lifecycle condition; verify the final URL or business state separately.
- Native dialog workflows are session-token scoped: use the exact same `OMNIBOT_SESSION_TOKEN` for the triggering click, `dialog logs`, and `dialog handle`. A different token cannot observe or handle the original dialog.
- Parse JSON output from commands that return JSON.
- Treat both the process exit status and JSON result as part of the command contract. `status: error` and `status: timeout` exit non-zero and include an `error_code`; preserve that output in wrappers so cleanup and retry logic can distinguish runtime disconnects from page failures.
- Omnibot may retry read-only actions and same-tab `goto` once after a transient daemon or extension disconnect. It does not replay clicks, fills, new-tab creation, or other mutations. After any uncertain mutation result, observe browser state before deciding whether another action is safe.
- Do not claim success without verification evidence.

### Runtime

Use the installed `omnibot` command that is available to the user. Before an
agent-driven browser workflow, verify that the CLI is available and inspect the
relevant command help when needed:

```bash
command -v omnibot
omnibot --version
```

If a workflow enters a shell function, sandbox, or subprocess that may replace
`PATH`, resolve the executable before entering it and keep the absolute path:

```bash
OMNIBOT_BIN="$(command -v omnibot)" || exit 1
"$OMNIBOT_BIN" --version
```

Do not diagnose `command not found` as a daemon or extension failure. The shell
raises it before Omnibot starts. If basic tools such as `sleep` or `ls` are also
missing, restore a baseline system `PATH` or use their absolute paths.
In zsh, lowercase `path` is a special array tied to `PATH`; never use `path` or
`local path` as a route/file variable. Use `route_path` or `page_path` instead.
Do not hide Omnibot output with `>/dev/null 2>&1` while diagnosing or while a
wrapper still needs to decide cleanup. Capture the JSON and exit status first,
then log, retry, or clean up from the structured result.

The CLI manages its local daemon automatically. Do not depend on a source
checkout, Python environment, repository files, or developer-only commands.

## Native Command Router

Before any page-state operation, choose the narrowest native command that expresses the intent. JavaScript is not a convenience shortcut; it is a fallback that requires evidence that native commands could not reach the state.

| Intent | Native command path | Do not start with |
| --- | --- | --- |
| Current page identity | `get title`, `get url`, then `snapshot -i` or `read` if needed | `execute-js "return document.title/location.href"` |
| Browser history | `browser history [text]` (also `history search [text]`) | reading browser history through page JavaScript |
| Bookmarks | `browser bookmarks` (also `bookmarks tree`) | reading the browser bookmark tree |
| Downloads | `browser downloads [terms]` (also `downloads search [terms]`, `downloads open <id>`) | inspecting/opening browser downloads |
| Recently closed | `browser recently-closed` | reading recently closed tabs/windows |
| Top sites | `browser top-sites` | reading browser frequent/top sites |
| Installed extensions | `browser extensions` | listing extension name, ID, enabled state, type, and version (read-only) |
| Content settings | `browser content-settings [TYPE] [URL]` | reading site permission state, default `automaticDownloads` (read-only) |
| Mouse visual state | `browser mouse-visual-state --tab-id <TAB_ID>` | verifying the extension cursor overlay and asset load state (read-only diagnostic) |
| Notifications | `browser notify <title> [message]` | showing a browser notification |
| Tab groups | `tab group <TAB_ID> [NAME]`, `tab group-info <TAB_ID>`, `tab ungroup <TAB_ID>` | grouping and inspecting browser tabs |
| Page text/content | `read --screens N`, `get text`, `get html`, `get attr`, `get count` | `execute-js "document.body.innerText"` |
| Iframe context | `frame <iframe-id/name/title/src>`, then `snapshot`/page-state commands | Assuming host selectors reach child frames |
| Click | `find ... --action click` -> `snapshot -i` + `click @eN` -> `click selector` -> `dom click` -> `mouse click` | `document.querySelector(...).click()` |
| Scroll | `scroll`, `scrollintoview`, `dom scroll`, then `mouse scroll` | `window.scrollTo`, `element.scrollIntoView()` |
| Fill/type | Text entry: `find ... --action fill`, `fill`, or `type`; key semantics: `press`/`keyboard` | setting `.value` or `innerHTML` in JS |
| Wait | `wait` by selector/text/url/load/fn | shell sleep or JS timers |

If you are about to write `document.querySelector`, `document.body.innerText`, `.click()`, `.value =`, `innerHTML`, `scrollTo`, or `scrollIntoView`, stop and identify the native command you will try first. Only use `execute-js` after documenting which native tiers failed and how you will verify the result.

Text entry rule: when the user asks to enter, type, fill, or replace text, use `fill` or `type`. `keyboard` and `press` dispatch key events for shortcuts and key semantics; they are not text insertion commands and must not be substituted for text entry.

Form commit rule: after `fill`, `type`, `select`, `check`, `uncheck`, or `upload`, verify the control itself with `get value`, `get attr`, or `is` before judging the workflow. Many pages keep a separate saved/rendered status that does not change until a visible `Save`, `Apply`, `Submit`, or equivalent control is activated. If such a commit control exists and the task expects business-state verification, observe it, activate it with a native command, then verify the resulting status. Do not report a form action as failed merely because an unrelated status element is still stale, and do not report it as complete without verifying both the control value and any required commit result.

Form terminal-timeout rule: keep form workflows as short observe → one control action → one verification steps. If a terminal call times out after `fill`, `select`, `check`, or `Save`, query the browser state first; do not repeat the action blindly because the browser may already have applied it. Continue from the first unverified control and finish with one commit click plus one final status read.

Mutation retry rule: issue at most one mutating browser command (`fill`, `type`, `select`, `check`, `uncheck`, `click`, `dblclick`, `drag`, `upload`, or `navigate`) per agent request. If its terminal output is empty, delayed, or times out, the next request must be read-only (`get`, `is`, `snapshot`, `read`, `tabs`, or `wait`) to determine whether the mutation already happened. Never replay the mutation merely because the tool response was missing; duplicate fills can append text and duplicate clicks can change business state.

Drag performance rule: selector-based `drag` may take longer than a terminal tool's short default timeout because it dispatches a human-like event sequence. For agent workflows where exact trajectory is not required, prefer `snapshot -i` plus coordinate `mouse drag --fast` after verifying source/target boxes; then verify the target state. If semantic `drag` is required, allow a longer command timeout and do not retry blindly while the first drag may still be running.

Clipboard rule: both `clipboard read` and `clipboard write` require the explicit
`--tab-id <TAB_ID>` on every invocation, even though the clipboard is shared by
the browser extension. If no tab id is known, discover a safe target tab first;
never omit the flag or infer a default tab.

Cross-origin frame rule: snapshot visibility does not guarantee write access. After targeting a cross-origin iframe, verify `fill`/`type` focus and the resulting value; if focus fails, report the limitation explicitly and do not use JavaScript as a bypass.

## Workflow Context + Tab Target

Every page-state workflow must use both controls:

- `OMNIBOT_SESSION_TOKEN=<workflow-name>` for workflow isolation.
- `--tab-id <TAB_ID>` for page targeting.

OMNIBOT_SESSION_TOKEN is a workflow/context token, not a browser session and not a tab target. It isolates agent state such as refs, trace, recording, aliases, and temporary resources. Tab ID controls which page receives the command.

Do not rely on default tab, active tab, current tab, or prior targeting state. Every page-state command requires explicit `--tab-id` except when the command is only discovering or creating a tab.

Use the same token inside one workflow. Use different tokens for independent workflows.

Standard form:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
```

`@eN` refs are tab-scoped. Refs rule: never reuse `@eN` refs across tabs.

The agent dispatch pattern is token + tab-id:

1. Set a stable `OMNIBOT_SESSION_TOKEN`.
2. Discover or create the target tab.
3. Save the returned tab id.
4. Pass `--tab-id <TAB_ID>` on every command that touches page state.
5. Run observe -> act -> verify on that same tab.

Tab-id identity rule: use the exact `id` field returned by Omnibot `tabs`/`tab list` or by a tab-creation command. Browser-control surfaces may expose a shorter numeric `tab_id`; that value is not necessarily the Omnibot session id. When the discovery output contains both `tab_id` and `id`, pass the full namespaced `id` (for example, `edge-...:12345`) to `--tab-id`. Never reconstruct or strip the namespace.

Phased workflow rule: do not bundle navigation and several page actions into one unverified sequence. After creating or navigating a tab, first run `get url` (and `snapshot -i` when controls are involved); then perform one meaningful action; then verify its concrete state before issuing the next action. For a form or multi-control task, repeat this observe -> one action -> verify cycle for each control.

Examples of tab-locked page-state commands:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot get value "input[name=email]" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find placeholder "Search" --action type --action-value "omnibot" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot dom dblclick n1 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot clipboard read --tab-id <TAB_ID>
```

Targeting categories:

| Command category | Rule |
| --- | --- |
| Page-state commands: `snapshot`, `click`, `fill`, `type`, `get`, `is`, `wait`, `screenshot`, `console`, `network`, `execute-js`, `dom`, `mouse`, `clipboard`, `viewport`, `assets`, `goto`, same-tab `navigate` | Require `--tab-id <TAB_ID>`. |
| Discovery or tab creation: `tabs`, `tab list`, `tab new <URL>`, `open <URL>`, `navigate <URL>` | Return or discover the tab id; save it for later page-state commands. |
| Read URL exception: `read <URL>` | Opens a temporary read tab and does not need `--tab-id`; reading an existing tab still requires `read --tab-id <TAB_ID>`. |

Navigation safety invariant:

- When the task says "open", "open a new tab", or "create a test page", use `open <URL>` or `tab new <URL>` and use the returned tab id. Do not substitute `goto`, plain `navigate`, or the currently active tab.
- `navigate <URL>` also opens a new tab by default; `navigate <URL> --new-tab` is an explicit equivalent accepted for agent compatibility. Use `navigate <URL> --same-tab --tab-id <TAB_ID>` only for deliberate same-tab reuse.
- Use `goto --tab-id <TAB_ID>` or `navigate --same-tab --tab-id <TAB_ID>` only when the task explicitly asks to reuse an existing tab.
- After creating a tab, verify `get url --tab-id <TAB_ID>` before any clipboard, upload, form, or other page-state operation. This prevents a failed or misinterpreted tab-creation result from mutating a user-owned page.
- Tool-created tabs are temporary workflow resources and may be auto-closed by cleanup after inactivity. Complete the intended tab workflow in the same token/context, keep the returned tab id, and do not assume it will still exist after a long model pause or a separate one-shot agent process. If a later close reports `not found`, re-list tabs before retrying; the cleanup may already have closed it.
- If `open` or `tab new` times out, loses its final response, or is retried after an agent/tool interruption, first run `tabs` or `tab list` and match the requested URL. Reuse one matching tab id instead of issuing another create command. Only create again after confirming that no matching tab from the interrupted attempt exists.

## Observe -> Act -> Verify

All page operations must follow this loop:

1. Observe the current page state.
2. Act once using the highest reliable pattern available.
3. Verify the expected state change.

Click example:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
```

Read/verify example:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot is enabled "button[type=submit]" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find role button --name "Submit" --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --url "/dashboard" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot get url --tab-id <TAB_ID>
```

If verification fails, do not repeat blindly. Re-observe, choose the next fallback tier, and verify again.

Click refs are live-node actions, not cached-coordinate actions. A successful `click @eN` may report `auto_scrolled`, `before_box`, `clicked_box`, and `hit_test`; use those fields as evidence that an off-screen or nested-container target was brought into the viewport safely. Do not insert a manual `scroll -> snapshot` sequence between selecting a known ref and clicking it.

## Pattern > Command

Start from the task, not the command name. Use operation patterns for read, click, fill, select/check, navigation, wait, extraction, and batch.

Use fallback tiers only after standard patterns fail. Collect evidence separately from fallback execution. The command reference is only a lookup table; it must not decide behavior.

## Read vs Snapshot Routing

Choose by intent before choosing by command name:

| Intent | Prefer | Why |
| --- | --- | --- |
| Summarize or extract page content, article text, search results, feeds, or long/lazy pages | `read` | Returns clean text/Markdown for agent reasoning. |
| Quickly observe current visible UI structure before deciding what to do next | `snapshot -i` | Returns interactive refs plus visual-region refs for screenshot targeting. |
| Find buttons, links, inputs, or refs for a later action | `find` or `snapshot -i` | Produces actionable targets; `read` does not. |
| Verify one concrete condition | `get`, `is`, or `wait` | Narrow evidence is more reliable than dumping a page. |

Do not use `read` as the first step for click/fill workflows unless the user explicitly asked for page content first.

## Screenshots And Visual Regions

`screenshot --tab-id <TAB_ID>` without `--ref` remains a full current-viewport screenshot.
For a specific visual region, run `snapshot -i` and choose a ref marked `[visual=true]`, such as
`article`, `region`, `dialog`, `listitem`, `image`, or `video`:

```bash
OMNIBOT_SESSION_TOKEN=visual omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=visual omnibot screenshot --ref @e146 --tab-id <TAB_ID> -o /tmp/region.png
```

Visual-region refs are intended for complete content containers, cards, posts, dialogs, media, and similar areas.
Do not screenshot a button, link, or textbox as a standalone target unless the user explicitly asks for that control.
The ref screenshot path re-resolves the live DOM node, scrolls it into view, waits for layout to settle, and then captures its region.
After `read` or scrolling, refresh the snapshot before using a stale ref. Raw `get box` plus `cdp Page.captureScreenshot` is not the normal screenshot workflow.

## Dropdowns And Custom Comboboxes

`snapshot -i` may auto-probe visible custom comboboxes and append their options as refs. If the output lists `@eN [option] "..."`, click that option ref directly; Omnibot will reopen the owning combobox through `openerSelector` if the dropdown closed during snapshot.

Use `select @combobox "value"` for native selects or simple controls. Use `click @option` when `snapshot -i` exposes auto-probed combobox option refs. Do not manually reopen every dropdown just to discover options unless `snapshot -i` did not expose option refs.

## Rich Text Article Editors

ContentEditable rich text editors (ProseMirror, Quill, Draft.js, Slate, ByteDance/Toutiao article body, etc.) are often missing from the AX tree. `snapshot -i` appends them under `# DOM Rich Text Editors` as `@eN [richtext] "..." [contenteditable=true]` refs.

- Detect the body editor: `snapshot -i` → look for `@eN [richtext]` under `# DOM Rich Text Editors`. Do not fill the article body through a `[textbox]` title ref.
- Replace the whole body: `fill @richtext "paragraph 1\n\nparagraph 2"`. Empty lines split paragraphs; the previous content is cleared and `input`/`change` events are dispatched.
- Append to the body: `type @richtext " additional text"`.
- Focus before keyboard input: click `@richtext` first, then `press`/`keyboard`.
- Raw selector fallback: `omnibot fill '[contenteditable="true"]' "..."` also routes through the rich text path when the selector looks like a rich editor.

Do not use `execute-js` first for rich text writes; `fill`/`type` on the `[richtext]` ref is the supported path.

## Quick Routing

| Need | Read |
| --- | --- |
| Runtime check | `references/runtime-and-status.md` |
| Reading pages | `references/operation-patterns.md#read` |
| Clicking | `references/operation-patterns.md#click` |
| Filling forms | `references/operation-patterns.md#fill` |
| Scrolling | `references/operation-patterns.md#scroll` |
| Select / check | `references/operation-patterns.md#select--check` |
| Navigation | `references/operation-patterns.md#navigation` |
| Waiting | `references/operation-patterns.md#wait` |
| Extraction | `references/operation-patterns.md#extraction` |
| Batch | `references/operation-patterns.md#batch` |
| Fallback | `references/fallback-operations.md` |
| Tabs and sessions | `references/session-and-tabs.md` |
| Debug evidence | `references/debugging-and-evidence.md` |
| Network/API capture | `references/debugging-and-evidence.md#network-capture` |
| Commands | `references/command-reference.md` |
| Anti-patterns | `references/anti-patterns.md` |

## Runtime First

Before troubleshooting browser behavior, check runtime state:

```bash
omnibot doctor
omnibot tabs
omnibot visibility status
omnibot browser current
```

If the extension is not connected, open Chrome or Edge with the omnibot extension loaded and keep an HTTP/HTTPS tab open.

## Fallback Discipline

Fallback tiers are for completing operations after better patterns fail. They are not debugging shortcuts.

Tier order:

1. Semantic `find`.
2. `snapshot -i` refs.
3. Selectors.
4. `dom` fallback.
5. `mouse` fallback.
6. `execute-js` fallback.
7. Raw `cdp` fallback.

When entering a lower tier, state why the higher tier failed. After any fallback action, verify with `snapshot`, `get`, `is`, `wait`, or equivalent evidence.

Before `execute-js`, the agent must have native-attempt evidence: the exact `find`/`snapshot`/`click`/`fill`/`scroll`/`get`/`read` commands tried, their result, why they were insufficient, and the post-JS verification command to run. Without that evidence, use a native command instead.

## Debug Evidence

Debugging is for evidence. Fallback is for completing operations.

Use screenshots, annotated screenshots, console logs, network logs, trace, record/replay, and CDP inspection to explain failures or prove state. Do not treat `execute-js` as ordinary debug output.

For a cursor that reappears at an old click point, collect `browser mouse-visual-state --tab-id <TAB_ID>` and a screenshot before retrying the click. The visual cursor is diagnostic overlay state; its position alone does not prove that the old element was clicked again.

## Absolute Prohibitions

- Missing `OMNIBOT_SESSION_TOKEN` or missing `--tab-id` on page-state commands.
- Acting without verify or claiming success without evidence.
- Using `execute-js` first, raw CSS before semantic find, `@eN` across tabs, implicit tab targeting, or shell sleep instead of `omnibot wait`.
- Using JavaScript read/click/scroll shortcuts when native `get`/`read`/`find`/`snapshot`/`click`/`scroll` can express the task.
- Using removed commands: `switch-tab`, `focus-tab`, `tab switch`, `tab focus`. These are no longer available.
- Using `tabs[0]` or the first tab as a target. The first tab is often a user tab or transport tab.
- Closing user tabs discovered during cleanup. Only close tabs created by the current workflow.

See `references/anti-patterns.md` before using shortcuts.
