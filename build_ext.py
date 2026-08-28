#!/usr/bin/env python3
"""omnibot extension build script - package for distribution.

Note: Code is submitted in human-readable form to comply with Chrome Web Store
code readability requirements.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / 'browser-extension'
DIST_DIR = ROOT / 'dist' / 'omnibot'
JS_FILES = ['background.js', 'config.js', 'popup.js', 'help.js', 'content.js', 'mouse_visual.js', 'native_dialogs.js', 'offscreen.js']
STATIC_EXTS = {'.html', '.json', '.png', '.jpg', '.svg'}


def build():
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    print("Copying static files...")
    for item in SRC_DIR.iterdir():
        if item.is_file() and item.suffix in STATIC_EXTS:
            shutil.copy2(item, DIST_DIR / item.name)
    icon_dir = DIST_DIR / 'icons'
    icon_dir.mkdir(exist_ok=True)
    for item in (SRC_DIR / 'icons').iterdir():
        shutil.copy2(item, icon_dir / item.name)

    print("Copying JavaScript files...")
    for jsf in JS_FILES:
        src = SRC_DIR / jsf
        if not src.exists():
            print(f"  Skipping {jsf} (not found)")
            continue
        dst = DIST_DIR / jsf
        shutil.copy2(src, dst)
        print(f"  Copied {jsf}")

    print("Copying _locales...")
    locales_src = SRC_DIR / '_locales'
    if locales_src.exists():
        shutil.copytree(locales_src, DIST_DIR / '_locales')
        print("  Copied _locales/")

    print(f"\nBuild complete: {DIST_DIR}")
    print("Load in browser: edge://extensions → Developer mode → Load unpacked → select dist/omnibot/")


if __name__ == '__main__':
    build()
