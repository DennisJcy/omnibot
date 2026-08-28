#!/usr/bin/env node

const os = process.platform;
const arch = process.arch;
const { spawnSync } = require("child_process");
const path = require("path");

let pkg;
let dirName;
let binName;

if (os === "win32" && arch === "x64") {
  pkg = "@omniaibot/win-x64";
  dirName = "omnibot-windows-x64";
  binName = "omnibot-windows-x64.exe";
} else if (os === "linux" && arch === "x64") {
  pkg = "@omniaibot/linux-x64";
  dirName = "omnibot-linux-x64";
  binName = "omnibot-linux-x64";
} else if (os === "darwin" && arch === "arm64") {
  pkg = "@omniaibot/macos-arm64";
  dirName = "omnibot-macos-arm64";
  binName = "omnibot-macos-arm64";
} else {
  console.error("Unsupported platform: " + os + " " + arch);
  process.exit(1);
}

const pkgDir = path.dirname(require.resolve(pkg + "/package.json"));
const binPath = path.join(pkgDir, "bin", dirName, binName);

const result = spawnSync(binPath, process.argv.slice(2), { stdio: "inherit" });
process.exit(result.status ?? 1);
