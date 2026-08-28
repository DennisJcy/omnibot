# Operation Patterns

Use this file to choose behavior by task. Every page-state workflow must set `OMNIBOT_SESSION_TOKEN=<workflow-name>` and pass `--tab-id <TAB_ID>` on each page-state command.

## Native-First Decision Gate

Use native Omnibot commands for normal browser operations. Treat `execute-js` as a repair tool only after native attempts fail with evidence.

| If you need to... | Use first | JS shortcut to avoid |
| --- | --- | --- |
| Know where you are | `get title`, `get url` | `return document.title`, `location.href` |
| Read visible or rendered content | `read`, `get text`, `get html`, `get attr`, `get count` | `document.body.innerText` |
| Click a control | `find ... --action click`, `snapshot -i` + `click @eN`, `click selector` | `querySelector(...).click()` |
| Scroll | `scroll`, `scrollintoview`, `dom scroll`, `mouse scroll` | `window.scrollTo`, `scrollIntoView()` |
| Enter text | `find ... --action fill`, `fill`, `type` | `.value = ...`, `innerHTML = ...`, `keyboard`, `press` |

If a page task can be phrased as click, fill, type, press, scroll, wait, read, get, or is, use that command. Do not translate user-visible actions into JavaScript unless the fallback file says the higher tiers have failed.

Text versus keys: `fill`/`type` are the only native commands for inserting text and dispatching the page's input events. Use `press`/`keyboard` only for a key such as Enter, Escape, Tab, arrows, or a shortcut; raw keydown/keyup events do not guarantee that a focused text control receives characters.

## Read

### When to use

Use Read when the agent needs clean rendered page content: article text, search results, feed items, long pages, lazy-loaded text, or a human-readable summary source.

Use targeted state commands when the agent needs one value, visibility, enabled/checked state, layout box, or computed styles. Use `snapshot -i` when the agent needs current visible UI structure for deciding the next action.

### Preferred sequence

1. `read --tab-id <TAB_ID>` for clean page text on an existing tab.
2. `read --screens N --tab-id <TAB_ID>` for longer or lazy-loaded pages.
3. `read <URL>` when opening a temporary tab only for reading that URL.
4. `get title/url/text/html/value/attr/count/box/styles` for narrow evidence.
5. `is visible/hidden/enabled/checked` for boolean state.
5. `snapshot -i` when actionable refs are needed.
6. `dom visible` or `execute-js` fallback only after standard reads cannot access the state.

### Example

```bash
OMNIBOT_SESSION_TOKEN=research omnibot read --screens 5 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot read --screens 3 https://example.com/article
OMNIBOT_SESSION_TOKEN=research omnibot get title --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
```

Do not use `execute-js "return document.title + location.href"` or `execute-js "return document.body.innerText"` for normal page detection or text extraction. Use `get` or `read`; they are the native evidence path.

Legacy Java/JSF pages may contain multiple `body` elements or several layout tables before the business table. `read` selects the content-rich body; do not replace it with `document.body.innerText` merely because the first body is empty. A broad `get html "table"` returns the first match, so use a table ref from `snapshot -i` or a unique table id when the page contains layout tables.

### Verification

Use the narrowest read that proves the claim:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot get title --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot is visible "#main" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot is hidden "#spinner" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get count ".result" --tab-id <TAB_ID>
```

### Fallback entry point

If `read` or targeted reads omit needed runtime state, go to `fallback-operations.md#fallback-tier-model`. Start with DOM fallback before JavaScript.

## Click

### When to use

Use Click for buttons, links, menu items, cards, checkouts, modal actions, and any user-like click target.

### Preferred sequence

1. `find role/text/testid --action click`
2. `snapshot -i` -> `click @eN`
3. `click selector`
4. `dom click`
5. `mouse click`
6. `execute-js` click
7. `cdp` fallback

### Example

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find role button --name "Submit" --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --url "/dashboard" --tab-id <TAB_ID>
```

If semantic find is ambiguous, use refs from the same tab:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
```

### Verification

Verify the expected state, not just command success:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot is visible ".success" --tab-id <TAB_ID>
```

`find ... --action click`, `click @eN`, and selector clicks own target preparation. For a ref backed by a live DOM node, Omnibot scrolls the correct page or nested scroll container, waits for stable geometry, reacquires the click box, and performs a pointer hit-test before dispatching the click. Do not manually scroll a known target merely because its snapshot box is outside the current viewport.

When returned, `auto_scrolled`, `before_box`, `clicked_box`, and `hit_test` are click evidence. `auto_scrolled=true` means target preparation changed its viewport geometry; `hit_test=true` means the final point was verified to receive pointer events.

### Fallback entry point

If semantic and refs fail, document why and continue at `fallback-operations.md#selector-fallback`.

Do not use `execute-js` for a visible button, link, menu item, tab, card, or modal control until the native click tiers above have failed and you have re-observed the page. A JS `.click()` can bypass pointer events, framework guards, disabled state, overlays, and user-intent safety checks.

### Static-text refs

When `snapshot -i` shows only `StaticText` for a visible control label, do not assume the text ref itself is clickable. Prefer, in order:

1. `find role button --name "<label>" --action click`.
2. `click "text=<label>"`.
3. `get box "text=<label>"` followed by `mouse click <center-x> <center-y>`.
4. CDP/JS fallback only after verifying the semantic and coordinate paths failed.

## Fill

### When to use

Use Fill for text inputs, textareas, search boxes, login fields, form fields where the final value must be controlled, and rich text article body editors (contenteditable ProseMirror/Quill/Draft.js/Slate/Toutiao article body).

### Preferred sequence

1. `find label/placeholder --action fill`
2. `snapshot -i` -> `fill @eN`
3. `fill selector`
4. `focus` + `type`
5. `execute-js` set value and dispatch `input`/`change` events

### Example

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot find label "Email" --action fill --action-value "a@b.com" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot get value "input[name=email]" --tab-id <TAB_ID>
```

With refs:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot fill --tab-id <TAB_ID> @e2 "a@b.com"
OMNIBOT_SESSION_TOKEN=checkout omnibot get value "input[name=email]" --tab-id <TAB_ID>
```

### Password and blank-name textboxes

`snapshot -i` annotates native input types, for example:

```text
@e1 [textbox] [type=text]
@e2 [textbox] [type=password]
```

Use `fill @e2 "<secret>"` even when both AX names are blank. The ref is bound to the exact live input; do not assume that two unnamed textbox roles require a CSS selector. Verify the target type/focus or a non-secret success condition, and do not print the password with `get value` or repeat it in the report. Use `input[type=password]` only as the selector fallback after the ref path fails.

### Rich text article body

For article body editors exposed as `@eN [richtext] "..." [contenteditable=true]` under `# DOM Rich Text Editors`:

```bash
OMNIBOT_SESSION_TOKEN=editor omnibot snapshot -i --tab-id <TAB_ID>
# Body appears under "# DOM Rich Text Editors": @eN [richtext] "..."
OMNIBOT_SESSION_TOKEN=editor omnibot fill --tab-id <TAB_ID> @eN "First paragraph.\n\nSecond paragraph."
OMNIBOT_SESSION_TOKEN=editor omnibot snapshot -i --tab-id <TAB_ID>  # verify body content replaced
```

- `\n\n` splits paragraphs; previous content is cleared.
- `type @richtext " text"` appends at the cursor (click the ref first to focus).
- Do NOT write the article body into a `[textbox]` title field. Title and richtext body are separate refs.

### Verification

Use `get value`, visible validation text, enabled state, or submit readiness:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot get value "input[name=email]" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot is enabled "button[type=submit]" --tab-id <TAB_ID>
```

For richtext bodies, re-run `snapshot -i` and confirm the `@eN [richtext]` name matches the intended content.

### Cursor positioning and inline image insertion

For `contenteditable` article bodies (ProseMirror/Quill/Draft.js/Slate/Toutiao article body), `find text "<anchor phrase>" --action click` collapses the editor selection at the end of the matched phrase and focuses the editor. Use this to place the caret at a specific paragraph before inserting an image, typing, or pressing keys. Do not rely on a bare `click` of the editor followed by `press End`, because the caret would stay on the first line.

Insert an image after a specific paragraph:

```bash
OMNIBOT_SESSION_TOKEN=editor omnibot find text "第二段锚点文字" --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=editor omnibot click ".syl-toolbar-tool.image .syl-toolbar-button" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=editor omnibot wait ".upload-image-panel input[type=file]" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=editor omnibot upload ".upload-image-panel input[type=file]" "/path/to/image.png" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=editor omnibot find role button --name "确定" --action click --tab-id <TAB_ID>
```

Verify the inserted image by counting visible image cards, not raw `<img>` nodes. Toutiao/ProseMirror image cards keep a hidden `<templ>` template and a visible `<mask>` copy of the same `<img>`, so `.ProseMirror img` returns 2 for one logical image. Count the image card container instead (e.g. `.ProseMirror [__syl_tag=true]` or `.ProseMirror .pgc-image`), which reports one per inserted image.

### Fallback entry point

If fill does not update the application state, use `fallback-operations.md#javascript-fallback` only after selector/focus/type attempts fail. JavaScript must dispatch real `input` and `change` events.

Do not use JS `.value = ...`, `innerText`, or `innerHTML` for normal form fields or rich text. Native `fill`/`type` paths already handle events and rich text editor integration.

## Select / Check

### When to use

Use this pattern for dropdowns, comboboxes, checkboxes, toggles, agreement boxes, filters, and boolean controls.

### Preferred sequence

1. Use `snapshot -i` first; visible comboboxes may include auto-probed option refs.
2. Use `click @option` if `snapshot -i` lists auto-probed combobox option refs.
3. Use `select @combobox "value"` for native selects or simple select-like controls.
4. Use `check` / `uncheck` for boolean controls.
5. Verify selected label, value, URL query, result count, or dependent page state.

`snapshot -i` can list options for visible custom comboboxes even though the dropdown closes during observation. These refs are still actionable because Omnibot stores the option's `openerSelector` and can reopen the owning combobox before clicking the option.

### Example

```bash
OMNIBOT_SESSION_TOKEN=form omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot click @e22 --tab-id <TAB_ID>  # @e22 [option] "OpenAI Chat"
OMNIBOT_SESSION_TOKEN=form omnibot get url --tab-id <TAB_ID>
```

Checkbox example:

```bash
OMNIBOT_SESSION_TOKEN=form omnibot is checked "#agree" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot check "#agree" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot is checked "#agree" --tab-id <TAB_ID>
```

### Verification

For checkboxes, verify boolean state. For selects, verify value or dependent page state.

### CSS-only dropdowns and custom menus

Some dropdowns, hover menus, tooltips, and custom selects are CSS-only or portal-based widgets. The visible trigger may be accessible, while the option nodes are hidden `<div>` elements without `role`, accessible name, or stable refs. Start with `snapshot -i`; visible comboboxes may include auto-probed option refs before any manual dropdown opening.

Escalation order:

1. Run `snapshot -i` and look for `[option]` refs near the combobox.
2. If an option ref exists, click the option ref directly and verify.
3. If options are absent, click/hover the trigger once, run `snapshot -i` again, then click the option ref if it appears.
4. If trigger interaction works but options remain absent or option refs fail verification, use `fallback-operations.md#css-only-dropdown-javascript-fallback`.

Do not loop on manual open -> snapshot -> open -> snapshot when `snapshot -i` already lists auto-probed combobox options.

### Fallback entry point

If native select/check fails, use `fallback-operations.md#selector-fallback`. Use JavaScript only if events must be synthesized or if evidence shows a CSS-only multi-step widget cannot be completed through semantic, snapshot, selector, DOM, or mouse tiers.

## Scroll

### When to use

Use Scroll when content, controls, lazy-loaded lists, dropdown panels, or editor areas are off-screen.

Do not use Scroll as a mandatory pre-step for a target that is already represented by a semantic locator, selector, or `@eN` ref. Normal click preparation scrolls that known live target atomically. Use explicit scrolling to discover content that is not yet present in the DOM/snapshot, or when the task itself is scrolling rather than clicking.

### Preferred sequence

1. `scroll down|up|left|right <pixels>` for page scroll.
2. `scroll down|up|left|right <pixels> --selector <container>` for scrollable containers.
3. `scrollintoview @eN` or `scrollintoview selector` for a known target.
4. `dom scroll` when visible DOM node fallback is needed.
5. `mouse scroll` only when element/container scroll commands fail.
6. `execute-js` scroll only after the native tiers fail.

For virtualized lists, infinite feeds, or lazy-rendered content where the target does not exist yet, scroll the relevant container by about 70% of its visible height, take a fresh snapshot, and stop as soon as the target appears. Keep this loop bounded. Once discovered, click the new target normally and let click preparation handle final positioning and hit-testing.

### Example

```bash
OMNIBOT_SESSION_TOKEN=read omnibot scroll down 800 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=read omnibot scrollintoview @e7 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=read omnibot snapshot -i --tab-id <TAB_ID>
```

Do not start with `execute-js "window.scrollTo(...)"` or `element.scrollIntoView()`. Native scroll commands preserve the agent's observe -> act -> verify loop and produce clearer failure modes.

## Navigation

### When to use

Use Navigation to open pages, create tabs, change history, reload, close tabs, move between pages, create windows, or select frames.

### Preferred sequence

1. Create or discover a tab with `tabs`, `tab list`, `tab new`, `open`, or `navigate`.
2. Save the returned tab id.
3. Verify with `get url --tab-id <TAB_ID>`.
4. Run all later page-state commands with `--tab-id <TAB_ID>`.

Do not chain navigation, discovery, and multiple mutations before observing the result. After navigation, verify the URL and snapshot first; then issue one action and verify its state before continuing. Multi-control workflows must use one observe -> act -> verify cycle per control.

### Example

```bash
OMNIBOT_SESSION_TOKEN=research omnibot tab new https://example.com --label research
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
```

History and lifecycle:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot back --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot forward --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot reload --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot wait --load domcontentloaded --tab-id <TAB_ID>
```

Other navigation commands:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot navigate https://example.com
OMNIBOT_SESSION_TOKEN=research omnibot navigate https://example.com --same-tab --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot open https://example.com
OMNIBOT_SESSION_TOKEN=research omnibot goto https://example.com --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot pushstate /dashboard --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot close <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot tab list
OMNIBOT_SESSION_TOKEN=research omnibot tab close research
OMNIBOT_SESSION_TOKEN=research omnibot window new
OMNIBOT_SESSION_TOKEN=research omnibot frame main
```

Iframe workflow:

1. Verify the host tab URL and snapshot first.
2. Set the frame target explicitly, for example `frame #payment-frame --tab-id <TAB_ID>` (an iframe `id`, `name`, `title`, or matching `src` is accepted).
3. Re-observe the child context with `snapshot -i --tab-id <TAB_ID>` before filling or clicking.
4. If that snapshot contains another `[Iframe]`, read its source with `get attr @eN src`, target a unique descendant URL substring such as `frame "entity.jsf?"`, and snapshot again.
5. Perform one child-frame action and verify its child-frame state with `get`, `is`, or `wait`.
6. Return to the host with `frame main --tab-id <TAB_ID>` before reading host-page state.

Frame selection is absolute for the tab, not a relative push into the currently selected frame. Nested same-origin and CDP-visible frames are resolved recursively by id/name/title/src; choose the most specific source substring when parent and child URLs are similar. `frame iframe` normally selects the first matching frame, and `frame main` is a reserved host alias rather than a way to select an iframe whose id is `main`.

Do not assume a host-page selector reaches an iframe. If a child selector returns `null`, establish the frame target and re-observe; for cross-origin frames, report the explicit inaccessible-frame result rather than using JavaScript to bypass it.

Cross-origin caveat: a CDP snapshot may expose remote-frame refs for observation or coordinate actions, but `fill`/`type` may still fail to focus a child control. Verify the child value after every write; if focus fails, report cross-origin text entry as unsupported instead of claiming success or retrying with JavaScript.

### Verification

Always verify the final target:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot wait --load networkidle --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
```

### Fallback entry point

Same-tab navigation must include `--tab-id <TAB_ID>`. If the target tab id is unknown, run `omnibot tabs` first and choose the intended tab explicitly.

## Wait

### When to use

Use Wait after navigation, clicks, form submissions, reloads, dynamic rendering, lazy loading, or any action that changes asynchronous state.

### Preferred sequence

1. Wait for selector visibility or hidden state.
2. Wait for text.
3. Wait for URL.
4. Wait for load state.
5. Wait for a JavaScript condition with `--fn`.
6. Avoid shell sleep.

### Example

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=checkout omnibot wait "#spinner" --state hidden --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --text "Welcome" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot get text "#main" --tab-id <TAB_ID>
```

Other waits:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --url "/dashboard" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --load --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --load domcontentloaded --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --load networkidle --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --fn "window.appReady === true" --tab-id <TAB_ID>
```

Bare `--load` defaults to the browser `load` lifecycle state. An explicit
`domcontentloaded` or `networkidle` value selects that narrower condition.
Load completion is not proof that the requested route, account, or article is
still active: authentication redirects and tab replacement can satisfy the
lifecycle wait on another page. Follow it with `get url` and the smallest
business-state check.

### Verification

After waiting, read the final condition with `get`, `is`, `wait`, or `snapshot`.

### Fallback entry point

If waits time out, collect evidence with `debugging-and-evidence.md`; do not replace them with shell sleep.

## Extraction

### When to use

Use Extraction for retrieving page text, HTML fragments, links, counts, assets, or clipboard data.

### Preferred sequence

1. `get text/html/attr/count` for targeted extraction.
2. `read --screens N` for clean page text, long pages, or lazy-loaded content.
3. `snapshot -i` for structured page observation before action planning.
4. `assets list/export` for resources.
5. `clipboard read` only when clipboard content is part of the task.

### Example

```bash
OMNIBOT_SESSION_TOKEN=extract omnibot get text "#article" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=extract omnibot get attr "a.next" href --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=extract omnibot get count ".result" --tab-id <TAB_ID>
```

Long page example:

```bash
OMNIBOT_SESSION_TOKEN=extract omnibot read --screens 5 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=extract omnibot assets list --tab-id <TAB_ID>
```

### Verification

Verify extraction completeness with expected markers in `read`, element counts, or targeted reads for known selectors.

### Fallback entry point

If content exists only in runtime objects, use `fallback-operations.md#javascript-fallback` after explaining why `read`, `snapshot`, and `get` could not access it.

## Upload

### When to use

Use `omnibot upload` to attach a local file to an `<input type="file">` element. The command speaks CDP (`DOM.setFileInputFiles`) through the extension debugger transport, with a JS `DataTransfer` fallback for pages that reject programmatic file assignment.

### Preferred sequence

1. Observe the upload UI and confirm the task requires a local file.
2. Locate the file input via `snapshot -i` or a CSS selector.
3. Run `omnibot upload <selector> <local-file> --tab-id <TAB_ID>`.
4. Verify the file was accepted (filename, count, enabled submit state, or application-specific confirmation).

### Example

```bash
OMNIBOT_SESSION_TOKEN=form omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot upload "input[type=file]" /path/to/cover.png --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot is enabled "button[type=submit]" --tab-id <TAB_ID>
```

### Verification

Confirm the input accepted the file:

```bash
OMNIBOT_SESSION_TOKEN=form omnibot get attr "input[type=file]" value --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=form omnibot is enabled "button[type=submit]" --tab-id <TAB_ID>
```

### Fallback entry point

The CLI already falls back from CDP `DOM.setFileInputFiles` (by objectId, then nodeId) to a JS `DataTransfer` assignment. Do not add further JavaScript fallbacks on top; file inputs are security-sensitive and page-specific. If all three transports fail, report the failure to the user instead of scripting around it.

## Batch

### When to use

Use Batch for short, known-safe extension/CDP command chains where the target tab and verification are already explicit. Batch is not a wrapper for normal CLI commands such as `snapshot` or `click`.

### Preferred sequence

1. Keep batches short.
2. Include only deterministic operations.
3. Verify after the batch with a separate command.
4. Use `--file` for complex JSON quoting.
5. In shell wrappers, resolve `OMNIBOT_BIN` once and preserve each command's JSON output and exit status until cleanup decisions are complete.

### Example

```bash
OMNIBOT_SESSION_TOKEN=research omnibot batch '[{"cmd":"cdp","method":"Runtime.evaluate","params":{"expression":"document.title","returnByValue":true}}]' --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get title --tab-id <TAB_ID>
```

File example:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot batch --file /tmp/omnibot-batch.json --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
```

Shell-wrapper example:

```bash
OMNIBOT_BIN="$(command -v omnibot)" || exit 1
route_path="/article"
result="$("$OMNIBOT_BIN" wait --url "$route_path" --tab-id "$TAB_ID")"
result_status=$?
printf '%s\n' "$result"
if [ "$result_status" -ne 0 ]; then
  # Inspect error_code before deciding whether to retry or clean up.
  exit "$result_status"
fi
```

Do not use lowercase `path` as a zsh variable and do not send Omnibot output to
`/dev/null` before capturing the status. These shell failures can look like a
browser action that started but never entered its completion path.

### Verification

Do not treat batch success as task success. Verify final page state separately.

### Fallback entry point

Batch is not a fallback tier. If a batched operation fails, re-run the workflow step-by-step and enter the normal fallback model.
