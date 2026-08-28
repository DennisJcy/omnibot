# Debugging and Evidence

Debugging is for evidence. Fallback is for completing operations.

Use this file when you need to prove browser state, explain a failure, or collect artifacts for review. Do not use `execute-js` as the first debug tool.

Use a unique workflow/debug token per task, such as `debug-checkout` or `debug-research`. Do not share one global `debug` token across independent agents.

## Screenshot

Use screenshots when visual layout, canvas, dialogs, or visual regressions matter.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot screenshot --tab-id <TAB_ID> -o /tmp/omni-shot.png
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot screenshot --annotate --tab-id <TAB_ID> -o /tmp/omni-annotated.png
```

Prefer text extraction when text is enough. Screenshot is evidence, not extraction.

For file output, inspect the successful JSON response:

- `bytes` must be greater than zero and is the authoritative completed file size.
- `url` and `title` identify the page whose pixels were captured.
- `viewport` identifies the final capture dimensions.

Do not infer page identity from the filename or from an earlier `goto`.
Authentication redirects, backend restarts, and tab reuse can produce a valid
image of a different page. Prefer the returned `bytes` over a separate shell
file-size check. If a diagnostic script must use `wc` on macOS, use
`/usr/bin/wc -c`; `/bin/wc` is not portable there.

Screenshot capture already waits for stable paint and durable file completion.
If the result is still visually stale or blurred, compare a second bounded
capture and verify `get url`, `title`, and the relevant DOM state rather than
assuming that another fixed sleep will repair it.

## Mouse Visual State

Use the read-only mouse bridge diagnostic plus a screenshot when the visible Omnibot cursor is missing, stale, or appears again at an older click point:

```bash
OMNIBOT_SESSION_TOKEN=debug-cursor omnibot browser mouse-visual-state --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-cursor omnibot screenshot --tab-id <TAB_ID> -o /tmp/omni-cursor.png
```

Check `host`, `shadowRoot`, `pointer`, `assetComplete`, and `pointerOpacity`. Do not infer that the page received another click from the overlay position alone. Verify the page with `get`, `snapshot`, or a business-state condition before retrying any mutation.

## Console

Use console logs for runtime JavaScript errors, frontend warnings, or app-level diagnostics.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot console errors --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot console logs --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot console clear --tab-id <TAB_ID>
```

Collect console diagnostics before and after the action when debugging regressions. `console errors` currently uses the console log collection path; verify level filtering in output before treating it as error-only evidence.

## Network

Use network logs for failed requests, redirects, blocked assets, API errors, or loading stalls.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot network summary --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot network logs --tab-id <TAB_ID>
```

Pair network evidence with page verification:

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot get text "#main" --tab-id <TAB_ID>
```

## Network Capture

Use this when the user asks to capture API requests, checkout requests, submit requests, redirect chains, or CDP/network evidence around a specific browser action.

Required order:

1. Discover the tab id with `omnibot tabs`.
2. Verify network command syntax with `omnibot network --help` and `omnibot network start --help` if this is the first network operation in the session.
3. Clear old logs.
4. Start capture.
5. Perform exactly one browser action.
6. Verify the page state changed.
7. Stop capture.
8. Read logs and summary.
9. Report host, path, method, status, initiator, and non-sensitive payload shape. Do not reveal cookies, auth headers, full addresses, full phone numbers, payment data, or final order submission tokens.

Example:

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot tabs
OMNIBOT_SESSION_TOKEN=checkout omnibot network clear --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot network start --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e12
OMNIBOT_SESSION_TOKEN=checkout omnibot wait --url "/checkout" --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot network stop --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot network summary --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot network logs --tab-id <TAB_ID>
```

If `network logs` returns an extension capability error, report that Omnibot needs the newer browser extension and fall back to `cdp Page.getNavigationHistory` plus `get url` for navigation evidence.

## Trace

Use trace for a reproducible artifact around a failing workflow.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot trace start
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot trace stop -o trace.zip
```

Trace is evidence. It does not replace operation verification.

## Record and Replay

Use record/replay when a flow must be captured or reproduced.

When a user asks for a complete recording or trace workflow, treat `start` as an
internal setup step: continue with the requested browser actions, run the
matching `stop -o <path>`, verify the artifact exists and contains events, and
only then report the result. Do not stop after `record start` or `trace start`
to ask what should be recorded when the user already specified the workflow.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot record start
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot record stop -o flow.json
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot replay flow.json
```

After replay, verify final state:

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot get url --tab-id <TAB_ID>
```

## CDP Inspection

Use CDP for low-level inspection when normal evidence is insufficient.

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot cdp Runtime.evaluate '{"expression":"document.title"}' --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=debug-checkout omnibot cdp DOM.getDocument '{"depth":1}' --tab-id <TAB_ID>
```

CDP inspection is not a first-choice operation path. If CDP changes state, it becomes Tier 7 fallback and must follow `fallback-operations.md#raw-cdp-fallback`.

## Evidence Checklist

Before reporting a browser issue, collect the smallest evidence set that explains it:

- Runtime: `doctor`, `tabs`, `visibility status`.
- Page state: `get`, `is`, `snapshot`, or `wait`.
- Visual proof: `screenshot --annotate` only if visual state matters.
- Browser diagnostics: `console errors` and `network summary`.
- Reproduction artifact: `trace` or `record` when the flow is unstable.
