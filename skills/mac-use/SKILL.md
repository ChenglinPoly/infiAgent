---
name: mac-use
description: Control macOS GUI apps visually — take screenshots, click, scroll, type. Use when the user asks to interact with any Mac desktop application's graphical interface.
metadata: {"openclaw":{"emoji":"🖥️","requires":{"bins":["python3"]},"os":["darwin"],"install":[{"id":"python-brew","kind":"brew","formula":"python","bins":["python3"],"label":"Install Python 3 (brew)"}]}}
---

# Mac Use

Control any macOS GUI application through a **screenshot → pick element → click → verify** loop.

## Setup

**Platform**: macOS only (requires Apple Vision framework for OCR)

**System binaries** (pre-installed on macOS):
- `python3` — via Homebrew (`brew install python`)
- `screencapture` — built-in macOS utility

**Python packages** — install from the skill directory:
```bash
pip3 install --break-system-packages -r {baseDir}/requirements.txt
```

## How It Works

The `screenshot` command captures a window, uses **Apple Vision OCR** to detect all text elements, draws numbered annotations on the image, and returns both:
1. **Annotated image** at `/tmp/mac_use.png` — numbered green boxes around each detected text
2. **Element list** in JSON — `[{num: 1, text: "Submit", at: [500, 200]}, {num: 2, text: "Cancel", at: [600, 200]}, ...]` where `at` is the center point `[x, y]` on the 1000x1000 canvas (origin at top-left)

You receive both by calling Bash (gets JSON with element list) and then Read on `/tmp/mac_use.png` (gets the visual). **Always do both** so you can cross-reference the numbers with what you see.

## Quick Reference

```bash
# List all visible windows
python3 {baseDir}/scripts/mac_use.py list

# Screenshot + annotate (returns image + numbered element list)
python3 {baseDir}/scripts/mac_use.py screenshot <app> [--id N]

# Click element by number (primary click method)
python3 {baseDir}/scripts/mac_use.py clicknum <N>

# Click at canvas coordinates (fallback for unlabeled icons)
python3 {baseDir}/scripts/mac_use.py click --app <app> [--id N] <x> <y>

# Scroll inside a window
python3 {baseDir}/scripts/mac_use.py scroll --app <app> [--id N] <direction> <amount>

# Type text (uses clipboard paste — supports all languages)
python3 {baseDir}/scripts/mac_use.py type [--app <app>] "text here"

# Press key or combo
python3 {baseDir}/scripts/mac_use.py key [--app <app>] <combo>
```

## Workflow

1. **Open** the target app with `open -a "App Name"` (optionally with a URL or file path)
2. **Wait** for it to load: `sleep 2`
3. **Screenshot** the app:
   ```bash
   python3 {baseDir}/scripts/mac_use.py screenshot <app> [--id N]
   ```
   This returns JSON with `file` (image path) and `elements` (numbered text list).
4. **Read** the annotated image at `/tmp/mac_use.png` to see the numbered elements visually
5. **Decide** which element to interact with:
   - **Prefer `clicknum N`** — pick the number of a detected text element
   - **Fallback `click --app <app> x y`** — only for unlabeled icons (arrows, close buttons, cart icons) that have no text and therefore no number
6. **Act** using `clicknum`, `type`, `key`, or `scroll`
7. **Screenshot again** to verify the result
8. Repeat from step 3

## Commands

### list

Show all visible app windows.

```bash
python3 {baseDir}/scripts/mac_use.py list
```

Returns JSON array: `[{"app":"Google Chrome","title":"Wikipedia","id":4527,"x":120,"y":80,"w":1200,"h":800}, ...]`

### screenshot

Capture a window, detect text elements via OCR, annotate with numbered markers, and return the element list. The target window is automatically raised to the top before capture, so overlapping windows are handled.

```bash
python3 {baseDir}/scripts/mac_use.py screenshot chrome
python3 {baseDir}/scripts/mac_use.py screenshot chrome --id 4527
```

- `<app>`: fuzzy, case-insensitive match (e.g. "chrome" matches "Google Chrome")
- `--id N`: target a specific window ID (required when multiple windows of the same app exist)
- Returns JSON with:
  - `file`: path to annotated screenshot (`/tmp/mac_use.png`)
  - `id`, `app`, `title`, `scale`: window metadata
  - `elements`: array of `{num, text, at}` — the numbered clickable text elements, where `at` is `[x, y]` center coordinates on the 1000x1000 canvas (origin at top-left)
- If multiple windows match, returns a list of windows instead — pick one and retry with `--id`
- The image is 1000x1000 pixels with green bounding boxes and blue number badges
- Element map is saved to `/tmp/mac_use_elements.json` for `clicknum`

### clicknum

Click on a numbered element from the last screenshot. **This is the primary click method.**

```bash
python3 {baseDir}/scripts/mac_use.py clicknum 5
python3 {baseDir}/scripts/mac_use.py clicknum 12
```

- `N`: the element number from the last `screenshot` output
- Reads the saved element map, activates the window, and clicks at the element's center
- Returns JSON with `clicked_num`, `text`, canvas coords, and absolute screen coords

### click

Click at a position using canvas coordinates. **Fallback only — use for unlabeled icons.**

```bash
python3 {baseDir}/scripts/mac_use.py click --app chrome 500 300
python3 {baseDir}/scripts/mac_use.py click --app chrome --id 4527 500 300
```

- **Coordinates are canvas positions (0-1000)** from the screenshot image
- x=0 is left, x=1000 is right; y=0 is top, y=1000 is bottom
- Use this only when Vision OCR didn't detect the element (icon-only buttons, images, etc.)

### scroll

Scroll inside an app window.

```bash
python3 {baseDir}/scripts/mac_use.py scroll --app chrome down 5
python3 {baseDir}/scripts/mac_use.py scroll --app notes up 10
```

- Directions: `up`, `down`, `left`, `right`
- Amount: number of scroll clicks (3-5 for moderate, 10+ for fast scrolling)
- Mouse is moved to the center of the window before scrolling

### type

Type text into the currently focused input field.

```bash
python3 {baseDir}/scripts/mac_use.py type --app chrome "hello world"
python3 {baseDir}/scripts/mac_use.py type --app chrome "你好世界"
```

- `--app`: activates the app first to ensure keystrokes go to the right window
- Uses clipboard paste (Cmd+V) for reliable Unicode/CJK support
- **Always click on the target input field first** before typing

### key

Press a single key or key combination.

```bash
python3 {baseDir}/scripts/mac_use.py key --app chrome return
python3 {baseDir}/scripts/mac_use.py key --app chrome cmd+a
python3 {baseDir}/scripts/mac_use.py key --app chrome cmd+shift+s
```

- `--app`: activates the app first
- Common keys: `return`, `tab`, `escape`, `space`, `delete`, `backspace`, `up`, `down`, `left`, `right`
- Modifiers: `cmd`, `ctrl`, `alt`/`opt`, `shift`

## Important Rules

- **Always screenshot before your first interaction** with an app
- **Always screenshot after an action** to verify the result
- **Always Read the screenshot image** after running the screenshot command — you need both the element list AND the visual
- **Prefer `clicknum`** over `click` — only use direct coordinates for unlabeled icons
- **Click before typing** — ensure the correct input field has focus first
- **Multiple windows**: if you get `multiple_windows` error, use `list` to see all windows, then pass `--id`
- **Popup windows** (like WeChat mini-program panels) are separate windows with their own IDs — use `list` to find them and `--id` to target them
- **Wait after opening apps**: use `sleep 2-3` after `open -a` before taking a screenshot
- **Activate the app** before screenshot/click: prepend `osascript -e 'tell application "AppName" to activate' && sleep 1` when the target app may be behind other windows
- **Do not type passwords or secrets** via this tool

## Coordinate System (for fallback `click` only)

Screenshots are rendered onto a **1000x1000 canvas**:
- **Origin (0, 0)** is at the **top-left** corner
- **x** increases left to right (0 = left edge, 1000 = right edge)
- **y** increases top to bottom (0 = top edge, 1000 = bottom edge)
- The app window is scaled to fit (aspect ratio preserved), centered, with dark gray padding

## Example: Order food on Meituan in WeChat

```bash
# 1. Open WeChat
open -a "WeChat"
sleep 3

# 2. Screenshot WeChat — find the mini program window
python3 {baseDir}/scripts/mac_use.py list
# → find the mini program window ID

# 3. Screenshot the mini program (annotated + element list)
python3 {baseDir}/scripts/mac_use.py screenshot 微信 --id 41266
# → returns: {"file": "/tmp/mac_use.png", "elements": [{num: 1, text: "搜索", at: [500, 200]}, ...]}
# → Read /tmp/mac_use.png to see annotated image

# 4. Click "搜索" (element #1)
python3 {baseDir}/scripts/mac_use.py clicknum 1

# 5. Type search query
python3 {baseDir}/scripts/mac_use.py type --app 微信 "炸鸡"

# 6. Press Enter
python3 {baseDir}/scripts/mac_use.py key --app 微信 return
sleep 2

# 7. Screenshot to see results
python3 {baseDir}/scripts/mac_use.py screenshot 微信 --id 41266
# → Read /tmp/mac_use.png, pick a restaurant by number

# 8. Click on a restaurant (e.g. element #5)
python3 {baseDir}/scripts/mac_use.py clicknum 5
```
