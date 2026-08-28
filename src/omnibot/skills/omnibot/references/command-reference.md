# Omnibot Command Reference

This is a lookup table, not a behavior guide. Choose behavior from `operation-patterns.md`, use `session-and-tabs.md` for targeting, and use `fallback-operations.md` before dropping to lower tiers.

Unless marked as discovery, runtime, or tab creation, page-state examples assume `OMNIBOT_SESSION_TOKEN=<workflow>` and `--tab-id <TAB_ID>`.

## Runtime & Status

### doctor

Purpose: Check daemon and browser extension health.

```bash
omnibot doctor
```

Preferred pattern: See `runtime-and-status.md#startup-check`.
Fallback relation: Not a fallback command.

### status

Purpose: Show daemon status only (lighter than `doctor`).

```bash
omnibot status
```

Preferred pattern: See `runtime-and-status.md#daemon-lifecycle`.
Fallback relation: Not a fallback command.

### start

Purpose: Start the daemon in the background.

```bash
omnibot start
```

Equivalent to: `omnibot daemon start`

### stop

Purpose: Stop the running daemon.

```bash
omnibot stop
```

Equivalent to: `omnibot daemon stop`

### run

Purpose: Run the daemon in the foreground.

```bash
omnibot run
```

Equivalent to: `omnibot daemon run`

### tabs

Purpose: List connected browser tabs and discover tab ids.

```bash
omnibot tabs
```

Preferred pattern: See `session-and-tabs.md#tab-explicit`.
Fallback relation: Not a fallback command.

### version

Purpose: Print the installed omnibot CLI version. No daemon or extension access required.

```bash
omnibot version
omnibot --version
omnibot -V
```

Output: a single line in the form `omnibot <version>`.
Preferred pattern: See `runtime-and-status.md#version`.
Fallback relation: Not a fallback command.

## Reading

### read

Purpose: Read clean rendered page text/Markdown from an existing tab or a temporary URL tab.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot read --screens 5 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot read --screens 5 --timeout 120 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot read --screens 3 https://example.com/article
OMNIBOT_SESSION_TOKEN=research omnibot read --json --screens 5 --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#read` and `operation-patterns.md#extraction`.
Fallback relation: Prefer for page content. Use `snapshot -i` when the next step is action planning, and `get`/`is`/`wait` for narrow state verification.

### snapshot -i

Purpose: Read accessibility tree and produce actionable `@eN` refs. With `-i`, it includes both interactive refs and visual-region refs marked `[visual=true]` for targeted screenshots.

For visible custom comboboxes, `snapshot -i` may auto-probe options and append `[option]` refs under DOM Popup Controls. These refs remain actionable after the dropdown closes because they carry `openerSelector` internally.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i -c -d 4 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i -s "#main" -u --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#click`, `operation-patterns.md#fill`, and `session-and-tabs.md#ref-scope`.
Fallback relation: Tier 2 after semantic find.

### get

Purpose: Read one value or element state without dumping the page.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot get title --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get text "#main" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get html "#main" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get value "input[name=email]" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get attr "a.login" href --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get count ".item" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get box "#submit" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get styles "#submit" --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#read` and `operation-patterns.md#extraction`.
Fallback relation: Selector tier for reading; escalate only if unavailable.

### is

Purpose: Check element state.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot is visible "#submit" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot is hidden "#spinner" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot is enabled "#submit" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot is checked "#agree" --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#read` and `operation-patterns.md#select--check`.
Fallback relation: Prefer before visual or JavaScript checks.

## Actions

### click

Purpose: Click an element by `@eN` ref or selector.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e4 --new-tab
OMNIBOT_SESSION_TOKEN=checkout omnibot click "button[type=submit]" --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#click`.
Fallback relation: Tier 2 with refs, Tier 3 with selector.

Combobox option refs: if `snapshot -i` shows `@eN [option] "OpenAI Chat"`, prefer `click @eN` over JavaScript fallback. Omnibot will reopen the owning combobox when needed.

Rich text editor refs: if `snapshot -i` shows `@eN [richtext] "..." [contenteditable=true]` under `# DOM Rich Text Editors`, treat it as the article body editor. Use `fill @richtext` to replace the whole body (supports `\n\n` for paragraphs) and `type @richtext` to append. Do not fall back to `execute-js` first.

### dblclick

Purpose: Double-click an element by `@eN` ref or selector.

```bash
OMNIBOT_SESSION_TOKEN=editor omnibot dblclick --tab-id <TAB_ID> @e7
```

Preferred pattern: See `operation-patterns.md#click`.
Fallback relation: Prefer semantic or snapshot first; then selector.

### fill

Purpose: Replace an input value.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot fill --tab-id <TAB_ID> @e2 "a@b.com"
OMNIBOT_SESSION_TOKEN=checkout omnibot fill "input[name=email]" "a@b.com" --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#fill`.
Fallback relation: Tier 2 with refs, Tier 3 with selector.

Rich text body editors (ProseMirror/Quill/Draft.js/Slate/Toutiao article body): if the target is an `@eN [richtext]` ref, `fill` writes through a dedicated contenteditable path that clears the previous body and dispatches `input`/`change` events. Split paragraphs with an empty line:

```bash
OMNIBOT_SESSION_TOKEN=editor omnibot fill --tab-id <TAB_ID> @eN "First paragraph.\n\nSecond paragraph."
```

Raw selector fallback is supported for selectors that look like a rich editor (e.g. `[contenteditable="true"]`, `.ProseMirror`, `.ql-editor`).

### type

Purpose: Type text into an element.

```bash
OMNIBOT_SESSION_TOKEN=search omnibot type --tab-id <TAB_ID> @e3 "omnibot"
```

Preferred pattern: See `operation-patterns.md#fill`.
Fallback relation: Use after fill is not appropriate or focus is needed.

For `@eN [richtext]` article body editors, `type` appends at the cursor position. Click the `@richtext` ref first to focus the editor.

### press

Purpose: Press a key in the target tab.

```bash
OMNIBOT_SESSION_TOKEN=search omnibot press Enter --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#fill` and `operation-patterns.md#wait`.
Fallback relation: Not a fallback by itself; verify after pressing.

### hover

Purpose: Hover an element by ref or selector.

```bash
OMNIBOT_SESSION_TOKEN=menu omnibot hover --tab-id <TAB_ID> @e5
```

Preferred pattern: Observe menu state, hover, then verify visible options.
Fallback relation: Use mouse move only if hover fails.

### focus

Purpose: Focus an element by selector.

```bash
OMNIBOT_SESSION_TOKEN=form omnibot focus "input[name=email]" --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#fill`.
Fallback relation: Selector tier before keyboard/type fallback.

### select

Purpose: Select an option in a dropdown.

```bash
OMNIBOT_SESSION_TOKEN=form omnibot select @e5 "US" --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#select--check`.
Fallback relation: Prefer refs/selectors before JavaScript value changes. For custom comboboxes, first check whether `snapshot -i` exposes auto-probed option refs and click `@option`. For CSS-only dropdowns whose options are still absent or whose refs fail verification, see `fallback-operations.md#css-only-dropdown-javascript-fallback`.

### check / uncheck

Purpose: Set checkbox state.

```bash
OMNIBOT_SESSION_TOKEN=form omnibot check @e6 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot uncheck @e6 --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#select--check`.
Fallback relation: Verify with `is checked` before and after.

### scroll / scrollintoview

Purpose: Scroll page or element.

```bash
OMNIBOT_SESSION_TOKEN=read omnibot scroll down 500 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=read omnibot scroll down 500 --selector "#list" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=read omnibot scrollintoview @e7 --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#read` and `operation-patterns.md#extraction`.
Fallback relation: DOM or mouse scroll only after standard scroll fails.

### drag

Purpose: Drag from one element to another.

```bash
OMNIBOT_SESSION_TOKEN=board omnibot drag @e8 @e9 --tab-id <TAB_ID>
```

Preferred pattern: Observe source and target, drag, verify position/state.
Fallback relation: Mouse drag is Tier 5 if element drag fails.

### upload

Purpose: Attach a local file to an `<input type="file">` element via CDP (`DOM.setFileInputFiles`), with nodeId and JS `DataTransfer` fallbacks.

```bash
OMNIBOT_SESSION_TOKEN=form omnibot upload "input[type=file]" /path/to/file.png --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#upload`.
Fallback relation: The CLI falls back from CDP objectId → CDP nodeId → JS DataTransfer. Do not stack additional JavaScript fallbacks.

### keyboard / keydown / keyup

Purpose: Send keyboard text or key state to the target tab when element-specific `type` or `press` is insufficient.

```bash
OMNIBOT_SESSION_TOKEN=form omnibot keyboard type "hello" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot keyboard inserttext "hello" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot keydown Shift --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot keyup Shift --tab-id <TAB_ID>
```

Preferred pattern: Prefer `fill`, `type`, and `press` first.
Fallback relation: Keyboard commands are a focused fallback before mouse or JavaScript.

`keyboard type` preserves keyboard events and updates the focused editable when the browser does not apply the default text insertion. `keyboard inserttext` inserts text directly and intentionally does not emit per-character key events.

## Semantic Find

Semantic find is Tier 1 for operating by meaning.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot find role button --name "Submit" --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find text "Sign in" --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find label "Email" --action fill --action-value "a@b.com" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find placeholder "Search" --action type --action-value "omnibot" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find testid submit-button --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find nth ".card" 2 --action click --tab-id <TAB_ID>
```

Text-node precision: `find text` walks the DOM text nodes and marks the nearest visible container of the matching text, not the first ancestor whose `textContent` happens to include the needle. The matched offset/length is stored on the element, so `--action click` positions the mouse at the end of the matched text. Inside a `contenteditable` body (ProseMirror/Quill/etc.), the selection is collapsed right after the matched text and the editor is focused, so a follow-up image insertion lands at the intended paragraph instead of the editor root.

Preferred pattern: See `operation-patterns.md#click` and `operation-patterns.md#fill`.
Fallback relation: Tier 1. Explain failure before using refs, selectors, DOM, mouse, JavaScript, or CDP.

## Fallback Actions

### mouse

Purpose: Coordinate-based mouse operations.

All coordinate mouse operations are mirrored in the connected extension's
visible page: a cursor, movement trail, pressed state, drag path, and click
wave are shown at the same viewport coordinates as the dispatched input. The
visual layer is best-effort and never changes whether the underlying action
succeeds. It is recreated after a page reload when the last mouse position is
known.
Usage tier: Tier 5 fallback only.

> **Development status:** The realistic trajectory mode (`mouse drag` without `--fast`) is experimental and has not been validated in production workflows. The trajectory parameters, step count, and timing are still being tuned. Use `--fast` for stable linear drags until the realistic mode is proven.

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot mouse click --x 100 --y 200 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot mouse click --x 100 --y 200 --click-count 2 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot mouse move --x 50 --y 60 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot mouse scroll --x 100 --y 200 --dy 500 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot mouse drag --from-x 10 --from-y 20 --to-x 100 --to-y 200 --tab-id <TAB_ID>
```

`mouse drag` uses a realistic multi-step trajectory by default (70-110 interpolated points with easing, jitter, overshoot, and short random pauses). **This mode is experimental and not yet production-ready.** Optional tuning flags:

```bash
omnibot mouse drag --from-x 633 --from-y 733 --to-x 706 --to-y 733 --duration-ms 700 --steps 90 --jitter 1 --overshoot 2 --tab-id <TAB_ID>
```

Use `--fast` for the old linear 4-event drag (stable, recommended for production):

```bash
omnibot mouse drag --from-x 0 --from-y 0 --to-x 100 --to-y 0 --fast --tab-id <TAB_ID>
```

Preferred pattern: See `fallback-operations.md#mouse-fallback`.
Fallback relation: After semantic, refs, selector, and DOM fail.

### verify

Purpose: Inspect human-verification (captcha) widgets. Returns structured metadata (provider, type, action type, element boxes, coordinate mapping, and an optional panel screenshot) for an agent to solve. Does not solve captchas itself.

> **Development status:** This command is experimental and in active development. It is not production-ready. Known limitations:
> - Only NetEase Yidun (网易易盾) is supported; other captcha providers are not detected.
> - DOM-based classification (`yidun_classes`) is best-effort and may report wrong types on newer widget versions.
> - The `coordinate_map` panel-image-to-viewport scale assumes `Page.captureScreenshot` returns DPR-scaled device pixels; this has not been validated across all DPR and viewport combinations.
> - Success/failure state detection (`state` field) from DOM classes is unreliable; always cross-check with a visual screenshot.
> - There is no built-in captcha solver. External vision-model-based solving (e.g. via `--solver-command`) has shown insufficient accuracy for production-grade captcha solving on jigsaw-type captchas.
> - Do not rely on this command for automated captcha bypass in production workflows.

```bash
OMNIBOT_SESSION_TOKEN=verify omnibot verify inspect --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=verify omnibot verify inspect --tab-id <TAB_ID> --no-image
```

The agent workflow for slider captchas (experimental, not validated for production):
1. `verify inspect` → get type, coordinate_map, panel image
2. Vision model identifies the gap/target position in the image
3. Convert panel screenshot coordinates to viewport coordinates using `coordinate_map.panel_image_to_viewport_scale_x/y`
4. `mouse drag` from slider handle to target
5. `verify inspect` or `screenshot` to verify result

For click-sequence captchas (text/icon click):
1. `verify inspect` → get click area and image
2. Vision model identifies target coordinates in the image
3. Convert and execute `mouse click` for each target

Batch scoring harness for NetEase Yidun trial pages (test-only):

```bash
python3 tests/verify_workflow_matrix_test.py --iterations 50
python3 tests/verify_workflow_matrix_test.py --case jigsaw --iterations 50 --solver-command './solver.py'
```

Without `--solver-command`, the harness performs inspect-only sampling and saves panel images. With a solver command, it executes returned `drag` / `click` actions and writes JSON/TXT score reports.

### dom

Purpose: Interact with visible DOM node ids returned by `dom visible`.
Usage tier: Tier 4 fallback only.

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot dom visible --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot dom click n1 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot dom dblclick n1 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot dom scroll n1 --dy 800 --tab-id <TAB_ID>
```

Preferred pattern: See `fallback-operations.md#dom-fallback`.
Fallback relation: After selector failure and before mouse fallback.

### execute-js

Purpose: Run arbitrary JavaScript in the page.
Usage tier: Tier 6 fallback only. Do not use first.

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot execute-js "return window.appState?.status" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot execute-js --file /tmp/repair.js --tab-id <TAB_ID>
```

Preferred pattern: See `fallback-operations.md#javascript-fallback`.
Fallback relation: After semantic, refs, selector, DOM, and mouse are insufficient. Valid examples include CSS-only dropdowns where the trigger exists but option refs are absent from `snapshot -i`.

### cdp

Purpose: Send raw Chrome DevTools Protocol commands.
Usage tier: Tier 7 fallback and inspection only.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot cdp Runtime.evaluate '{"expression":"document.title"}' --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot cdp DOM.getDocument '{"depth":1}' --tab-id <TAB_ID>
```

Preferred pattern: See `fallback-operations.md#raw-cdp-fallback` and `debugging-and-evidence.md#cdp-inspection`.
Fallback relation: Last resort.

## Navigation & Tabs

### navigate / open / goto

Purpose: Navigate or open pages. New-tab forms return a tab id. Same-tab navigation requires an explicit target tab id. There is no CLI current-tab state.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot navigate https://example.com
OMNIBOT_SESSION_TOKEN=research omnibot navigate https://example.com --same-tab --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot open https://example.com
OMNIBOT_SESSION_TOKEN=research omnibot goto https://example.com --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#navigation` and `session-and-tabs.md#tab-explicit`.
Fallback relation: Verify with `get url --tab-id <TAB_ID>` before continuing.

Safety rule: treat `open` and `tab new` as the only new-tab commands. Never replace a requested new-tab operation with `goto`, plain `navigate`, or an active-tab action. Use `goto --tab-id` or `navigate --same-tab --tab-id` only when reusing an explicitly selected existing tab, and verify the returned tab's URL before mutating page state.

### close / back / forward / reload / pushstate

Purpose: Change tab lifecycle or history state.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot close <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot back --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot forward --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot reload --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot pushstate /dashboard --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#navigation`.
Fallback relation: Verify URL or page state after the action.

### tab

Purpose: Manage browser tabs.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot tab list
OMNIBOT_SESSION_TOKEN=research omnibot tab new https://docs.example.com --label docs
OMNIBOT_SESSION_TOKEN=research omnibot tab close docs
```

Preferred pattern: See `session-and-tabs.md#tab-explicit`.
Removed: `tab switch` and `tab focus` are no longer available. Use explicit `--tab-id` on every page-state command.

### window / frame

Purpose: Manage windows and frames.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot window new
OMNIBOT_SESSION_TOKEN=research omnibot frame "#payment-frame" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get attr @e12 src --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot frame "entity.jsf?" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot frame main --tab-id <TAB_ID>
```

`frame` targets an iframe by id, name, title, or matching source URL. Targets are absolute for the tab and matching recursively covers nested descendant frames; use a unique source substring when a selected child snapshot exposes another `[Iframe]`. `frame iframe` usually selects the first match. Use `frame main` before reading host-page state; `main` is a reserved host alias and does not select an iframe with `id="main"`.

## Waiting & Batch

### wait

Purpose: Wait for time, selector, text, URL, load state, or JavaScript condition.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot wait "#ready" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait "#spinner" --state hidden --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --text "Welcome" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --url "/dashboard" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --load --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --load domcontentloaded --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --load networkidle --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --fn "window.appReady === true" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait 500 --tab-id <TAB_ID>
```

Bare `--load` defaults to the `load` lifecycle state. A successful lifecycle
wait does not verify the final route or business state; follow it with `get url`
or a targeted `get`/`is` check.

Preferred pattern: See `operation-patterns.md#wait`.
Fallback relation: Prefer condition waits over shell sleep. Fixed-time waits like `wait 500` are diagnostic or last resort only.

### batch

Purpose: Send short extension/CDP command arrays as JSON or from a file. Batch is not a wrapper for normal CLI commands such as `snapshot` or `click`.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot batch '[{"cmd":"cdp","method":"Runtime.evaluate","params":{"expression":"document.title","returnByValue":true}}]' --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot batch --file /tmp/omnibot-batch.json --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#batch`.
Fallback relation: Not a substitute for verification.

## Debugging

### screenshot

Purpose: Capture visual evidence from a browser tab.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot screenshot --tab-id <TAB_ID> -o /tmp/omni-shot.png
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot screenshot --ref @e146 --tab-id <TAB_ID> -o /tmp/omni-region.png
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot screenshot --annotate --tab-id <TAB_ID> -o /tmp/omni-annotated.png
```

Without `--ref`, screenshot captures the current viewport. `--ref` accepts a visual ref marked
`[visual=true]`, such as `[article]`, `[region]`, `[dialog]`, `[listitem]`, `[image]`, or `[video]`.
Do not use ordinary button/link/textbox refs as standalone screenshot targets. Re-run `snapshot -i`
after scrolling or `read` before using a ref that may be stale.
Successful file output includes `url`, `title`, `viewport`, and `bytes`. Treat
those fields as the identity of the pixels actually captured; do not infer page
identity from the output filename or the URL requested by an earlier `goto`.
Require `bytes > 0`. Prefer this returned value over `wc`; if a macOS diagnostic
must call it, the portable absolute location is `/usr/bin/wc`, not `/bin/wc`.

Preferred pattern: See `debugging-and-evidence.md#screenshot`.
Fallback relation: Evidence collection, not operation fallback.

### console

Purpose: Read or clear browser console evidence.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot console logs --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot console errors --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot console clear --tab-id <TAB_ID>
```

Preferred pattern: See `debugging-and-evidence.md#console`.
Fallback relation: Evidence collection, not operation fallback. `console errors` currently uses the console log collection path; verify level filtering in output before treating it as error-only evidence.

### dialog

Purpose: Read, clear, or handle native browser JavaScript dialogs (`alert`, `confirm`, `prompt`).

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot dialog logs --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot dialog clear --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot dialog handle accept --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot dialog handle dismiss --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot dialog handle accept --text "prompt text" --tab-id <TAB_ID>
```

Preferred pattern: Use `dialog logs` or `dialog clear` before triggering a browser-native dialog so the extension has debugger capture ready. Trigger through normal page actions when possible; use `execute-js` only when the task is explicitly to test a native JS dialog.
Fallback relation: Evidence and dialog handling, not a general page-operation fallback.

### network

Purpose: Capture and inspect CDP Network events buffered by the Omnibot browser extension.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot network clear --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot network start --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot network stop --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot network logs --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot network summary --tab-id <TAB_ID>
```

Raw `cdp Network.enable` is not a substitute for `network start` because raw `cdp` does not by itself expose a persistent event log to the agent.

Preferred pattern: See `debugging-and-evidence.md#network-capture`.
Fallback relation: Evidence collection, not operation fallback.

## Browser Capabilities

### clipboard

Purpose: Read or write browser clipboard.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot clipboard read --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot clipboard write "text" --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#extraction`.
Fallback relation: Use only when clipboard is part of the browser task.

### viewport

Purpose: Read or set viewport size.

```bash
OMNIBOT_SESSION_TOKEN=visual omnibot viewport get --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=visual omnibot viewport set 1280 720 --tab-id <TAB_ID>
```

Preferred pattern: Set explicit viewport before visual verification if layout matters.
After `viewport set`, navigate or reload as required by the application, then
verify `get url` before capture. Authentication redirects and backend restarts
can otherwise produce a valid screenshot of a different page. Confirm the
screenshot response `url` and `title` as final evidence.
Fallback relation: Not a fallback command.

### assets

Purpose: List or export page resources.

```bash
OMNIBOT_SESSION_TOKEN=extract omnibot assets list --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=extract omnibot assets export -o /tmp/assets.zip --tab-id <TAB_ID>
```

Preferred pattern: See `operation-patterns.md#extraction`.
Fallback relation: Use after page content indicates assets are needed.

## Visibility & Sessions

### visibility

Purpose: Inspect or set automation browser visibility mode. `visibility launch` currently reports planned configuration only; it does not launch a browser.

```bash
omnibot visibility status
omnibot visibility set background
omnibot visibility set visible
omnibot visibility launch headless --user-data-dir /tmp/omnibot-headless
```

Preferred pattern: See `session-and-tabs.md#visibility`.
Fallback relation: Headless does not inherit existing user login state. Treat `visibility launch` status `planned` as not launched.

### browser

Purpose: Manage browser runtime ownership.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot browser list
OMNIBOT_SESSION_TOKEN=research omnibot browser current
OMNIBOT_SESSION_TOKEN=research omnibot browser claim 123
OMNIBOT_SESSION_TOKEN=research omnibot browser release 123
```

Preferred pattern: See `session-and-tabs.md#browser-claimrelease`.
Fallback relation: Use in multi-browser or multi-runtime scenarios.

### session

Purpose: Name or list Omnibot workflow context state for the current `OMNIBOT_SESSION_TOKEN`. This does not switch tabs, preserve login, or replace `--tab-id`.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot session name "checkout"
OMNIBOT_SESSION_TOKEN=checkout omnibot session list
```

Preferred pattern: See `session-and-tabs.md#session-first`.
Fallback relation: Not a fallback command.

## Recording & Trace

### record / replay / trace

Purpose: Capture, replay, or trace workflows for evidence.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot record start
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot record stop -o flow.json
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot replay flow.json
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot trace start
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot trace stop -o trace.zip
```

Preferred pattern: See `debugging-and-evidence.md#record-and-replay` and `debugging-and-evidence.md#trace`.
Fallback relation: Evidence collection, not operation fallback.

## Skills

### skills install / skills path

Purpose: Install packaged omnibot skills or show the packaged skills path.

```bash
omnibot skills install --agent hermes --profile nuwa
omnibot skills install --agent opencode
omnibot skills install --agent claude
omnibot skills install --agent codex
omnibot skills install --agent openclaw
omnibot skills install --agent workbuddy
omnibot skills install --agent trae
omnibot skills path
```

Preferred pattern: See `runtime-and-status.md#skills-path`.
Fallback relation: Not a fallback command.

