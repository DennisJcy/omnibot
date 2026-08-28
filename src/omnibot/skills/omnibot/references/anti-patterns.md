# Anti-Patterns

| Bad | Why bad | Good |
| --- | --- | --- |
| Missing `OMNIBOT_SESSION_TOKEN` | Workflows can share implicit state across agents. | `OMNIBOT_SESSION_TOKEN=research omnibot snapshot -i --tab-id <TAB_ID>` |
| Missing `--tab-id` | The command may target the wrong page. | Pass `--tab-id <TAB_ID>` on every page-state command. |
| `execute-js` first | JavaScript bypasses standard browser interaction and hides better evidence. | Try semantic find, snapshot refs, selectors, DOM, and mouse first. For CSS-only dropdowns, use JavaScript only after the trigger clicked, options remain absent from `snapshot -i`, and higher tiers cannot complete open-then-select. |
| JS page detection (`document.title`, `location.href`) | It teaches agents to treat scripts as normal reads. | Use `get title` and `get url`. |
| JS text extraction (`document.body.innerText`) | It bypasses `read` cleanup, lazy-page handling, and targeted evidence. | Use `read --screens N` or `get text`. |
| Using `document.body.innerText` because a JSF page's first body is empty | Legacy pages may contain multiple bodies; the first can be an autocomplete shell while the content-rich body holds the form or table. | Keep the selected frame and use `read`; target exact refs/ids for narrow evidence. |
| JS click shortcut (`querySelector(...).click()`) | It can bypass pointer events, overlays, disabled state, and framework/user-intent safety checks. | Use `find ... --action click`, `snapshot -i` + `click @eN`, then selector/DOM/mouse fallback. |
| JS scroll shortcut (`window.scrollTo`, `scrollIntoView`) | It hides whether the scroll target/container is correct and bypasses Omnibot's action evidence path. | Use `scroll`, `scrollintoview`, `dom scroll`, or `mouse scroll`. |
| JS value or richtext writes | App frameworks may ignore value/HTML mutation without trusted events and editor integration. | Use `fill`, `type`, `press`, `keyboard`, and `[richtext]` refs. |
| Reusing `@eN` across tabs | Refs are tab-scoped and may point to a different element elsewhere. | Take a fresh `snapshot -i --tab-id <TAB_ID>` per tab. |
| Relying on implicit tab targeting | It is unavailable and unsafe for concurrent workflows. | Use explicit `--tab-id` on every page-state command. |
| Using sleep instead of wait | Fixed sleeps are flaky and either too short or too slow. | Use `omnibot wait --text`, `--url`, selector state, load state, or `--fn`. |
| Writing `wait --load` with a guessed positional value | Bare `--load` already means the `load` lifecycle state; invented syntax can fail before any wait begins. | Use bare `--load`, or explicitly choose `--load domcontentloaded` / `--load networkidle`, then verify URL/business state. |
| Acting without verify | Command success is not task success. | Run `snapshot`, `get`, `is`, or `wait` after every action. |
| Claiming success without evidence | The browser may not have changed as expected. | Cite verified URL, text, element state, screenshot, console, or network evidence. |
| Raw CSS before semantic find | CSS is more brittle and less tied to user intent. | Start with `find role/text/label/placeholder/testid`. |
| Replacing an unnamed password ref with CSS immediately | Snapshot distinguishes `[type=password]`, and the ref binds the exact live input even when AX names are blank. | Use `fill @password-ref`, verify without exposing the secret, then use `input[type=password]` only as fallback. |
| Screenshot when text extraction is enough | Screenshots cost more and are harder to parse. | Use `read` for page content or `get text` for a selector. |
| Trusting a screenshot filename or earlier requested URL | A redirect or reused tab can yield a valid image of a different page. | Validate the response `url`, `title`, `viewport`, and `bytes > 0`; prefer `bytes` over shell `wc` (`/usr/bin/wc` on macOS). |
| Using `read` before an action workflow | `read` returns text, not stable action targets. | Use `find`, `snapshot -i`, `get`, or `is` for click/fill/verify workflows. |
| Headless expecting existing user login | Headless does not automatically share the user's visible browser session. | Use visible/background mode for existing login or explicitly log in headless. |
| Mixing multiple workflows in one session token | Agents can overwrite each other's default state. | Use different tokens: `research`, `checkout`, `debug`. |
| Using default tab state in concurrent agents | There is no default tab. Every page command requires explicit `--tab-id`. | Discover or create a tab, save its id, and pass `--tab-id`. |
| Not checking doctor/tabs before troubleshooting | You may debug page logic when the runtime is disconnected. | Run `omnibot doctor` and `omnibot tabs` first. |
| Ignoring exit status or redirecting Omnibot output to `/dev/null` | `status: error` and `status: timeout` exit non-zero with an `error_code`; hiding them can strand the caller in an executing state and skip cleanup. | Capture JSON plus `$?`, branch on `error_code`, and keep diagnostics until completion handling finishes. |
| Using lowercase `path` as a zsh route variable | zsh ties `path` to `PATH`, so assignment can make `omnibot`, `sleep`, and other commands disappear. | Use `route_path` or `page_path`; resolve `OMNIBOT_BIN="$(command -v omnibot)"` before restricted subprocesses. |
| Blindly retrying after a daemon/extension interruption | A mutation may already have reached the browser even when its response was lost; replay can double-click, duplicate tabs, or reverse state. | Let Omnibot retry read-only actions and same-tab `goto`; after uncertain mutations, observe state before another action. |
| Using `tabs[0]` or the first tab | The first tab is often a user tab or the transport tab, not the workflow target. | Create or identify the intended tab and store its full id. |
| Treating transport as target | Extension routing may use a different tab than the page being acted on. | Always pass `--tab-id <TAB_ID>` and verify with `get url --tab-id <TAB_ID>`. |
| Treating `frame` as a relative push into the current iframe | Frame targets are absolute for the tab, so a generic target can resolve the wrong ancestor. | Inspect the nested iframe `src`, target a unique descendant substring, and re-run `snapshot -i`. |
| Closing discovered user tabs | Cleanup can destroy the user's real work. | Track only tool-created tabs and close only those ids. |
| Leaving worker-token tabs untracked | Cross-token test tabs can remain open or auto-close later. | Add every worker-created tab id to cleanup tracking. |
| Manually reopening every combobox after snapshot | `snapshot -i` may already include auto-probed option refs; reopening all dropdowns wastes time and can change focus/state. | If `[option]` refs are present, click the option ref and verify. |
| JavaScript fallback for a visible combobox before refs | Auto-probed combobox option refs are a higher reliability tier than ad-hoc JS. | Run `snapshot -i`, use `@option` refs, then fallback only if refs are absent or fail verification. |
| Stale CLI memory | Parser failures waste browser state and can lead to wrong conclusions about page behavior. | Run `omnibot --help` and `omnibot <command> --help` before using uncommon or newly introduced commands. |
| Unsafe checkout capture | Clicking through all checkout controls until an order is placed is irreversible and may charge the user. | Capture only the transition into confirmation/preview pages, stop before final submit/pay/place-order controls, and report only non-sensitive request metadata. |
| Revealing sensitive network data | Cookies, auth headers, full addresses, phone numbers, and payment data must not be pasted into reports. | Report host, path, method, status, and non-sensitive payload shape only. |
| Using stale `@eN` refs after a failed click | Refs may have expired or the page may have changed. | Re-observe with `snapshot -i` or use a higher-evidence fallback. |
| Manually scrolling a known ref before every click | It adds an unnecessary mutation, can invalidate refs, and may scroll the wrong nested container. | Click the semantic target or `@eN` directly; Omnibot atomically scrolls, reboxes, hit-tests, and clicks live DOM targets. Manually scroll only to discover virtualized or lazy-rendered content that is not yet in the snapshot. |
| `Network.enable` without log retrieval | Raw `cdp` calls are one-shot and do not persist events for later reading. | Use `network clear -> network start -> one action -> network stop -> network logs/summary`. |
| Writing the article body into the title field | Rich text article body editors are often missing from the AX tree; filling the only visible `[textbox]` (title) overwrites the wrong control. | Run `snapshot -i`, find the body under `# DOM Rich Text Editors` as `@eN [richtext]`, then `fill @richtext "..."`. |
| `execute-js` for rich text body before `fill @richtext` | ContentEditable writes need event dispatch and framework integration; ad-hoc `innerHTML` bypasses Omnibot's supported path. | Use `fill @richtext "p1\n\np2"` or `type @richtext " text"` first. |
| Counting `<img>` nodes to detect duplicate images in a rich editor | ProseMirror/Toutiao image cards keep a hidden `<templ>` template and a visible `<mask>` copy of the same `<img>`, so `.ProseMirror img` returns 2 for one logical image and falsely reports duplication. | Count image card containers (`.ProseMirror [__syl_tag=true]` or `.ProseMirror .pgc-image`), one per inserted image. |
| Inserting an image via `click @richtext` + `press End` | The caret stays on the first line; the image lands at the editor root instead of the target paragraph. | Use `find text "<anchor phrase>" --action click` to collapse the selection at the end of the matched phrase, then open the image tool and upload. |

Do not manually reopen a dropdown just to discover options if `snapshot -i` already lists them.

## Red Flags

- "I can just use the current tab."
- "This is only one click, no need to verify."
- "JavaScript is faster."
- "I just need title/url/text, so JS is fine."
- "Clicking with JS is equivalent to a user click."
- "Scrolling with JS is harmless."
- "The ref probably still points to the same element."
- "The target is off-screen, so I must manually scroll before clicking its ref."
- "A screenshot is enough even though I need text."
- "Sleep should be fine."
- "The trigger clicked, so another `find text` should eventually select the option."
- "`snapshot -i` cannot see the option, so the element must not exist."
- "This dropdown is custom, so I can start with JavaScript."
- "I remember the command syntax from before."
- "`Network.enable` should be enough to capture requests."
- "It is just a checkout preview, clicking pay should be fine."
- "The article body is not in `snapshot -i`, so I will fill the title textbox."
- "I will just set `innerHTML` on the contenteditable with `execute-js`."
- "`.ProseMirror img` returned 2, so the image was inserted twice."
- "I clicked the editor and pressed End, so the caret must be after the last paragraph."

All of these mean: stop, re-enter the standard pattern, and make state explicit.
