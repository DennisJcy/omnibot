# Workflow Context and Tabs

Workflow context tokens and tab ids are core reliability concepts, not advanced usage.

## Context First

`OMNIBOT_SESSION_TOKEN` is mandatory for every workflow. It is a workflow/context token, not a browser session, login session, or tab target.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot tabs
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
```

The same token keeps one workflow isolated. Different tokens prevent independent agents from sharing refs, trace, recording, temporary resources, and other workflow state.

## Tab Explicit

`--tab-id <TAB_ID>` is mandatory for every page-state command.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=checkout omnibot get url --tab-id <TAB_ID>
```

Do not rely on default tab, active tab, current tab, or previous targeting state.

## Explicit Targeting Model

Page-state commands never infer a target tab. Always pass `--tab-id <TAB_ID>` for commands that read or mutate page state.

Transport selection is internal. Omnibot may use any connected extension WebSocket to deliver extension-level commands, but that transport tab is never the page target.

Do not use the first returned tab, `tabs[0]`, browser active tab, newest tab, or prior command state as a target.

## Transport Is Not Target

Omnibot can send extension commands through any connected extension WebSocket tab. That transport tab is not the page target. The target is only the tab id passed in the command, for example `--tab-id edge-client:123`.

Safe sequence:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot navigate https://example.com
# Save the returned full tab id exactly, for example edge-client:123.
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id edge-client:123
OMNIBOT_SESSION_TOKEN=research omnibot click --tab-id edge-client:123 @e4
OMNIBOT_SESSION_TOKEN=research omnibot wait --text "Saved" --tab-id edge-client:123
```

Unsafe sequence:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot tabs
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i
```

The unsafe sequence has no target. Do not infer target from first tab, active tab, or prior operation.

## Safe Browser Test Cleanup

Browser integration tests must only close tabs they created:

1. Record the list of existing tabs before creating fixtures.
2. Create a unique fixture tab per case.
3. Store the returned full tab id.
4. Pass that id to every page-state command.
5. Close only stored fixture ids in cleanup.
6. Verify user tabs remain present after the test.

## Why Both

- Workflow context token = agent/workflow state isolation.
- Tab ID = page targeting.

The workflow token alone does not prove which page receives a command. Tab ID alone does not isolate concurrent agents. Use both.

## Ref Scope

`@eN` refs are tab-scoped.

Never reuse `@eN` across tabs. Never assume a ref remains valid after navigation, reload, major DOM changes, or a different snapshot.

```bash
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=checkout omnibot click --tab-id <TAB_ID> @e4
OMNIBOT_SESSION_TOKEN=checkout omnibot snapshot -i --tab-id <TAB_ID>
```

## Multi-Agent Pattern

Agent A:

```bash
OMNIBOT_SESSION_TOKEN=research
```

Agent B:

```bash
OMNIBOT_SESSION_TOKEN=checkout
```

Agent C:

```bash
OMNIBOT_SESSION_TOKEN=debug-checkout
```

Each agent must:

1. Set a stable token.
2. Discover or create a tab.
3. Save the tab id.
4. Pass `--tab-id <TAB_ID>` on every page-state command.
5. Run `snapshot` -> action -> verify, or `get/is` -> action -> `get/is`.

Example:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot tab new https://example.com --label research
OMNIBOT_SESSION_TOKEN=research omnibot get url --tab-id <TAB_ID>
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
```

## No Implicit Targeting

Omnibot does not provide a workflow-level current tab command. Every command that reads or changes page state must receive `--tab-id <TAB_ID>` in that command invocation.

This prevents stale target state and cross-agent tab confusion.

## browser claim/release

Use `browser claim` and `browser release` in multi-browser or multi-runtime scenarios where an agent must explicitly own or release a browser tab.

```bash
OMNIBOT_SESSION_TOKEN=research omnibot browser list
OMNIBOT_SESSION_TOKEN=research omnibot browser current
OMNIBOT_SESSION_TOKEN=research omnibot browser claim 123
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id 123
OMNIBOT_SESSION_TOKEN=research omnibot browser release 123
```

Claiming does not replace `--tab-id`. It only documents or coordinates ownership.

## visibility

Visibility controls where automation is intended to run:

- `visible`: controls the user's already-open real browser tabs and preserves visible session state.
- `background`: avoids foregrounding tabs unless requested.
- `dedicated-profile`: planned separate-profile mode.
- `headless`: planned headless browser context.
- `launch`: currently reports planned configuration only; it does not launch a browser.

Examples:

```bash
omnibot visibility status
omnibot visibility set visible
omnibot visibility set background
omnibot visibility launch headless --user-data-dir /tmp/omnibot-headless
```

Headless and dedicated-profile modes do not automatically share the user's current tabs or login state. Because `visibility launch` is currently planned-only, verify actual browser availability with `doctor` and `tabs` before assuming access.
