# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 常用命令

用户通过 `npm install -g omnibot` 安装后，直接使用 `omnibot` 命令：

```bash
# 检查扩展连接状态（CLI 会自动启动 daemon）
omnibot doctor
omnibot status
omnibot tabs

# 安装 skills
omnibot skills install --agent hermes --profile nuwa
omnibot skills install --agent opencode
omnibot skills install --agent claude
omnibot skills install --agent codex

# 浏览器操作
omnibot snapshot -i
omnibot navigate 'https://example.com'
omnibot execute-js "return document.title"
omnibot screenshot -o /tmp/screenshot.png
```

## 架构

omnibot v2 让 LLM 客户端连接**用户正在使用的真实浏览器**，对外能力主要通过本地 daemon 和 CLI 子命令暴露。

**启动链路** → 控制台脚本 `omnibot:main` → `cli.main()` 启动 CLI 命令解析；当执行需要浏览器能力的命令时，CLI 会自动尝试启动或连接本地 daemon。

**`cli.py`** — CLI 命令树：`daemon`（及顶层别名 `start/stop/status/run`）、`tabs`、`snapshot`、`read`、`execute-js`、`batch`、`wait`、`navigate`、`screenshot`、`skills`、`doctor`。

**`daemon.py`** — 本地 daemon 进程，负责保持 `TMWebDriver` 长连接、扩展 WebSocket 状态和浏览器动作调度。

**`daemon_client.py`** — CLI 到 daemon 的客户端层，负责健康检查、自动启动 daemon 和发起 action 请求。

**`actions.py`** — 可复用浏览器动作层，包含核心逻辑：`snapshot`、`read`、`execute_js`、`batch`、`wait`、`navigate`、`screenshot` 等。

**`TMWebDriver.py`** — 核心桥接层。管理通过 WebSocket（`127.0.0.1:18765`）或 HTTP 长轮询（`:18766`）连接的浏览器会话。每个 `Session` 跟踪一个标签页（url、连接类型、活跃状态）。三种连接模式：
- `ws` — 扩展直连 WebSocket
- `ext_ws` — 扩展 WebSocket，带标签页级别的追踪（`tabs_update` 广播）
- `http` — HTTP 长轮询降级方案

也可在 `is_remote` 模式下运行，通过 HTTP 代理到另一 TMWebDriver 实例。

**`simphtml.py`** — 浏览器内 HTML 优化。包含大型嵌入式 JS 代码块（`optHTML()` — 去除脚本/样式/不可见元素并对页面区域分类；`findMainList()` — 检测重复内容列表；`smart_truncate()` — 基于 token 预算的 HTML 截断）。Python 侧用 BeautifulSoup 做后处理（属性清理、列表截断、`execute_js_rich()` 的 DOM 变更 diff）。

**`browser-extension/`** — Chromium 扩展：`background.js`（WebSocket 连接 + 约每 5 秒自动重连）、`content.js`（页面内脚本执行）、`popup.html/js`（扩展工具栏界面）。

**`src/omnibot/skills/`** — omnibot v2 skills 目录，指导 agent 如何使用 CLI 命令读取和操作页面。

**`sop/`** — 扩展 CDP 能力和 Vue3 组件处理的标准操作文档。

## 关键约定

- **日志必须走 stderr**：用 `log()`（在 `TMWebDriver.py` 和 `simphtml.py` 中已定义）输出所有诊断信息。CLI 的结构化结果通过 stdout 输出，诊断信息不要混入 stdout。
- 会话 ID 就是 Chrome 标签页 ID（字符串类型）。每个页面状态命令必须通过 `--tab-id` 显式指定目标标签页，不再有默认目标。
- `execute_js()` 有约 15 秒超时，并跟踪 ACK 确认——能区分"脚本未送达"和"脚本已送达但尚无结果"。
- v2 首版本地优先：CLI 默认通过 `127.0.0.1:18764` 访问 daemon，通过 `127.0.0.1:18765` 连接浏览器扩展。

## 源码验证 daemon 注意事项

- 验证本地源码改动时，不能依赖全局 npm 安装的 packaged daemon。`uv run omnibot ...` 在某些情况下会启动 `/opt/homebrew/lib/node_modules/@omniaibot/omnibot/.../omnibot-macos-arm64`，导致源码新增 action（例如 `read`）返回 `Unknown action`。
- 测试源码内 CLI/daemon 行为前，先停止现有 daemon：
  ```bash
  uv run omnibot stop
  ```
- 然后显式用源码启动 daemon：
  ```bash
  uv run python -m omnibot --api-port 18764 --ws-port 18765 daemon run
  ```
- 另开终端执行验证命令，例如：
  ```bash
  uv run omnibot doctor
  uv run omnibot read --screens 3 https://x.com/home
  ```
- 若 `doctor` 显示 daemon 正常但 action 仍是旧行为，检查 `ps` 中监听 18764 的进程路径，确认不是 packaged binary。

## 测试

### 发版前测试

标准发版 gate：

```bash
python3 tests/release/preflight.py
```

该 gate 执行：

```bash
uv run python -m pytest tests/unit -q
python3 tests/e2e/feature_matrix_test.py --no-playwright
python3 tests/e2e/full_workflow_test.py --no-playwright
```

其中 `tests/e2e/feature_matrix_test.py` 按 Omnibot 子功能拆分测试；`snapshot` 暂不作为单独 case，只作为其他 case 的观察和 ref 获取前置能力。

### 点击功能测试

多维度持久性点击功能测试，验证 omnibot 在不同场景下的点击稳定性。

**测试维度：**
- 基础点击：按钮、链接、输入框
- 动态内容：热搜"换一换"等动态加载内容
- 多标签页：新标签页打开验证
- 边界条件：快速连续点击
- 持久性：重复迭代测试

**运行测试：**

点击功能覆盖已合并到 feature matrix（见上方"发版前测试"）。如需单独回归点击维度：

```bash
python3 tests/e2e/feature_matrix_test.py --case snapshot_ref_click --case dom_cua_click --no-playwright
```

**测试报告：**
- JSON 报告：`tests/reports/comprehensive_test_report_<timestamp>.json`
- 文本报告：`tests/reports/comprehensive_test_report_<timestamp>.txt`

### snapshot + click 闭环测试

v2 核心交互路径：`snapshot` 拿 a11y tree + `@eN` 引用 → `click @eN` 触发操作 →
`snapshot` 验证状态变化。验证 `omnibot snapshot` / `omnibot click` /
`omnibot dblclick` 在真实浏览器 + 扩展下的端到端可用性。

**测试维度：**
- Snapshot 输出：@eN 引用唯一性、`-i`/`-c`/`-d`/`-s`/`-u` flag
- click @eN：button / link / input
- click 选择器回退：CSS / `text=` / `xpath=`
- Round-trip：dynamic refresh / navigation / modal
- Ref 失效与跨 tab 隔离
- `dblclick` + `--new-tab`
- 持久性 / 延迟 / 失败路径
- 弹窗控件：snapshot 自动追加 DOM Popup Controls，并可用生成的 @e 引用点击取消/关闭按钮

**运行测试：**

```bash
# 运行 snapshot + click 闭环测试（需要浏览器扩展连接）
python3 tests/e2e/feature_matrix_test.py --case snapshot_ref_click --no-playwright
```

**测试报告：**
- JSON 报告：`tests/reports/comprehensive_snapshot_click_test_report_<timestamp>.json`
- 文本报告：`tests/reports/comprehensive_snapshot_click_test_report_<timestamp>.txt`

### Upload 单元测试

Upload 命令的单元测试，覆盖 CDP `DOM.setFileInputFiles`、`DOM.querySelector` nodeId 回退、以及 JS `DataTransfer` fallback 三条上传路径，无需浏览器扩展连接。

**测试用例：**
- `test_upload_action_request_maps_to_upload_action` — CLI 参数到 action 映射
- `test_upload_action_sets_file_input_files_with_cdp` — CDP Runtime.evaluate objectId 路径
- `test_upload_action_falls_back_to_dom_node_id` — CDP DOM.querySelector nodeId 回退路径
- `test_upload_action_falls_back_to_js_file_assignment` — JS DataTransfer fallback 路径

**运行测试：**

```bash
uv run python -m pytest tests/unit/test_cli_contract.py -k upload -q
```

### 弹窗控件端到端测试

弹窗/模态框 DOM Popup Controls 扫描 + 点击闭环测试，使用本地 HTML fixture 页面验证 5 种弹窗类型的控件检测和 @eN 引用点击。

**测试用例：**
- `test_modal_dialog_controls_detected_and_clickable` — `role="dialog"` 弹窗检测 + Cancel 点击
- `test_drawer_controls_detected_and_clickable` — CSS class drawer 抽屉检测 + Close drawer 点击
- `test_alertdialog_controls_detected_and_clickable` — `role="alertdialog"` 告警弹窗检测 + Dismiss 点击
- `test_combobox_dropdown_options_detected_and_clickable` — combobox + listbox + option 下拉检测 + 选项点击
- `test_fixed_overlay_popup_controls_detected_and_clickable` — position:fixed 叠加层检测 + Close 点击
- `test_no_popup_controls_when_all_closed` — 关闭弹窗后 modal/drawer/alert/popup 控件不再出现在 DOM Popup Controls（combobox 自动探测除外）
- `test_multiple_popups_open_simultaneously` — 多弹窗同时打开时所有控件均被捕获

**运行测试：**

```bash
# 需要浏览器扩展连接
python3 tests/e2e/popup_modal_test.py -v
```

### 浏览器原生弹窗 dialog 测试

`omnibot dialog` 覆盖浏览器原生 JavaScript 弹窗（`alert` / `confirm` / `prompt`）的捕获与处理。扩展不得吞掉弹窗或替用户选择结果；`native_dialogs.js` 只做透明捕获，然后继续调用浏览器原生函数。

**单元测试覆盖：**
- `tests/unit/test_cli_contract.py` — `dialog logs` / `dialog clear` / `dialog handle accept|dismiss` / `dialog handle accept --text` CLI 解析和 action 映射
- `tests/unit/test_actions_contract.py` — `dialog_logs()` / `dialog_handle()` 到扩展 `dialogCapture` 命令的请求形状，并验证 prompt 文本会转发为 `promptText`
- `tests/unit/test_build_ext_contract.py` — 不再注入 `disable_dialogs.js`；打包 `native_dialogs.js`；`confirm` 透明调用 `nativeConfirm(message)`，不得 `return true` 或显示 `Blocked Confirm`

**端到端测试覆盖：**
- `browser_dialog_capture` — 验证原生弹窗捕获事件进入 `dialog logs`，并验证透明 wrapper 已安装
- `browser_dialog_confirm_accept` — 触发真实原生 `confirm`，用 `dialog handle accept` 点击确定，并验证页面得到 `true`
- `browser_dialog_confirm_dismiss` — 触发真实原生 `confirm`，用 `dialog handle dismiss` 点击取消，并验证页面得到 `false`
- `browser_dialog_prompt_text` — 触发真实原生 `prompt`，用 `dialog handle accept --text` 提交文本，并验证页面得到该文本

**dialog handle 正确触发模式：**
CDP `Runtime.evaluate(confirm(...))` 在 one-shot `handleCDP` 中会阻塞 service worker 导致死锁。必须先 `dialog clear`/`dialog logs`（使扩展 attach debugger + `Page.enable`），再通过 `execute-js`（content script 路径）异步触发 `confirm()`/`prompt()`，然后用 `dialog handle` 处理。

**运行测试：**

```bash
# 单元测试，无需浏览器扩展连接
uv run python -m pytest tests/unit/test_cli_contract.py tests/unit/test_actions_contract.py tests/unit/test_build_ext_contract.py -k 'dialog or native_dialog' -q

# E2E 测试，需要浏览器扩展连接，并且扩展已重新加载当前源码
python3 tests/e2e/feature_matrix_test.py --case browser_dialog_capture --no-playwright
python3 tests/e2e/feature_matrix_test.py --case browser_dialog_confirm_accept --case browser_dialog_confirm_dismiss --case browser_dialog_prompt_text --no-playwright
```

## 发布流程

发布由 **GitHub Actions 流水线**完成（`.github/workflows/build-release.yml`）：推送 `v*` tag 后自动在 GitHub 原生 runner 上并行构建三平台二进制 + 浏览器扩展，并发布 GitHub Release、npm 包和（可选）Edge Add-ons Store。不需要任何本地构建脚本或远程构建机器。

| 平台 | runner | 构建方式 |
|------|--------|---------|
| Linux x64 | `ubuntu-latest` | Nuitka 原生编译 |
| macOS ARM64 | `macos-latest`（Apple Silicon） | Nuitka 原生编译 |
| Windows x64 | `windows-latest`（自带 MSVC） | Nuitka 原生编译 |
| Extension | `ubuntu-latest` | `build_ext.py` |

**为什么用 GitHub runner 而不是 Docker/远程机器？**
- `windows-latest` 自带 MSVC 工具链，Nuitka 可直接编译 Windows 二进制——此前本地没有 Windows 环境，才需要远程 SSH 构建机（`build-windows-remote.sh` 已删除）
- `macos-latest` 是 Apple Silicon 原生 runner，直接产出 ARM64 二进制
- 发布流程不再依赖任何内网 IP / SSH 凭据

**发布所需 secrets（仓库 Settings → Secrets and variables → Actions）：**
- `NPM_TOKEN` — npm 发布令牌，必须有 `@omniaibot/*` scope 的 publish 权限（bypass-2FA 的 Granular Access Token 可以发布）
- `EDGE_API_KEY` / `EDGE_PRODUCT_ID` / `EDGE_CLIENT_ID` —（可选）Edge Add-ons Store 发布；不配置则 CI 跳过 Edge 发布

### 版本号规则

版本号必须在以下位置保持一致：

- `pyproject.toml` → `version = "1.6.8"`
- `src/omnibot/cli.py` → fallback 版本字符串（`_version()` 异常时使用）
- `npm-packages/cli/package.json` → `"version": "1.6.8"`
- `npm-packages/cli/package.json` → `optionalDependencies` 中三个平台包版本
- `npm-packages/win-x64/package.json` → `"version": "1.6.8"`
- `npm-packages/linux-x64/package.json` → `"version": "1.6.8"`
- `npm-packages/macos-arm64/package.json` → `"version": "1.6.8"`
- `browser-extension/manifest.json` → `"version": "1.6.8"`

**发布前版本同步检查清单（按顺序执行）：**

1. `pyproject.toml` → `version`
2. `src/omnibot/cli.py` → fallback 版本字符串
3. 所有 `npm-packages/*/package.json` → `version`
4. `npm-packages/cli/package.json` → `optionalDependencies` 平台包版本
5. `browser-extension/manifest.json` → `version`
6. 二进制 `VERSION` 文件：构建时由 `normalize_nuitka_standalone.py` 自动写入
7. 二进制 skills 文件：构建时由 `scripts/build-all.sh` 自动同步

**关键约束：**
- npm 不允许覆盖发布同一版本号，版本一旦发布必须升到下一个版本
- 所有 8 个位置的版本号必须完全一致，否则安装时会出现版本不匹配
- 浏览器扩展版本号必须与 CLI 版本号保持一致
- skills 文档版本号和命令示例必须与 Omnibot 发版保持一致
- 发版前搜索 skills 和 README 中是否有已删除命令的残留引用

### Tag 格式

```bash
# 格式: v<major>.<minor>.<patch>
git tag v1.6.8
git push origin v1.6.8
```

Tag 必须以 `v` 开头，后面跟 semver 版本号。CI 会去掉 `v` 前缀作为 npm/VERSION 版本。

### 完整发布步骤

**Step 1: 版本 bump**
更新所有 8 个版本号位置到新版本，并运行 `uv lock` 同步 `uv.lock`。

**Step 2: 发版前测试**
```bash
python3 tests/release/preflight.py
```

preflight 必须全部通过（单元测试 + feature matrix + full workflow）。通过后提交所有更改再进入 Step 3：包括版本号 bump、测试修复，以及 preflight 运行可能产生的 `uv.lock` 等自动变更。若 preflight 因过时测试失败，先修复测试（必要时同步修正对应生产代码契约）使其通过，再提交。确保 `git status` 干净后再打 tag。

**Step 3: 提交 + Tag + 推送**
```bash
git add -A
git commit -m "chore: bump to v1.6.8"
git tag v1.6.8
git push origin master --tags
```

**Step 4: CI 自动完成（无需本地操作）**

推送 tag 后 `.github/workflows/build-release.yml` 自动执行：
1. 并行构建 Linux / macOS / Windows 二进制 + 浏览器扩展（4 个独立 job）
2. 创建 GitHub Release 并上传 4 个 zip（extension/linux/macos/windows）
3. 校验 npm 包版本与 tag 一致（不一致则中止）
4. 发布 npm 包（`@omniaibot/omnibot`、`@omniaibot/linux-x64`、`@omniaibot/macos-arm64`、`@omniaibot/win-x64`）
5. 配置了 `EDGE_API_KEY` 时发布到 Edge Add-ons Store

发布失败排查：打开仓库 Actions 页面查看对应 job 日志。npm 发布失败最常见原因是版本号与 tag 不一致（Step 1 漏改某处）；构建失败常见于 Nuitka 版本变更，查看 `pip install nuitka` 是否升级了不兼容版本。

**Edge Add-ons Store 自动发布：**

CI 的 release job 会在配置了 `EDGE_API_KEY` / `EDGE_PRODUCT_ID` / `EDGE_CLIENT_ID` secrets 时自动发布扩展到 Edge Add-ons Store。也可以本地单独运行：

```bash
EDGE_API_KEY="your-api-key" EDGE_PRODUCT_ID="..." EDGE_CLIENT_ID="..." ./scripts/publish-edge-extension.sh /tmp/omnibot-extension.zip
```

Edge Add-ons API 配置：
- **Product ID / Client ID**: 从 Partner Center 获取
- **API Key**: 从 Partner Center 获取（需要定期更新）
- **API 文档**: https://learn.microsoft.com/en-us/microsoft-edge/extensions/update/api/using-addons-api

**发布后验证：**
```bash
npm view @omniaibot/omnibot@1.6.8 version
npm view @omniaibot/linux-x64@1.6.8 version
npm view @omniaibot/macos-arm64@1.6.8 version
npm view @omniaibot/win-x64@1.6.8 version
npm install -g @omniaibot/omnibot@1.6.8
$(npm prefix -g)/bin/omnibot --help
```

### 发布注意事项

1. **npm 不允许覆盖已发布版本**：如果发布了错误内容（如旧二进制），不能通过 `npm unpublish` + `npm publish` 同一版本号来修复。必须 bump 到下一个版本（如 1.6.8 → 1.6.9）重新发布。npm 新政策还禁止 bypass-2FA 令牌执行 unpublish，撤回发布只能 deprecate 标记废弃。

2. **目录命名不一致**：npm 包名是 `@omniaibot/win-x64`，但实际产物目录名是 `omnibot-windows-x64`（不是 `omnibot-win-x64`）。CI 的 normalize 与解压逻辑已统一此命名。

3. **Nuitka + Python 3.13 + Windows UnicodeDecodeError**：`scripts/patch_nuitka_windows.py` 会把 metadata 访问包在 try-except 中。CI 的 Windows job 每次构建前自动执行此 patch。

4. **二进制污染检查**（发布前人工确认可选）：`strings <二进制> | grep -i license` 应无输出——此前出现过远程构建机残留旧模块被 Nuitka 编入二进制的问题；CI 从干净 checkout 构建不会遇到。

### 构建基础设施

**`.github/workflows/build-release.yml`** — 发布流水线（三平台构建 + 扩展 + GitHub Release + npm + Edge）。

**`scripts/normalize_nuitka_standalone.py`** — 归一化 Nuitka 产物：重命名二进制、写 VERSION 文件、整理目录。CI 三个平台 job 均使用。

**`scripts/patch_nuitka_windows.py`** — 修复 Windows 上 Nuitka 的 UnicodeDecodeError，CI Windows job 自动执行。

**`scripts/publish-edge-extension.sh`** — Edge Add-ons Store 发布脚本（CI 可选步骤，也可本地单独运行）。

**`build_ext.py`** — 浏览器扩展打包（CI 与本地开发通用，输出 `dist/omnibot/`）。

**`scripts/publish.sh`** — PyPI 发布（独立用途，与 GitHub/npm 发布无关）。

