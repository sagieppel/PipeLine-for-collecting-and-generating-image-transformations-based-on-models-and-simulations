"""
animation_viewer.py
-------------------
Display multiple image sequences as animations alongside a filmstrip preview.

Usage
-----
    show_sequences(
        sequences   = [["a1.png", "a2.png", ...], ["b1.png", ...]],
        sz          = (256, 256),          # (height, width) in pixels
        n_im        = 5,                   # frames shown in filmstrip
        key_map     = {'k': 'keep', 'r': 'reject'},
        initial_list= [],                  # optional pre-selected items
    )
    # Returns the selected-items list when SPACE is pressed.
"""

import tkinter as tk
from tkinter import ttk

from IPython.terminal.shortcuts.auto_suggest import accept
from PIL import Image, ImageTk
import numpy as np
import json
import pickle
import time
import os, tempfile, math

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_frames(paths: list[str], sz: tuple[int, int]) -> list:
    """Load & resize images; return list of PIL Images."""
    h, w = sz
    frames = []
    for p in paths:
        try:
            img = Image.open(p).convert("RGBA").resize((w, h), Image.LANCZOS)
        except Exception:
            img = Image.new("RGBA", (w, h), (60, 60, 60, 255))
        frames.append(img)
    return frames


def _make_tk_image(pil_img) -> ImageTk.PhotoImage:
    return ImageTk.PhotoImage(pil_img)


# ──────────────────────────────────────────────────────────────────────────────
# Main function
# ──────────────────────────────────────────────────────────────────────────────

def show_sequences(
    sequences: list[list[str]],
    sz: tuple[int, int] = (128, 128),
    n_im: int = 5,
    key_map: dict[str, str] | None = None,
    initial_list: list[str] | None = None,
    title: str = "Sequence Viewer",
) -> list[str]:
    """
    Parameters
    ----------
    sequences    : list of lists of image paths (one list per animation row).
    sz           : (height, width) every image is resized to this.
    n_im         : number of frames shown in the filmstrip (right panel).
    key_map      : {'letter': 'word', ...} — keyboard shortcuts for tagging.
    initial_list : optional pre-populated selection list.
    title        : window title and banner text displayed in the control panel.

    Returns
    -------
    List of selected words when SPACE is pressed.
    """
    if key_map is None:
        key_map = {}
    selected: list[str] = list(initial_list) if initial_list else []

    h, w = sz
    PAD = 8
    STRIP_GAP = 4          # gap between filmstrip thumbnails
    FPS_DEFAULT = 0.1     # seconds between frames

    # ── load all frames ──────────────────────────────────────────────────────
    all_frames: list[list] = [_load_frames(seq, sz) for seq in sequences]
    n_rows = len(all_frames)

    # ── layout math ──────────────────────────────────────────────────────────
    anim_col_w  = w + PAD * 2
    strip_col_w = n_im * (w + STRIP_GAP) + PAD * 2
    row_h       = h + PAD * 2

    CTRL_W      = 260      # right control panel width
    canvas_w    = anim_col_w + strip_col_w
    canvas_h    = n_rows * row_h + PAD
    win_w       = canvas_w + CTRL_W + PAD * 3
    win_h       = max(canvas_h + 100, 420)

    # ── window ───────────────────────────────────────────────────────────────
    root = tk.Tk()
    root.title(title)
    root.configure(bg="#1a1a2e")
    root.resizable(False, False)
    root.geometry(f"{win_w}x{win_h}")

    # keep PhotoImage refs alive
    _photo_cache: list = []

    # ── left: canvas for animations + filmstrips ──────────────────────────────
    canvas_frame = tk.Frame(root, bg="#1a1a2e")
    canvas_frame.grid(row=0, column=0, padx=PAD, pady=PAD, sticky="nsew")

    canvas = tk.Canvas(
        canvas_frame,
        width=canvas_w,
        height=canvas_h,
        bg="#16213e",
        highlightthickness=1,
        highlightbackground="#0f3460",
    )
    canvas.pack()

    # draw row separators & labels
    for r in range(n_rows):
        y_top = r * row_h + PAD
        canvas.create_text(
            PAD + 4, y_top + 4,
            text=f"#{r+1}",
            fill="#e94560",
            font=("Courier", 9, "bold"),
            anchor="nw",
        )

    # ── right: scrollable control panel ──────────────────────────────────────
    # Outer container (fixed width, full height)
    ctrl_outer = tk.Frame(root, bg="#0f3460", width=CTRL_W)
    ctrl_outer.grid(row=0, column=1, padx=(0, PAD), pady=PAD, sticky="nsew")
    ctrl_outer.pack_propagate(False)
    ctrl_outer.grid_propagate(False)

    # Scrollable canvas + inner frame
    ctrl_canvas = tk.Canvas(ctrl_outer, bg="#0f3460", highlightthickness=0,
                            width=CTRL_W - 14)
    ctrl_scroll = tk.Scrollbar(ctrl_outer, orient="vertical",
                               command=ctrl_canvas.yview)
    ctrl_canvas.configure(yscrollcommand=ctrl_scroll.set)

    ctrl_scroll.pack(side="right", fill="y")
    ctrl_canvas.pack(side="left", fill="both", expand=True)

    # The actual frame that holds all widgets lives inside the canvas
    ctrl = tk.Frame(ctrl_canvas, bg="#0f3460")
    ctrl_window = ctrl_canvas.create_window((0, 0), window=ctrl, anchor="nw",
                                            width=CTRL_W - 14)

    def _on_ctrl_configure(event):
        ctrl_canvas.configure(scrollregion=ctrl_canvas.bbox("all"))

    def _on_canvas_configure(event):
        ctrl_canvas.itemconfig(ctrl_window, width=event.width)

    ctrl.bind("<Configure>", _on_ctrl_configure)
    ctrl_canvas.bind("<Configure>", _on_canvas_configure)

    # Force geometry pass so content is visible on first paint
    root.update_idletasks()

    # Mouse-wheel scrolling (works on Windows, Mac, Linux)
    def _on_mousewheel(event):
        if event.num == 4:          # Linux scroll up
            ctrl_canvas.yview_scroll(-1, "units")
        elif event.num == 5:        # Linux scroll down
            ctrl_canvas.yview_scroll(1, "units")
        else:                       # Windows / Mac
            ctrl_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    ctrl_canvas.bind("<MouseWheel>", _on_mousewheel)
    ctrl_canvas.bind("<Button-4>", _on_mousewheel)
    ctrl_canvas.bind("<Button-5>", _on_mousewheel)
    ctrl.bind("<MouseWheel>", _on_mousewheel)
    ctrl.bind("<Button-4>", _on_mousewheel)
    ctrl.bind("<Button-5>", _on_mousewheel)

    # title
    tk.Label(ctrl, text=title.upper(), bg="#0f3460", fg="#e94560",
             font=("Courier", 11, "bold"), wraplength=CTRL_W - 24).pack(pady=(14, 4))
    ttk.Separator(ctrl, orient="horizontal").pack(fill="x", padx=8, pady=4)

    # ── speed control ─────────────────────────────────────────────────────────
    tk.Label(ctrl, text="Frame delay (s)", bg="#0f3460", fg="#a8dadc",
             font=("Courier", 9)).pack(anchor="w", padx=12, pady=(8, 0))

    delay_var = tk.DoubleVar(value=FPS_DEFAULT)

    delay_frame = tk.Frame(ctrl, bg="#0f3460")
    delay_frame.pack(fill="x", padx=12, pady=2)

    delay_label = tk.Label(delay_frame, text=f"{FPS_DEFAULT:.2f}s",
                           bg="#0f3460", fg="#e94560",
                           font=("Courier", 10, "bold"), width=6)
    delay_label.pack(side="right")

    def on_delay_change(val):
        delay_label.config(text=f"{float(val):.2f}s")

    delay_slider = tk.Scale(
        ctrl, from_=0.05, to=2.0, resolution=0.05,
        orient="horizontal", variable=delay_var,
        bg="#0f3460", fg="#a8dadc", troughcolor="#16213e",
        highlightthickness=0, showvalue=False,
        command=on_delay_change,
        length=CTRL_W - 40,
    )
    delay_slider.pack(padx=12)

    ttk.Separator(ctrl, orient="horizontal").pack(fill="x", padx=8, pady=6)

    # ── key-map buttons ───────────────────────────────────────────────────────
    tk.Label(ctrl, text="KEYBOARD SHORTCUTS", bg="#0f3460", fg="#a8dadc",
             font=("Courier", 9, "bold")).pack(anchor="w", padx=12)

    btn_frames: dict[str, tk.Label] = {}
    for key, word in key_map.items():
        row_f = tk.Frame(ctrl, bg="#0f3460")
        row_f.pack(fill="x", padx=12, pady=3)

        key_lbl = tk.Label(row_f, text=f"[{key.upper()}]",
                           bg="#e94560", fg="white",
                           font=("Courier", 10, "bold"),
                           width=4, relief="flat")
        key_lbl.pack(side="left")

        word_lbl = tk.Label(row_f, text=word,
                            bg="#16213e", fg="#a8dadc",
                            font=("Courier", 10),
                            anchor="w", padx=6)
        word_lbl.pack(side="left", fill="x", expand=True)
        btn_frames[key.lower()] = word_lbl

        # propagate scroll to child widgets too
        for _w in (row_f, key_lbl, word_lbl):
            _w.bind("<MouseWheel>", _on_mousewheel)
            _w.bind("<Button-4>", _on_mousewheel)
            _w.bind("<Button-5>", _on_mousewheel)

    if key_map:
        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", padx=8, pady=6)

    # ── selected list display ─────────────────────────────────────────────────
    tk.Label(ctrl, text="SELECTED", bg="#0f3460", fg="#a8dadc",
             font=("Courier", 9, "bold")).pack(anchor="w", padx=12)

    list_var = tk.StringVar()
    list_box = tk.Listbox(
        ctrl,
        listvariable=list_var,
        bg="#16213e", fg="#e2e2e2",
        font=("Courier", 10),
        selectbackground="#e94560",
        relief="flat",
        highlightthickness=0,
        height=6,
        borderwidth=0,
    )
    list_box.pack(fill="x", padx=12, pady=4)

    def refresh_list():
        list_var.set(selected)
        # update button highlight
        for key, word in key_map.items():
            lbl = btn_frames.get(key.lower())
            if lbl:
                active = word in selected
                lbl.config(
                    bg="#e94560" if active else "#16213e",
                    fg="white" if active else "#a8dadc",
                )

    refresh_list()

    ttk.Separator(ctrl, orient="horizontal").pack(fill="x", padx=8, pady=6)
    tk.Label(ctrl, text="SPACE  →  close & return",
             bg="#0f3460", fg="#555577",
             font=("Courier", 8)).pack(anchor="w", padx=12, pady=(0, 12))

    # ── animation state ───────────────────────────────────────────────────────
    frame_indices = [0] * n_rows
    anim_ids: dict[str, int] = {}    # canvas image-item ids
    strip_ids: list[list[int]] = [[] for _ in range(n_rows)]

    # pre-render filmstrips (evenly spaced n_im frames from each sequence)
    filmstrip_photos: list[list] = []

    for r, frames in enumerate(all_frames):
        n = len(frames)
        if n == 0:
            filmstrip_photos.append([])
            continue
        # pick n_im evenly spaced indices
        indices = [int(i * (n - 1) / max(n_im - 1, 1)) for i in range(n_im)] if n_im > 1 else [0]
        photos = [_make_tk_image(frames[idx]) for idx in indices]
        _photo_cache.extend(photos)
        filmstrip_photos.append(photos)

        # draw strip
        y_center = r * row_h + PAD + h // 2
        x_start  = anim_col_w + PAD
        for i, ph in enumerate(photos):
            x = x_start + i * (w + STRIP_GAP)
            sid = canvas.create_image(x, y_center - h // 2, anchor="nw", image=ph)
            strip_ids[r].append(sid)
            # frame border
            canvas.create_rectangle(
                x - 1, y_center - h // 2 - 1,
                x + w, y_center + h // 2,
                outline="#0f3460", width=1,
            )

    # initial animation photos
    anim_photos: list = []
    for r, frames in enumerate(all_frames):
        if not frames:
            anim_photos.append(None)
            continue
        ph = _make_tk_image(frames[0])
        _photo_cache.append(ph)
        y_center = r * row_h + PAD + h // 2
        iid = canvas.create_image(PAD, y_center - h // 2, anchor="nw", image=ph)
        anim_ids[r] = iid
        anim_photos.append(ph)

    # ── animation loop ────────────────────────────────────────────────────────
    running = True

    def animate():
        if not running:
            return
        delay_ms = int(delay_var.get() * 1000)

        for r, frames in enumerate(all_frames):
            if not frames:
                continue
            frame_indices[r] = (frame_indices[r] + 1) % len(frames)
            ph = _make_tk_image(frames[frame_indices[r]])
            _photo_cache.append(ph)
            # trim cache to avoid unbounded growth
            if len(_photo_cache) > 500:
                del _photo_cache[:100]
            canvas.itemconfig(anim_ids[r], image=ph)
            anim_photos[r] = ph

        root.after(delay_ms, animate)

    root.after(int(delay_var.get() * 1000), animate)

    # ── keyboard ──────────────────────────────────────────────────────────────
    def on_key(event: tk.Event):
        nonlocal running
        ch = event.keysym.lower()

        if event.keysym == "space":
            running = False
            root.destroy()
            return

        if ch in key_map or event.char.lower() in key_map:
            k = ch if ch in key_map else event.char.lower()
            word = key_map[k]
            if word in selected:
                selected.remove(word)
            else:
                selected.append(word)
            refresh_list()

    root.bind("<KeyPress>", on_key)
    root.focus_set()

    root.mainloop()
    return selected


# ──────────────────────────────────────────────────────────────────────────────
# Demo / smoke-test  (runs when executed directly)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    redo=False
    num_rejects=0
    options=["strong","medium","weak","reject","accept","not transition","1","2","3","4","5","6","7","8","9","x10","+"]
    key_map = {}
    for word in options:
        if word[0] in key_map:
            print("overlaping keys")
            exit(0)
        key_map[word[0]] = word


    trans_subdirs=["results/PBR/BaseColor","results/RGB"]
    imdr_name="results"
    main_dir= r"/media/fogbrain/6TB/python_project/PBR2PBR_Transformation/Single_Image_Transformation"
    num_done=0
    fail=True
    for sdr  in os.listdir(main_dir):
        topic_dir = os.path.join(main_dir,sdr)#,imdr_name)
       # outcome_file = os.path.join(main_dir,sdr,"manual_selection.json")
        for trans_dir in os.listdir(topic_dir):
            dr = os.path.join(topic_dir,trans_dir)
            results=[]
            # if os.path.exists(outcome_file):
            #     if not redo: continue
            #     results=json.load(open(outcome_file,"r", encoding="utf-8"))
            if not os.path.isdir(dr): continue
            num_done+=1
            outcome_path = os.path.join(dr,"outcome.json")
            if os.path.isfile(outcome_path):# and redo:
                results=json.load(open(outcome_path,"r"))
                #**************************************************************
                t=False

                if  "x10" not in results:
                      for ky in ["1","2","3","4","5","6","7","8","9"]:
                           if ky in results:
                               t=True
                if t==False:#"reject" in results or 'accept' in results:
                    num_rejects += 1
                    print("num rejects",num_rejects)
                    continue
                #***************************************************************************
            elif os.path.isfile(outcome_path):
                continue
            list_list=[]
            for nm in trans_subdirs:
                  list_im=[dr+"//"+nm+"//start.jpg"]
                  if not os.path.exists(list_im[0]): break
                  for ii in range(1,100):
                       pth=os.path.join(dr,nm,str(ii)+".jpg")
                       if not os.path.exists(pth): break
                       list_im.append(pth)
                  if os.path.exists(dr+"//"+nm+"finish.jpg"):
                     list_im.append(dr+"//"+nm+"finish.jpg")

                  if len(list_im)<2: break
                  list_list.append(list_im)
            if len(list_list)<2:
                result=["reject"]
            else:
                result = show_sequences(
                        sequences=list_list,
                        sz=(256, 256),
                        n_im=np.min([5, len(list_list[0])]),
                        key_map=key_map,
                        initial_list=results,
                        title=str(num_done)+") "+trans_dir + "  Num frames "+str(len(list_list[0]))
                    )

            with open(outcome_path, "w",encoding="utf-8") as f: json.dump(result, f)
            # with open(outcome_file.replace(".json",".pkl"), "wb") as f: pickle.dump(result, f)
            #


