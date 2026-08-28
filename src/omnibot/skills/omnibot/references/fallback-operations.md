# Fallback Operations

Fallback is for completing operations after preferred patterns fail. It is not debugging. Debugging collects evidence; fallback changes page state.

Every fallback escalation must answer two questions:

- Which higher tier failed, and why?
- How will the result be verified?

Before using `execute-js`, the answer must include native-attempt evidence:

- The native command path already tried (`find`, `snapshot -i`, `click`, `fill`, `scroll`, `get`, `read`, `wait`, `dom`, or `mouse`).
- The observed failure or missing state.
- Why the next native tier is insufficient.
- The exact post-JS verification command.

If the task is normal page identity, text extraction, click, scroll, fill/type, or wait, and you do not have that evidence, go back to `operation-patterns.md#native-first-decision-gate`.

## Fallback Tier Model

### Tier 1 Semantic

Use semantic intent first:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot find role button --name "Submit" --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find text "Sign in" --action click --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find label "Email" --action fill --action-value "a@b.com" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find placeholder "Search" --action type --action-value "omnibot" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot find testid submit-button --action click --tab-id <TAB_ID>
```

Verify:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
```

### Tier 2 Snapshot Refs

Use refs when semantic targeting is missing or ambiguous.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
```

Refs are tab-scoped. Never reuse `@eN` across tabs or after large DOM changes without a fresh snapshot.

## Selector Fallback


### Tier 3 Selector

Use selectors only after semantic find and refs are unavailable or unreliable.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot click "button[type=submit]" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot fill "input[name=email]" "a@b.com" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot focus "input[name=email]" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot get value "input[name=email]" --tab-id <TAB_ID>
```

Verify with `get`, `is`, `wait`, or `snapshot`.

## DOM Fallback

### Tier 4 DOM

Use DOM node fallback when selectors exist but standard commands fail due overlays, custom event routing, or unstable selectors.

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot dom visible --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot dom click n1 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot dom dblclick n1 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot dom scroll n1 --dy 800 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot snapshot -i --tab-id <TAB_ID>
```

Do not use `dom` as the first click path. It bypasses higher-level intent and can target the wrong node if the visible-node list changes.

## Mouse Fallback

### Tier 5 Mouse

Use coordinate mouse operations only when element-based actions cannot reach the target.

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot get box "#canvas-button" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot mouse click --x 100 --y 200 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot snapshot -i --tab-id <TAB_ID>
```

Other mouse operations:

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot mouse move --x 50 --y 60 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot mouse scroll --x 100 --y 200 --dy 500 --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot mouse drag --from-x 10 --from-y 20 --to-x 100 --to-y 200 --tab-id <TAB_ID>
```

Mouse fallback is fragile across viewport size, scroll position, and responsive layouts. Verify immediately.

## JavaScript Fallback

### Tier 6 JavaScript

Do not use `execute-js` first.

Do not use JavaScript as a shortcut for native commands:

| Shortcut | Native command instead |
| --- | --- |
| `return document.title` / `location.href` | `get title`, `get url` |
| `document.body.innerText` | `read --screens N`, `get text` |
| `querySelector(...).click()` | `find ... --action click`, `click @eN`, `click selector` |
| `.value = ...` or `innerHTML = ...` | `fill`, `type`, richtext refs |
| `window.scrollTo` / `scrollIntoView()` | `scroll`, `scrollintoview`, `dom scroll`, `mouse scroll` |

Use `execute-js` only when:

- Semantic find fails.
- Snapshot refs are unstable.
- CSS selector operation fails.
- DOM fallback fails.
- A complex frontend event must be triggered.
- A CSS-only dropdown or hover menu requires an atomic open-then-select sequence, and `snapshot -i` confirms the option nodes are absent from the accessibility tree.
- Runtime state cannot be read through `read`, `snapshot`, `get`, or `is`.

Rich text article body editors (`@eN [richtext]`, `.ProseMirror`, `.ql-editor`, `[contenteditable="true"]`) have native `fill`/`type` support. Do not fall back to JavaScript for richtext writes; use `fill @richtext "..."` first.

Read-only JavaScript fallback:

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot execute-js "return window.appState?.status" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot get text "#status" --tab-id <TAB_ID>
```

Input JavaScript fallback must trigger real browser events:

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot execute-js "const el=document.querySelector('input[name=email]'); el.value='a@b.com'; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); return el.value;" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot get value "input[name=email]" --tab-id <TAB_ID>
```

Click JavaScript fallback should call the element click only after higher tiers fail:

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot execute-js "document.querySelector('button[type=submit]')?.click(); return true;" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot wait --url "/dashboard" --tab-id <TAB_ID>
```

### CSS-only dropdown JavaScript fallback

Use CSS-only dropdown JavaScript fallback only after auto-probed refs are absent or fail verification. First run `snapshot -i`; if it lists `[option]` refs, click the option ref directly. If the ref fails, re-observe once, then escalate.

Use this only after the trigger is known and higher tiers failed: semantic `find` clicked the trigger or found the text, `snapshot -i` could not expose option refs, selector/DOM/mouse could not complete the two-step interaction, and verification showed the selection did not change.

Use a short `execute-js --file` script and verify the user-visible result, not just `{ ok: true }`: selected label, sorted result order, result count, URL/query state, or another page-specific condition.

Detailed recipe: `css-only-dropdown-js.md`.

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot execute-js --file /tmp/omnibot-css-dropdown.js --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot snapshot -i --tab-id <TAB_ID>
```

Prefer `--file` for longer scripts:

```bash
OMNIBOT_SESSION_TOKEN=repair omnibot execute-js --file /tmp/omnibot-repair.js --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=repair omnibot snapshot -i --tab-id <TAB_ID>
```

## Raw CDP Fallback

### Tier 7 Raw CDP

Raw CDP is the last resort. Use it only when standard commands and JavaScript fallback cannot complete or inspect the task.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot cdp Runtime.evaluate '{"expression":"document.title"}' --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot cdp DOM.getDocument '{"depth":1}' --tab-id <TAB_ID>
```

After CDP fallback, verify using normal Omnibot reads whenever possible:

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot get title --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot snapshot -i --tab-id <TAB_ID>
```

CDP can bypass application-level event semantics. Treat it as expert-only infrastructure access.

After any fallback succeeds unexpectedly, immediately verify page state with `get url`, `snapshot -i`, or `wait`. Do not continue assuming the previous page is still active.
