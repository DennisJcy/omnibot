# omnibot 编译构建指南

## 目录结构

```
dist/
├── omnibot-<platform>/      # 独立可执行文件 + 运行时目录（无需 Python 环境）
│   ├── omnibot-<platform>   # 可执行入口
│   ├── *.so / *.pyd         # Nuitka 编译产物
│   ├── lib/                 # 支持文件
│   └── VERSION              # 版本号文本
├── omnibot.crx              # Chrome 扩展（混淆打包）
└── omnibot/                 # Chrome 扩展（未打包目录）
```

## 一、Python 独立可执行文件编译

本项目发布流水线使用 Nuitka 在三个平台分别编译：

- Windows: `windows-latest` -> `omnibot-windows-x64/` (内含 `omnibot-windows-x64.exe`)
- Linux: `ubuntu-latest` -> `omnibot-linux-x64/`
- macOS ARM64: `macos-latest` -> `omnibot-macos-arm64/`

### 关于 `--mode=standalone`

Nuitka 提供 `--onefile`（单文件）和 `--mode=standalone`（目录分发）两种模式。
本项目使用 **standalone 模式**，原因：

- **启动快**：`omnibot --help`、`daemon status` 等短命令每次只付一次进程启动开销；
  `--onefile` 会在每次启动时把整个 bundle 解压到临时目录，引入 16-22s 的延迟。
- **代码安全**：standalone 目录分发的可执行文件已经包含编译后的 C 代码
  （Nuitka 会把 Python 编译为 C 再编译为原生模块），与 `--onefile` 同样不暴露 `.py` 源码。

### 依赖安装

```bash
uv sync --all-extras
```

### 本地构建命令

```bash
uv run python -m nuitka build-config/_entry.py \
  --mode=standalone \
  --assume-yes-for-downloads \
  --include-package=omnibot \
  --include-data-dir=src/omnibot/sop=omnibot/sop \
  --output-dir=dist \
  --output-filename=omnibot
```

### 编译后归一化

Nuitka 会把 standalone 产物写到 `dist/omnibot.dist/`。CI 跑
`scripts/normalize_nuitka_standalone.py` 把它重命名成 npm 平台包期望的
`dist/omnibot-<platform>/` 目录并写入 `VERSION` 文件：

```bash
python scripts/normalize_nuitka_standalone.py \
  --src dist/omnibot.dist \
  --output-dir dist \
  --platform macos-arm64 \
  --version 1.6.2
```

### 编译产物

- macOS: `dist/omnibot-macos-arm64/omnibot-macos-arm64` (Mach-O) + 运行时目录
- Windows: `dist/omnibot-windows-x64/omnibot-windows-x64.exe` (PE exe) + 运行时目录
- Linux: `dist/omnibot-linux-x64/omnibot-linux-x64` (ELF) + 运行时目录

### 注意事项

1. Nuitka 会自动下载 C 编译器（首次编译较慢）
2. 编译产物约 80-90MB，包含 Python 运行时和所有依赖
3. 每个平台需要在对应系统上编译，不能直接交叉编译
4. 授权私钥不参与构建。MCP 产物只包含 Ed25519 公钥，用于离线验签
5. Standalone 目录分发会让产物变成"一个文件夹"，但 npm 平台包本身就是
   `files: ["bin/**"]`，所以分发体积不变；用户安装后目录是私有的。

## 二、Chrome 扩展混淆打包

### 依赖

- Node.js (用于 javascript-obfuscator)

### 构建命令

```bash
python3 build_ext.py
```

### 构建产物

- `dist/omnibot/` — 未打包扩展目录
- JS 文件已混淆（background.js, popup.js, content.js, disable_dialogs.js）

### 打包为 .crx

```bash
# macOS
"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
  --pack-extension="dist/omnibot" \
  --pack-extension-key="omnibot.pem"

# Windows
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
  --pack-extension="dist\omnibot" ^
  --pack-extension-key="omnibot.pem"
```

产物：`dist/omnibot.crx`

## 三、完整构建流程

```bash
# 1. 构建 Python 独立可执行文件（standalone 目录）
uv run python -m nuitka build-config/_entry.py \
  --mode=standalone \
  --assume-yes-for-downloads \
  --include-package=omnibot \
  --include-data-dir=src/omnibot/sop=omnibot/sop \
  --output-dir=dist \
  --output-filename=omnibot

# 1b. 归一化为平台包目录（CI 自动跑）
python scripts/normalize_nuitka_standalone.py \
  --src dist/omnibot.dist \
  --output-dir dist \
  --platform macos-arm64 \
  --version 1.6.2

# 2. 混淆打包 Chrome 扩展
python3 build_ext.py

# 3. 打包 .crx（可选）
"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
  --pack-extension="dist/omnibot" \
  --pack-extension-key="omnibot.pem"
```

## 四、跨平台编译清单

| 平台 | 需要的环境 | 产物目录 |
|------|-----------|---------|
| macOS (arm64) | Python 3.12+ + Nuitka + Xcode CLI | `omnibot-macos-arm64/` |
| Windows (x64) | Python 3.12+ + Nuitka + MSVC/MinGW | `omnibot-windows-x64/` |
| Linux (x64) | Python 3.12+ + Nuitka + gcc | `omnibot-linux-x64/` |

每个平台独立编译，产物不可跨平台使用。
