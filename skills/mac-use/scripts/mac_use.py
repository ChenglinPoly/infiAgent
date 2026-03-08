#!/usr/bin/env python3
"""mac_use.py - macOS GUI automation helper.

Subcommands:
  list                              List all visible app windows
  screenshot <app> [--id N]         Capture + annotate an app's window
  clicknum <N>                      Click element N from last screenshot
  click --app <app> [--id N] x y    Click at canvas coords (0-1000)
  scroll --app <app> [--id N] <dir> <amount>  Scroll inside a window
  type <text>                       Type text (via clipboard paste)
  key <combo>                       Press key combo (e.g. return, cmd+v)
"""

import argparse
import json
import re
import subprocess
import sys
import time

import pyautogui
import Vision
import Quartz
from Foundation import NSURL
from PIL import Image, ImageDraw, ImageFont
from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGWindowListOptionOnScreenOnly,
    kCGNullWindowID,
)

# Keep failsafe on but set a short pause
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

SCREENSHOT_PATH = "/tmp/mac_use.png"
SCREENSHOT_FULL = "/tmp/mac_use_full.png"
ELEMENTS_FILE = "/tmp/mac_use_elements.json"
CANVAS_SIZE = 1000


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------

def get_windows():
    """Return all visible normal windows as a list of dicts."""
    raw = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    windows = []
    for w in raw:
        if w.get("kCGWindowLayer", -1) != 0:
            continue
        name = w.get("kCGWindowOwnerName", "")
        title = w.get("kCGWindowName", "")
        wid = w.get("kCGWindowNumber", 0)
        bounds = w.get("kCGWindowBounds", {})
        if not name or not wid:
            continue
        bw = int(bounds.get("Width", 0))
        bh = int(bounds.get("Height", 0))
        if bw < 50 or bh < 50:
            continue
        windows.append({
            "app": str(name),
            "title": str(title) if title else "",
            "id": int(wid),
            "x": int(bounds.get("X", 0)),
            "y": int(bounds.get("Y", 0)),
            "w": bw,
            "h": bh,
        })
    return windows


def find_window(app_name, window_id=None):
    """Find window(s) by fuzzy app name and optional ID."""
    windows = get_windows()
    app_lower = app_name.lower()
    matches = [w for w in windows if app_lower in w["app"].lower()]

    if not matches:
        all_apps = sorted(set(w["app"] for w in windows))
        return None, {
            "error": "no_window",
            "message": f"No visible window matching '{app_name}'",
            "available_apps": all_apps,
        }

    if window_id is not None:
        for w in matches:
            if w["id"] == window_id:
                return w, None
        return None, {
            "error": "window_id_not_found",
            "message": f"No window with ID {window_id} for '{app_name}'",
            "windows": matches,
        }

    if len(matches) == 1:
        return matches[0], None

    return None, {
        "error": "multiple_windows",
        "message": f"Multiple windows match '{app_name}'. Pass --id to choose one.",
        "windows": matches,
    }


def get_display_scale():
    """Get the display's backing scale factor directly from Quartz."""
    try:
        from Quartz import (
            CGDisplayCopyDisplayMode, CGMainDisplayID,
            CGDisplayModeGetPixelWidth, CGDisplayModeGetWidth,
        )
        mode = CGDisplayCopyDisplayMode(CGMainDisplayID())
        pixel_w = CGDisplayModeGetPixelWidth(mode)
        logical_w = CGDisplayModeGetWidth(mode)
        if logical_w > 0:
            s = pixel_w / logical_w
            if 0.8 < s < 1.2:
                return 1.0
            elif 1.8 < s < 2.2:
                return 2.0
            return s
    except Exception:
        pass
    return 1.0


def activate_app(app_name):
    """Bring an app to the foreground."""
    subprocess.run(
        ["osascript", "-e", f'tell application "{app_name}" to activate'],
        capture_output=True,
        timeout=5,
    )
    time.sleep(0.3)


def raise_window(app_name, window_title):
    """Raise a specific window to the top of the window stack via AXRaise."""
    # Escape double quotes in the title for AppleScript
    safe_title = window_title.replace('\\', '\\\\').replace('"', '\\"')
    script = (
        f'tell application "System Events" to tell process "{app_name}" '
        f'to perform action "AXRaise" of window "{safe_title}"'
    )
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        time.sleep(0.3)
    except Exception:
        pass


def activate_and_find(app_name, window_id=None):
    """Activate app first (restores from Stage Manager), then find window."""
    windows = get_windows()
    app_lower = app_name.lower()
    matches = [w for w in windows if app_lower in w["app"].lower()]
    if matches:
        activate_app(matches[0]["app"])
        time.sleep(0.3)
    return find_window(app_name, window_id)


def output(data):
    """Print JSON to stdout."""
    print(json.dumps(data, ensure_ascii=False))


def fail(data):
    """Print JSON error to stdout and exit 1."""
    output(data)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Canvas helpers
# ---------------------------------------------------------------------------

def reliable_click(x, y):
    """Click using CGEvent with proper click count and timing.
    More reliable than pyautogui for webviews and mini programs.
    """
    from Quartz import (
        CGEventCreateMouseEvent, CGEventPost,
        CGEventSetIntegerValueField,
        kCGEventLeftMouseDown, kCGEventLeftMouseUp,
        kCGMouseButtonLeft, kCGHIDEventTap,
        kCGMouseEventClickState,
    )
    point = (x, y)
    # Move mouse first so the window registers hover
    pyautogui.moveTo(x, y)
    time.sleep(0.15)
    # mouseDown with clickState=1
    down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
    CGEventSetIntegerValueField(down, kCGMouseEventClickState, 1)
    CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.08)
    # mouseUp with clickState=1
    up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
    CGEventSetIntegerValueField(up, kCGMouseEventClickState, 1)
    CGEventPost(kCGHIDEventTap, up)


def canvas_to_abs(canvas_x, canvas_y, win, scale):
    """Convert canvas coordinates (0-1000) to absolute screen coordinates."""
    orig_w = int(win["w"] * scale)
    orig_h = int(win["h"] * scale)
    fit = min(CANVAS_SIZE / orig_w, CANVAS_SIZE / orig_h)
    new_w = int(orig_w * fit)
    new_h = int(orig_h * fit)
    ox = (CANVAS_SIZE - new_w) / 2
    oy = (CANVAS_SIZE - new_h) / 2

    orig_px = (canvas_x - ox) / fit
    orig_py = (canvas_y - oy) / fit

    abs_x = win["x"] + orig_px / scale
    abs_y = win["y"] + orig_py / scale
    return abs_x, abs_y


# ---------------------------------------------------------------------------
# Screenshot, detection & annotation
# ---------------------------------------------------------------------------

def capture_full_screen():
    """Take a full-screen screenshot. Returns True on success."""
    r = subprocess.run(
        ["/usr/sbin/screencapture", "-x", SCREENSHOT_FULL],
        capture_output=True, timeout=10,
    )
    return r.returncode == 0


def crop_window(win):
    """Crop the full-screen screenshot to a window's bounds,
    then fit into a CANVAS_SIZE x CANVAS_SIZE square (no grid overlay).
    """
    img = Image.open(SCREENSHOT_FULL)
    img_w, img_h = img.size

    scale = get_display_scale()

    left = int(win["x"] * scale)
    top = int(win["y"] * scale)
    right = int((win["x"] + win["w"]) * scale)
    bottom = int((win["y"] + win["h"]) * scale)

    left = max(0, left)
    top = max(0, top)
    right = min(img_w, right)
    bottom = min(img_h, bottom)

    cropped = img.crop((left, top, right, bottom))
    orig_w, orig_h = cropped.size

    fit = min(CANVAS_SIZE / orig_w, CANVAS_SIZE / orig_h)
    new_w = int(orig_w * fit)
    new_h = int(orig_h * fit)
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (128, 128, 128, 255))
    ox = (CANVAS_SIZE - new_w) // 2
    oy = (CANVAS_SIZE - new_h) // 2
    canvas.paste(resized.convert("RGBA"), (ox, oy))

    canvas = canvas.convert("RGB")
    canvas.save(SCREENSHOT_PATH)
    return scale


def detect_text_elements(image_path):
    """Use Vision framework to detect text regions in an image.
    Returns list of dicts with text, position, size in canvas coords (0-1000).
    """
    img_url = NSURL.fileURLWithPath_(image_path)
    img_source = Quartz.CGImageSourceCreateWithURL(img_url, None)
    if not img_source:
        return []
    cg_image = Quartz.CGImageSourceCreateImageAtIndex(img_source, 0, None)
    if not cg_image:
        return []

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(["zh-Hans", "en"])
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg_image, None
    )
    success, err = handler.performRequests_error_([request], None)
    if not success:
        return []

    elements = []
    for obs in request.results():
        candidate = obs.topCandidates_(1)[0]
        text = candidate.string()
        conf = candidate.confidence()
        box = obs.boundingBox()

        # Vision coords: bottom-left origin, normalized 0-1
        # Canvas coords: top-left origin, 0-1000
        x1 = box.origin.x * CANVAS_SIZE
        y1 = (1.0 - box.origin.y - box.size.height) * CANVAS_SIZE
        w = box.size.width * CANVAS_SIZE
        h = box.size.height * CANVAS_SIZE
        cx = x1 + w / 2
        cy = y1 + h / 2

        elements.append({
            "text": text,
            "at": [round(cx), round(cy)],
            "x1": round(x1),
            "y1": round(y1),
            "w": round(w),
            "h": round(h),
            "conf": round(conf, 2),
        })

    return elements


def is_noise(elem):
    """Filter out noise elements."""
    text = elem["text"].strip()

    # Grid labels: 100-900 in multiples of 100
    if re.match(r"^\d{3}$", text):
        val = int(text)
        if val % 100 == 0 and 100 <= val <= 900:
            return True

    # Single/double digit numbers (badge counts, noise)
    if re.match(r"^\d{1,2}$", text):
        return True

    # Single punctuation or symbols
    if re.match(r"^[•·\.\*\-—_=|/\\:;,!?~`\s！？。，、]+$", text):
        return True

    return False


def draw_annotations(image_path, elements, output_path):
    """Draw numbered markers on the screenshot for each element."""
    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except Exception:
        font = ImageFont.load_default()

    for elem in elements:
        num = elem["num"]
        x1, y1, w, h = elem["x1"], elem["y1"], elem["w"], elem["h"]

        # Green bounding box
        draw.rectangle(
            [(x1 - 1, y1 - 1), (x1 + w + 1, y1 + h + 1)],
            outline=(0, 200, 0, 180),
            width=2,
        )

        # Blue number badge
        label = str(num)
        bbox = font.getbbox(label)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 3

        bx = x1 - 2
        by = y1 - th - pad * 2 - 2
        if by < 0:
            by = y1 + h + 2

        draw.rectangle(
            [(bx, by), (bx + tw + pad * 2, by + th + pad * 2)],
            fill=(0, 120, 255, 220),
        )
        draw.text((bx + pad, by + pad), label, fill=(255, 255, 255, 255), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list(_args):
    windows = get_windows()
    output(windows)


def cmd_screenshot(args):
    win, err = activate_and_find(args.app, args.id)
    if err:
        fail(err)

    # Re-activate app and raise the specific window to the top
    activate_app(win["app"])
    if win.get("title"):
        raise_window(win["app"], win["title"])

    if not capture_full_screen():
        fail({"error": "screenshot_failed",
              "message": "screencapture failed. Check Screen Recording permission."})
    try:
        scale = crop_window(win)
    except Exception as e:
        fail({"error": "crop_failed", "message": str(e)})

    # Detect text elements
    all_elements = detect_text_elements(SCREENSHOT_PATH)

    # Filter noise, require minimum confidence
    elements = [
        e for e in all_elements
        if not is_noise(e) and e["conf"] >= 0.1 and len(e["text"].strip()) > 0
    ]

    # Sort top-to-bottom, left-to-right
    elements.sort(key=lambda e: (e["at"][1] // 30, e["at"][0]))

    # Number them
    for i, elem in enumerate(elements):
        elem["num"] = i + 1

    # Draw annotations onto screenshot
    draw_annotations(SCREENSHOT_PATH, elements, SCREENSHOT_PATH)

    # Save element map for clicknum
    with open(ELEMENTS_FILE, "w") as f:
        json.dump({
            "window": {
                "id": win["id"],
                "app": win["app"],
                "title": win["title"],
                "x": win["x"], "y": win["y"],
                "w": win["w"], "h": win["h"],
            },
            "scale": scale,
            "elements": elements,
        }, f, ensure_ascii=False, indent=2)

    output({
        "file": SCREENSHOT_PATH,
        "id": win["id"],
        "app": win["app"],
        "title": win["title"],
        "scale": scale,
        "elements": [
            {"num": e["num"], "text": e["text"], "at": e["at"]}
            for e in elements
        ],
    })


def cmd_clicknum(args):
    """Click on element N from the last screenshot."""
    try:
        with open(ELEMENTS_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        fail({"error": "no_elements", "message": "Run screenshot first."})

    num = args.num
    elements = data["elements"]
    match = [e for e in elements if e["num"] == num]
    if not match:
        fail({
            "error": "invalid_num",
            "message": f"Element {num} not found. Valid: 1-{len(elements)}",
        })

    elem = match[0]
    win_data = data["window"]
    scale = data["scale"]

    # Activate window
    win, err = activate_and_find(win_data["app"], win_data["id"])
    if err:
        fail(err)

    # Convert canvas coords to absolute screen coords
    abs_x, abs_y = canvas_to_abs(elem["at"][0], elem["at"][1], win, scale)

    reliable_click(abs_x, abs_y)

    output({
        "ok": True,
        "clicked_num": num,
        "text": elem["text"],
        "canvas": elem["at"],
        "abs": [round(abs_x), round(abs_y)],
    })


def cmd_click(args):
    win, err = activate_and_find(args.app, args.id)
    if err:
        fail(err)

    scale = get_display_scale()
    abs_x, abs_y = canvas_to_abs(args.x, args.y, win, scale)

    reliable_click(abs_x, abs_y)

    output({"ok": True, "clicked": [round(abs_x), round(abs_y)], "scale": scale})


def cmd_scroll(args):
    win, err = activate_and_find(args.app, args.id)
    if err:
        fail(err)

    cx = win["x"] + win["w"] / 2
    cy = win["y"] + win["h"] / 2
    pyautogui.moveTo(cx, cy)

    d = args.direction.lower()
    n = args.amount
    if d == "down":
        pyautogui.scroll(-n)
    elif d == "up":
        pyautogui.scroll(n)
    elif d == "left":
        pyautogui.hscroll(-n)
    elif d == "right":
        pyautogui.hscroll(n)
    else:
        fail({"error": "invalid_direction", "message": f"Use up/down/left/right, got '{d}'"})

    output({"ok": True, "scrolled": d, "amount": n})


def keystroke_via_osascript(key, modifiers=None):
    """Send a keystroke via osascript (System Events)."""
    if modifiers:
        if len(modifiers) == 1:
            mod_str = f" using {modifiers[0]} down"
        else:
            mod_str = " using {" + ", ".join(f"{m} down" for m in modifiers) + "}"
    else:
        mod_str = ""
    script = f'tell application "System Events" to keystroke "{key}"{mod_str}'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    if r.returncode != 0:
        sys.stderr.write(f"osascript keystroke failed: {r.stderr.decode().strip()}\n")


def keycode_via_osascript(code, modifiers=None):
    """Send a key code via osascript (System Events)."""
    if modifiers:
        if len(modifiers) == 1:
            mod_str = f" using {modifiers[0]} down"
        else:
            mod_str = " using {" + ", ".join(f"{m} down" for m in modifiers) + "}"
    else:
        mod_str = ""
    script = f'tell application "System Events" to key code {code}{mod_str}'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    if r.returncode != 0:
        sys.stderr.write(f"osascript keycode failed: {r.stderr.decode().strip()}\n")


def cmd_type(args):
    if args.app:
        activate_and_find(args.app)

    proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    proc.communicate(args.text.encode("utf-8"))

    keystroke_via_osascript("v", ["command"])
    time.sleep(0.1)

    output({"ok": True, "typed": len(args.text)})


def cmd_key(args):
    if args.app:
        activate_and_find(args.app)

    combo = args.combo
    parts = [p.strip() for p in combo.split("+")]

    modifier_names = {"cmd", "ctrl", "alt", "opt", "shift", "command", "control", "option"}
    modifiers = []
    main_key = None

    for p in parts:
        low = p.lower()
        if low in modifier_names:
            mod_map = {
                "cmd": "command", "command": "command",
                "ctrl": "control", "control": "control",
                "alt": "option", "opt": "option", "option": "option",
                "shift": "shift",
            }
            modifiers.append(mod_map[low])
        else:
            main_key = low

    if main_key is None:
        fail({"error": "no_key", "message": f"No key specified in combo '{combo}'"})

    keycode_map = {
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "delete": 51, "backspace": 51, "escape": 53, "esc": 53,
        "up": 126, "down": 125, "left": 123, "right": 124,
        "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
    }

    if main_key in keycode_map:
        keycode_via_osascript(keycode_map[main_key], modifiers if modifiers else None)
    else:
        keystroke_via_osascript(main_key, modifiers if modifiers else None)

    output({"ok": True, "pressed": combo})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="macOS GUI automation helper")
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="List all visible windows")

    # screenshot (with annotation)
    p_ss = sub.add_parser("screenshot", help="Screenshot + annotate an app window")
    p_ss.add_argument("app", help="App name (fuzzy, case-insensitive)")
    p_ss.add_argument("--id", type=int, default=None, help="Window ID for disambiguation")

    # clicknum
    p_cn = sub.add_parser("clicknum", help="Click element N from last screenshot")
    p_cn.add_argument("num", type=int, help="Element number to click")

    # click (legacy — direct canvas coords)
    p_cl = sub.add_parser("click", help="Click at canvas coords (0-1000)")
    p_cl.add_argument("--app", required=True, help="App name (fuzzy)")
    p_cl.add_argument("--id", type=int, default=None, help="Window ID")
    p_cl.add_argument("x", type=int, help="Canvas X coordinate (0-1000)")
    p_cl.add_argument("y", type=int, help="Canvas Y coordinate (0-1000)")

    # scroll
    p_sc = sub.add_parser("scroll", help="Scroll inside an app window")
    p_sc.add_argument("--app", required=True, help="App name (fuzzy)")
    p_sc.add_argument("--id", type=int, default=None, help="Window ID")
    p_sc.add_argument("direction", choices=["up", "down", "left", "right"])
    p_sc.add_argument("amount", type=int, help="Scroll clicks (3-5 moderate, 10+ fast)")

    # type
    p_ty = sub.add_parser("type", help="Type text via clipboard paste")
    p_ty.add_argument("--app", default=None, help="App name to activate first (fuzzy)")
    p_ty.add_argument("text", help="Text to type")

    # key
    p_ke = sub.add_parser("key", help="Press key or combo (e.g. return, cmd+v)")
    p_ke.add_argument("--app", default=None, help="App name to activate first (fuzzy)")
    p_ke.add_argument("combo", help="Key combo like 'return', 'cmd+v', 'cmd+shift+s'")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "list": cmd_list,
        "screenshot": cmd_screenshot,
        "clicknum": cmd_clicknum,
        "click": cmd_click,
        "scroll": cmd_scroll,
        "type": cmd_type,
        "key": cmd_key,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
