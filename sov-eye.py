#!/usr/bin/env python3
"""
sov-eye — sovereign screen sight
==================================
Grabs the screen. Pops it up floating. AI can read it.

The eyepodermic. The sight bulb.

Usage:
  python3 sov-eye.py          # grab + show floating window
  python3 sov-eye.py --grab   # grab only, no popup (for AI reads)
  python3 sov-eye.py --crop   # grab + let you click-drag a region
"""
import os, sys, subprocess, time, argparse
from pathlib import Path

OUT   = "/tmp/sov-eye.png"
CROP  = "/tmp/sov-eye-crop.png"

PINK = "\033[38;2;255;105;180m"
LIME = "\033[38;2;57;255;100m"
CYAN = "\033[38;2;0;220;255m"
GRAY = "\033[38;2;85;85;105m"
RST  = "\033[0m"
BOLD = "\033[1m"

def grab(path=OUT, select=False):
    """Take a screenshot. select=True for click-drag region."""
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    if select:
        # scrot -s = click-drag to select region
        r = subprocess.run(["scrot", "-s", path], env=env)
    else:
        r = subprocess.run(["scrot", path], env=env)
    return r.returncode == 0

def show_feh(path):
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    subprocess.Popen(
        ["feh", "--geometry", "960x600+100+100", "--title", "sov-eye", path],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def show_eog(path):
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    subprocess.Popen(
        ["eog", path],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def show_display(path):
    """ImageMagick display as fallback."""
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    subprocess.Popen(
        ["display", "-title", "sov-eye", "-resize", "960x600>", path],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def show_tkinter(path):
    """Pure python fallback — always-on-top floating window."""
    import tkinter as tk
    from PIL import Image, ImageTk

    root = tk.Tk()
    root.title("sov-eye")
    root.configure(bg="black")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.95)

    img  = Image.open(path)
    # scale to fit ~960 wide
    w, h = img.size
    scale = min(960 / w, 600 / h)
    img  = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)

    lbl = tk.Label(root, image=photo, bg="black", bd=2, relief="solid",
                   highlightbackground="#00dcff", highlightthickness=2)
    lbl.pack(padx=4, pady=4)

    # close on click or Escape
    lbl.bind("<Button-1>", lambda e: root.destroy())
    root.bind("<Escape>",  lambda e: root.destroy())

    root.mainloop()

def popup(path):
    """Try viewers in order of preference."""
    for fn in (show_feh, show_eog, show_display):
        try:
            fn(path)
            return
        except FileNotFoundError:
            continue
    # last resort
    try:
        show_tkinter(path)
    except Exception as e:
        print(f"  {GRAY}no viewer found ({e}) — image at {path}{RST}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grab",  action="store_true", help="grab only, no popup")
    parser.add_argument("--crop",  action="store_true", help="click-drag region")
    args = parser.parse_args()

    print(f"\n{CYAN}{BOLD}  sov-eye{RST}  {GRAY}sight bulb — grabbing screen...{RST}", flush=True)

    path   = CROP if args.crop else OUT
    select = args.crop

    ok = grab(path, select=select)

    if not ok:
        print(f"  scrot failed — is DISPLAY set?")
        sys.exit(1)

    size = Path(path).stat().st_size // 1024
    print(f"  {LIME}✓{RST}  captured → {CYAN}{path}{RST}  {GRAY}({size}K){RST}")

    if not args.grab:
        popup(path)
        print(f"  {GRAY}(click image or Escape to close){RST}\n")
    else:
        print(f"  {GRAY}grab-only mode — no popup{RST}\n")

if __name__ == "__main__":
    main()
