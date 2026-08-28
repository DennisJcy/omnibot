# Runtime and Status

Use this file before troubleshooting. Runtime checks establish whether the daemon, extension, browser, visibility mode, and packaged skills are healthy.

## Startup Check

Run this sequence before diagnosing browser failures:

```bash
omnibot doctor
omnibot status
omnibot tabs
omnibot visibility status
omnibot browser current
```

Interpretation:

- `doctor` checks daemon and extension health.
- `status` checks daemon status only (lighter than `doctor`).
- `tabs` proves connected tabs are visible and provides tab ids.
- `visibility status` shows whether automation is visible, background, dedicated-profile, or headless.
- `browser current` shows current browser runtime ownership.

If the extension is not connected, open Chrome or Edge with the omnibot extension loaded and keep an HTTP/HTTPS page open.

## Shell and Structured Failures

Resolve the installed executable before entering a shell function, sandbox, or
subprocess that may replace `PATH`:

```bash
OMNIBOT_BIN="$(command -v omnibot)" || exit 1
"$OMNIBOT_BIN" doctor
```

In zsh, lowercase `path` is a special array tied to `PATH`. Use names such as
`route_path` or `page_path`; assigning to `path` can remove `omnibot` and even
system tools from command lookup. A `command not found` message is a shell
failure that occurs before the daemon is contacted.

Automation must preserve stdout and the process exit status. Results with
`status: error` or `status: timeout` exit non-zero and include a stable
`error_code`:

- `EXTENSION_DISCONNECTED` — daemon is reachable but the extension transport is disconnected.
- `NO_BROWSER_TABS` — extension is present but no routable page tab is connected.
- `TAB_NOT_FOUND` — the requested tab disappeared or the id is stale.
- `ACTION_TIMEOUT` / `ACTION_FAILED` — the browser action timed out or failed.
- `DAEMON_DISCONNECTED` / `DAEMON_TIMEOUT` — the CLI could not complete its daemon request.
- `CLI_ERROR` — another CLI-level exception occurred.

Do not redirect both output streams away before interpreting the result. A
wrapper that ignores the non-zero exit status can leave its UI or tab group
stuck in an "executing" state instead of entering countdown and cleanup.

Read-only actions may be retried once by the CLI after transient transport
recovery. Same-tab `goto` is also retry-safe. New-tab creation and mutations
such as click, fill, type, select, upload, drag, or close are not replayed;
observe with `tabs`, `get`, `is`, `snapshot`, or `wait` before retrying them.

## Daemon Lifecycle

Top-level shortcuts:

```bash
omnibot status   # Show daemon status
omnibot start    # Start the daemon
omnibot stop     # Stop the daemon
omnibot run      # Run daemon in foreground
```

Full form (also supported):

```bash
omnibot daemon run
omnibot daemon start
omnibot daemon stop
omnibot daemon status
```

## doctor

```bash
omnibot doctor
```

Use `doctor` first when commands fail, tabs are empty, screenshots fail, or the agent cannot reach the browser.

## tabs

```bash
omnibot tabs
```

Use `tabs` to discover tab ids. Save the target tab id and use it on every page-state command:

```bash
OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>
```

## browser list/current

```bash
omnibot browser list
omnibot browser current
```

Use browser status when multiple browser runtimes or agents may be active.

## visibility status

```bash
omnibot visibility status
```

Use visibility status to confirm whether automation should share the user's visible browser state. Headless and dedicated-profile modes do not automatically inherit user login.

## version

```bash
omnibot version
omnibot --version
omnibot -V
```

Use `version` to print the installed omnibot CLI version. Output is a single line in the form `omnibot <version>` with no banner, JSON, or daemon calls. Prefer this over `omnibot --help` or `doctor` when you only need the version string.

## skills path

```bash
omnibot skills path
```

Use skills path to locate packaged skills for installation or inspection.

## Skills Install

```bash
omnibot skills install --agent hermes --profile nuwa
omnibot skills install --agent opencode
omnibot skills install --agent claude
omnibot skills install --agent codex
omnibot skills install --agent openclaw
omnibot skills install --agent workbuddy
omnibot skills install --agent trae
```

Install only when setting up or repairing an agent integration. It is not part of normal page operations.
