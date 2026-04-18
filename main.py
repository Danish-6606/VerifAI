import flet as ft
import threading
import subprocess
import sys
import re
import os
from engine import MODEL

ALIGN_CENTER = ft.alignment.Alignment(0, 0)

def pad_all(v):         return ft.Padding(v, v, v, v)
def pad_sym(h=0, v=0):  return ft.Padding(h, v, h, v)
def pad_only(**kw):     return ft.Padding(kw.get("left",0), kw.get("top",0),
                                          kw.get("right",0), kw.get("bottom",0))
def border_all(w, c):   return ft.Border(ft.BorderSide(w,c), ft.BorderSide(w,c),
                                         ft.BorderSide(w,c), ft.BorderSide(w,c))
def border_right(w,c):  return ft.Border(right=ft.BorderSide(w,c))
def border_bottom(w,c): return ft.Border(bottom=ft.BorderSide(w,c))

_PICKER_SCRIPT = """
import tkinter as tk
from tkinter import filedialog
import subprocess, sys, platform

root = tk.Tk()
root.withdraw()
root.lift()
root.attributes('-topmost', True)

# Force the dialog to the front on macOS
if platform.system() == 'Darwin':
    try:
        subprocess.run(
            ['osascript', '-e',
             'tell application "System Events" to set frontmost of '
             '(first process whose unix id is ' + str(__import__("os").getpid()) + ') to true'],
            capture_output=True)
    except Exception:
        pass

root.focus_force()
path = filedialog.askopenfilename(
    title='Select a document',
    filetypes=[('Supported files','*.pdf *.docx *.txt'),
               ('PDF files','*.pdf'),
               ('Word documents','*.docx'),
               ('Text files','*.txt'),
               ('All files','*.*')])
root.destroy()
print(path or '', end='')
"""

def pick_file_via_subprocess() -> str | None:
    r = subprocess.run([sys.executable, "-c", _PICKER_SCRIPT],
                       capture_output=True, text=True)
    p = r.stdout.strip()
    return p if p else None

audit_history: list[dict] = []

C = {
    "bg":"#080B10","sidebar":"#0C0F16","card":"#050709",
    "border":"#1A2235","border2":"#111827",
    "blue":"#3B82F6","blue_dim":"#1E3A5F",
    "green":"#10B981","green_bg":"#052E16","green_bdr":"#064E3B",
    "red":"#EF4444","red_dim":"#F87171",
    "yellow":"#F59E0B","purple":"#8B5CF6","purple_bg":"#1E1040",
    "teal":"#14B8A6","teal_bg":"#042F2E",
    "orange":"#F97316","orange_bg":"#1C0F05",
    "text":"#E5E7EB","muted":"#9CA3AF","dim":"#6B7280",
    "darker":"#374151","darkest":"#1F2937",
}

RISK_KW = ["liability","indemnif","terminat","penalty","unlimited","waive",
           "forfeit","breach","arbitrat","govern","jurisdiction","non-compete",
           "sublicense","auto-renew","force majeure","consequential"]

MODES = [
    ("contract",   "Contract Audit",           ft.Icons.GAVEL_ROUNDED,            C["blue"]),
    ("nda",        "NDA / Privacy Policy",      ft.Icons.LOCK_OUTLINE_ROUNDED,     C["purple"]),
    ("employment", "Employment Agreement",      ft.Icons.BADGE_ROUNDED,            C["teal"]),
    ("tos",        "Terms of Service / EULA",   ft.Icons.ARTICLE_ROUNDED,          C["orange"]),
    ("compare",    "Compare Documents",         ft.Icons.COMPARE_ARROWS_ROUNDED,   C["yellow"]),
]

def fname(path: str) -> str:
    return path.replace("\\", "/").split("/")[-1] if path else ""

def main(page: ft.Page):
    page.title         = "VerifAI | Smart Legal Intelligence"
    page.theme_mode    = ft.ThemeMode.DARK
    page.window_width  = 1180
    page.window_height = 880
    page.bgcolor       = C["bg"]
    page.padding       = 0

    # ── state ─────────────────────────────────────────────────────────────────
    sel_file:    list[str|None] = [None]
    sel_file_b:  list[str|None] = [None]   # for compare mode
    cur_view:    list[str]      = ["audit"]
    cur_mode:    list[str]      = ["contract"]

    # ── shared atoms ──────────────────────────────────────────────────────────
    status_dot   = ft.Container(width=8, height=8, bgcolor=C["green"], border_radius=4)
    status_label = ft.Text("SYSTEM READY", size=10, weight=ft.FontWeight.W_700, color=C["green"])
    file_name_lbl = ft.Text("No file selected", size=12, color=C["dim"])
    file_b_lbl    = ft.Text("No second file", size=12, color=C["dim"])
    progress_ring = ft.ProgressRing(width=18, height=18, stroke_width=2,
                                    color=C["blue"], visible=False)
    results_scroll = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)
    content_panel  = ft.Container(expand=True, bgcolor=C["bg"])
    mode_label_ref = ft.Text("Contract Audit", size=26,
                              weight=ft.FontWeight.W_700, color="white")

    # ── helpers ───────────────────────────────────────────────────────────────
    def set_status(label, color):
        status_dot.bgcolor = color; status_label.value = label; status_label.color = color
        page.update()

    def centered_box(controls, height=340):
        return ft.Container(
            content=ft.Column(controls,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER, spacing=16),
            alignment=ALIGN_CENTER, height=height, expand=True)

    def mode_color() -> str:
        for m, _, _, color in MODES:
            if m == cur_mode[0]: return color
        return C["blue"]

    # ── result renderer ───────────────────────────────────────────────────────
    def render_results(text: str):
        results_scroll.controls.clear()

        def clean(s: str) -> str:
            return re.sub(r'\bL(\d+):', r'Line \1:', s)

        VERDICTS = ["REJECT THIS", "NEGOTIATE BEFORE", "ACCEPTABLE WITH",
                    "SAFE TO SIGN", "DO NOT SIGN", "AVOID THIS",
                    "PREFER DOCUMENT", "NEITHER IS", "BOTH ACCEPTABLE",
                    "USE WITH", "SAFE TO USE"]
        VERDICT_COLORS = {
            "REJECT":     (C["red"],    "#1a0505"),
            "DO NOT":     (C["red"],    "#1a0505"),
            "AVOID":      (C["red"],    "#1a0505"),
            "NEGOTIATE":  (C["yellow"], "#1a1205"),
            "ACCEPTABLE": (C["orange"], "#1a0e05"),
            "SAFE":       (C["green"],  "#051a0e"),
            "PREFER":     (C["blue"],   "#05101a"),
            "NEITHER":    (C["yellow"], "#1a1205"),
            "BOTH":       (C["green"],  "#051a0e"),
            "USE WITH":   (C["yellow"], "#1a1205"),
        }

        in_final_verdict = False
        pending_bubble: list = []

        def flush_pending():
            if pending_bubble:
                results_scroll.controls.append(pending_bubble[0])
                pending_bubble.clear()

        for line in text.strip().splitlines():
            s = line.strip()
            if not s:
                flush_pending()
                results_scroll.controls.append(ft.Container(height=6))
                continue

            # ── Section headers ───────────────────────────────────────
            if s.endswith(":") and s == s.upper() and len(s) < 70:
                flush_pending()
                in_final_verdict = "FINAL VERDICT" in s
                hdr_color = C["green"] if in_final_verdict else mode_color()
                results_scroll.controls.append(ft.Container(
                    content=ft.Text(s, size=13, weight=ft.FontWeight.W_700,
                                    color=hdr_color),
                    padding=pad_only(top=20, bottom=6)))

            # ── Verdict banner ────────────────────────────────────────
            elif in_final_verdict and any(v in s.upper() for v in VERDICTS):
                flush_pending()
                v_key = next((k for k in VERDICT_COLORS if s.upper().startswith(k)), None)
                txt_c, bg_c = VERDICT_COLORS.get(v_key, (C["muted"], C["card"]))
                results_scroll.controls.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.GAVEL_ROUNDED, size=16, color=txt_c),
                        ft.Text(s, size=13, weight=ft.FontWeight.W_700,
                                color=txt_c, selectable=True),
                    ], spacing=10),
                    bgcolor=bg_c, border=border_all(1, txt_c),
                    border_radius=8, padding=pad_sym(h=14, v=10),
                    margin=ft.Margin(0, 4, 0, 8)))

            # ── Inline suggestion (→) ─────────────────────────────────
            elif s.startswith("\u2192") or s.startswith("->") or s.startswith("=>"):
                sug = clean(s.lstrip("\u2192->=> ").strip())
                suggestion_card = ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Icon(ft.Icons.LIGHTBULB_ROUNDED,
                                            size=13, color="#10B981"),
                            width=26, height=26, bgcolor="#052E16",
                            border_radius=13, alignment=ALIGN_CENTER),
                        ft.Column([
                            ft.Text("SUGGESTION", size=9,
                                    weight=ft.FontWeight.W_700, color="#10B981"),
                            ft.Text(sug, size=12, color="#D1FAE5",
                                    selectable=True, expand=True),
                        ], spacing=2, expand=True),
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
                    bgcolor="#031a0e",
                    border=ft.Border(
                        left=ft.BorderSide(3, "#10B981"),
                        top=ft.BorderSide(1, "#064E3B"),
                        right=ft.BorderSide(1, "#064E3B"),
                        bottom=ft.BorderSide(1, "#064E3B"),
                    ),
                    border_radius=ft.BorderRadius(0, 8, 8, 0),
                    padding=ft.Padding(12, 8, 12, 8),
                    margin=ft.Margin(20, 0, 0, 8),
                )
                if pending_bubble:
                    combined = ft.Container(
                        content=ft.Column([pending_bubble[0], suggestion_card], spacing=0))
                    results_scroll.controls.append(combined)
                    pending_bubble.clear()
                else:
                    results_scroll.controls.append(suggestion_card)

            # ── Risk / finding bullet ─────────────────────────────────
            elif s.startswith(("\u2022", "-", "*", "\u00b7", "\u2013")):
                flush_pending()
                body = clean(s.lstrip("\u2022-*\u00b7\u2013 ").strip())
                risk = any(k in body.lower() for k in RISK_KW)
                loc  = re.search(r'(Page\s*\d+[,\s]*(?:Line\s*\d+)?)',
                                 body, re.IGNORECASE)
                dot_c = C["red"] if risk else mode_color()
                txt_c = C["red_dim"] if risk else C["text"]
                bubble = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Container(width=7, height=7, bgcolor=dot_c,
                                         border_radius=4,
                                         margin=ft.Margin(0, 5, 10, 0)),
                            ft.Text(body, size=13, color=txt_c,
                                    expand=True, selectable=True),
                        ], vertical_alignment=ft.CrossAxisAlignment.START),
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.LOCATION_ON_ROUNDED,
                                        size=11, color="#60A5FA"),
                                ft.Text(loc.group(1).strip(), size=10, color="#60A5FA"),
                            ], spacing=3),
                            padding=ft.Padding(18, 2, 0, 0),
                            visible=loc is not None),
                    ], spacing=2),
                    padding=ft.Padding(12, 8, 12, 8),
                    bgcolor="#0c111a" if risk else "transparent",
                    border_radius=ft.BorderRadius(8, 8, 0, 0) if risk else 8,
                    border=ft.Border(
                        left=ft.BorderSide(3, dot_c),
                        top=ft.BorderSide(1, "#1A2235") if risk else ft.BorderSide(0, "transparent"),
                        right=ft.BorderSide(1, "#1A2235") if risk else ft.BorderSide(0, "transparent"),
                        bottom=ft.BorderSide(0, "transparent"),
                    ),
                    margin=ft.Margin(0, 4, 0, 0),
                )
                pending_bubble.append(bubble)

            # ── Numbered ──────────────────────────────────────────────
            elif len(s) > 2 and s[0].isdigit() and s[1] in ".):":
                flush_pending()
                results_scroll.controls.append(ft.Container(
                    content=ft.Text(clean(s), size=13, color=C["text"], selectable=True),
                    padding=pad_sym(h=4, v=2)))

            # ── Plain text ────────────────────────────────────────────
            else:
                flush_pending()
                results_scroll.controls.append(
                    ft.Text(clean(s), size=13, color=C["muted"], selectable=True))

        flush_pending()
        page.update()

    # ── mode chips ────────────────────────────────────────────────────────────
    def build_mode_chips():
        chips = []
        for m, label, icon, color in MODES:
            active = cur_mode[0] == m
            def on_chip(e, mode=m, lbl=label):
                cur_mode[0] = mode
                mode_label_ref.value = lbl
                file_b_row.visible = (mode == "compare")
                results_scroll.controls = [centered_box([
                    ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=36, color=C["darkest"]),
                    ft.Text(f"Select a file and run {lbl}", size=14, color=C["darker"],
                            italic=True, text_align=ft.TextAlign.CENTER),
                ])]
                rebuild_mode_chips()
                page.update()
            chips.append(ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=14, color=color if active else C["dim"]),
                    ft.Text(label, size=11, color=color if active else C["dim"],
                            weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400),
                ], spacing=6, tight=True),
                bgcolor=C["card"] if active else "transparent",
                border=border_all(1, color if active else C["border"]),
                border_radius=20, padding=ft.Padding(12,6,12,6),
                ink=True, on_click=on_chip,
            ))
        mode_chips_row.controls = chips
        page.update()

    mode_chips_row = ft.Row([], spacing=8, scroll=ft.ScrollMode.AUTO, wrap=False)

    def rebuild_mode_chips():
        chips = []
        for m, label, icon, color in MODES:
            active = cur_mode[0] == m
            def on_chip(e, mode=m, lbl=label):
                cur_mode[0] = mode
                mode_label_ref.value = lbl
                file_b_row.visible = (mode == "compare")
                results_scroll.controls = [centered_box([
                    ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=36, color=C["darkest"]),
                    ft.Text(f"Select a file and run {lbl}", size=14, color=C["darker"],
                            italic=True, text_align=ft.TextAlign.CENTER),
                ])]
                rebuild_mode_chips()
                page.update()
            chips.append(ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=14, color=color if active else C["dim"]),
                    ft.Text(label, size=11, color=color if active else C["dim"],
                            weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400),
                ], spacing=6, tight=True),
                bgcolor=C["card"] if active else "transparent",
                border=border_all(1, color if active else C["border"]),
                border_radius=20, padding=ft.Padding(12,6,12,6),
                ink=True, on_click=on_chip,
            ))
        mode_chips_row.controls = chips

    rebuild_mode_chips()

    # ── file b row (compare mode only) ───────────────────────────────────────
    file_b_row = ft.Container(
        content=ft.Row([
            ft.FilledButton(
                content=ft.Row([ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED,size=15),
                                ft.Text("Select File B",size=12,weight=ft.FontWeight.W_600)],
                               spacing=6,tight=True),
                on_click=lambda e: pick_file_b(),
                style=ft.ButtonStyle(bgcolor=C["yellow"],color=C["bg"],
                                     padding=pad_sym(h=18,v=12),
                                     shape=ft.RoundedRectangleBorder(radius=10)),
            ),
            file_b_lbl,
        ], spacing=12),
        visible=False, padding=pad_only(top=8),
    )

    def pick_file_b():
        def _pick():
            path = pick_file_via_subprocess()
            if path:
                sel_file_b[0] = path
                file_b_lbl.value = f"📄  {fname(path)}"
                file_b_lbl.color = C["yellow"]
                page.update()
        threading.Thread(target=_pick, daemon=True).start()

    # ── file picker ───────────────────────────────────────────────────────────
    def pick_file_clicked(e):
        def _pick():
            set_status("OPENING…", C["dim"])
            path = pick_file_via_subprocess()
            if path:
                sel_file[0] = path
                file_name_lbl.value = f"📄  {fname(path)}"
                file_name_lbl.color = "#60A5FA"
                set_status("FILE LOADED", C["blue"])
                results_scroll.controls = [centered_box([
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED, size=36, color=C["blue"]),
                    ft.Text(f"Loaded: {fname(path)}", size=14, color="#60A5FA",
                            text_align=ft.TextAlign.CENTER),
                    ft.Text('Click "Run Analysis" to start.',
                            size=12, color=C["darker"], text_align=ft.TextAlign.CENTER),
                ], height=300)]
                page.update()
            else:
                set_status("SYSTEM READY", C["green"])
        threading.Thread(target=_pick, daemon=True).start()

    # ── run analysis (streaming) ──────────────────────────────────────────────
    def run_audit(e):
        import engine as eng
        if not sel_file[0]:
            results_scroll.controls = [ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,color=C["yellow"],size=20),
                                ft.Text("Please select a file first.",color=C["yellow"],size=13)],
                               spacing=10), padding=pad_all(16))]
            page.update(); return

        if cur_mode[0] == "compare" and not sel_file_b[0]:
            results_scroll.controls = [ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,color=C["yellow"],size=20),
                                ft.Text("Please select both File A and File B for comparison.",
                                        color=C["yellow"],size=13)], spacing=10),
                padding=pad_all(16))]
            page.update(); return

        if not eng.is_model_available(eng.MODEL):
            results_scroll.controls = [centered_box([
                ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, color=C["yellow"], size=36),
                ft.Text(f'Model "{eng.MODEL}" is not installed.',
                        size=14,color=C["yellow"],text_align=ft.TextAlign.CENTER),
                ft.Text("Run in terminal then try again:",size=12,color=C["dim"],
                        text_align=ft.TextAlign.CENTER),
                ft.Container(
                    content=ft.Text(f"ollama pull {eng.MODEL}",size=13,
                                    color="#60A5FA",selectable=True),
                    bgcolor="#0B1120",padding=pad_sym(h=20,v=10),
                    border_radius=8,border=border_all(1,C["blue_dim"])),
            ], height=340)]
            page.update(); return

        progress_ring.visible = True
        set_status("AI PROCESSING", C["yellow"])
        stream_text = ft.Text("", size=13, color=C["muted"], selectable=True)
        results_scroll.controls = [
            ft.Container(height=12),
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.ProgressRing(width=14,height=14,stroke_width=2,color=mode_color()),
                        ft.Text("Analysing… results appear as they are generated",
                                size=12,color=C["dim"],italic=True)], spacing=10),
                    ft.Text("(Scanned PDFs may take longer — OCR processing first)",
                            size=10, color=C["darker"], italic=True),
                ], spacing=4),
                padding=pad_only(bottom=16)),
            stream_text,
        ]
        page.update()

        mode = cur_mode[0]
        path_a = sel_file[0]
        path_b = sel_file_b[0]

        def _thread():
            full = []
            token_count = [0]

            def safe_update(txt):
                """Called on Flet UI thread — safe to update controls."""
                stream_text.value = txt
                page.update()

            try:
                if mode == "compare":
                    gen = eng.compare_stream(path_a, path_b)
                else:
                    gen = eng.audit_contract_stream(path_a, mode)

                for chunk in gen:
                    full.append(chunk)
                    token_count[0] += 1
                    if token_count[0] % 10 == 0:
                        current = "".join(full)
                        page.run_thread(safe_update, current)

                # Stream done — do ONE final update on UI thread
                complete = "".join(full)

                from datetime import datetime
                display_name = (f"{fname(path_a)} vs {fname(path_b)}"
                                if mode == "compare" else fname(path_a))
                audit_history.append({
                    "filename":  display_name,
                    "mode":      mode,
                    "result":    complete,
                    "timestamp": datetime.now().strftime("%d %b %Y, %H:%M"),
                })

                # Single UI-thread callback that does everything atomically
                def finish(_=None):
                    progress_ring.visible = False
                    status_dot.bgcolor  = C["green"]
                    status_label.value  = "COMPLETE"
                    status_label.color  = C["green"]
                    # Remove streaming indicator, render structured output
                    render_results(complete)

                page.run_thread(finish)

            except Exception as err:
                import traceback
                err_detail = traceback.format_exc()

                def show_err(_=None):
                    progress_ring.visible = False
                    status_dot.bgcolor  = C["red"]
                    status_label.value  = "ERROR"
                    status_label.color  = C["red"]
                    results_scroll.controls = [centered_box([
                        ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED,
                                color=C["red"], size=36),
                        ft.Text(f"Analysis failed:\n{err}",
                                color=C["red"], size=13,
                                text_align=ft.TextAlign.CENTER,
                                selectable=True),
                    ], height=300)]
                    page.update()

                page.run_thread(show_err)

        threading.Thread(target=_thread, daemon=True).start()

    # ── AUDIT VIEW ────────────────────────────────────────────────────────────
    def build_audit_view(reset_results: bool = False):
        # Only reset if explicitly requested (first load or mode change)
        # Returning from Library/Reports MUST preserve the existing results
        if reset_results or not results_scroll.controls:
            results_scroll.controls = [centered_box([
                ft.Icon(ft.Icons.GAVEL_ROUNDED, size=48, color=C["darkest"]),
                ft.Text("Select a document and choose an analysis mode",
                        size=15,color=C["darker"],italic=True,text_align=ft.TextAlign.CENTER),
                ft.Text("Supports PDF · DOCX · TXT",size=11,color=C["dim"],
                        text_align=ft.TextAlign.CENTER),
            ])]

        top_bar = ft.Container(
            content=ft.Row([
                ft.Column([
                    mode_label_ref,
                    ft.Text("Privacy-first AI legal intelligence",size=12,color=C["dim"]),
                ], spacing=2),
                ft.Row([progress_ring,
                        ft.Container(
                            content=ft.Row([status_dot,status_label],spacing=8),
                            bgcolor="#0C1A12",border=border_all(1,C["green_bdr"]),
                            border_radius=20,padding=pad_sym(h=14,v=8))],spacing=12),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=pad_only(bottom=20),
            border=border_bottom(1,C["border2"]),
            margin=ft.Margin(0,0,0,16),
        )

        def clear_results(e):
            sel_file[0]   = None
            sel_file_b[0] = None
            file_name_lbl.value = "No file selected"
            file_name_lbl.color = C["dim"]
            file_b_lbl.value    = "No second file"
            file_b_lbl.color    = C["dim"]
            set_status("SYSTEM READY", C["green"])
            results_scroll.controls = [centered_box([
                ft.Icon(ft.Icons.GAVEL_ROUNDED, size=48, color=C["darkest"]),
                ft.Text("Select a document and choose an analysis mode",
                        size=15, color=C["darker"], italic=True,
                        text_align=ft.TextAlign.CENTER),
                ft.Text("Supports PDF · DOCX · TXT", size=11, color=C["dim"],
                        text_align=ft.TextAlign.CENTER),
            ])]
            page.update()

        action_bar = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.FilledButton(
                        content=ft.Row([ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED,size=16),
                                        ft.Text("Select File",size=13,weight=ft.FontWeight.W_600)],
                                       spacing=8,tight=True),
                        on_click=pick_file_clicked,
                        style=ft.ButtonStyle(bgcolor=C["blue"],color="white",
                            padding=pad_sym(h=22,v=14),shape=ft.RoundedRectangleBorder(radius=10)),
                    ),
                    ft.OutlinedButton(
                        content=ft.Row([ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED,size=16),
                                        ft.Text("Run Analysis",size=13,weight=ft.FontWeight.W_600)],
                                       spacing=8,tight=True),
                        on_click=run_audit,
                        style=ft.ButtonStyle(color=C["muted"],side=ft.BorderSide(1,C["darkest"]),
                            padding=pad_sym(h=22,v=14),shape=ft.RoundedRectangleBorder(radius=10)),
                    ),
                    ft.OutlinedButton(
                        content=ft.Row([ft.Icon(ft.Icons.DELETE_OUTLINE_ROUNDED,size=16),
                                        ft.Text("Clear",size=13,weight=ft.FontWeight.W_600)],
                                       spacing=8,tight=True),
                        on_click=clear_results,
                        style=ft.ButtonStyle(color=C["red"],side=ft.BorderSide(1,C["red"]),
                            padding=pad_sym(h=18,v=14),shape=ft.RoundedRectangleBorder(radius=10)),
                    ),
                    ft.Container(expand=True),
                    file_name_lbl,
                ], spacing=12),
                file_b_row,
            ], spacing=0),
            padding=pad_only(bottom=14),
        )

        mode_bar = ft.Container(
            content=mode_chips_row,
            padding=pad_only(bottom=14),
        )

        legend = ft.Container(
            content=ft.Row([
                ft.Row([ft.Container(width=8,height=8,bgcolor=C["red"],border_radius=4),
                        ft.Text("Risk clause",size=11,color=C["dim"])],spacing=6),
                ft.Row([ft.Container(width=8,height=8,bgcolor=C["blue"],border_radius=4),
                        ft.Text("Standard clause",size=11,color=C["dim"])],spacing=6),
                ft.Row([ft.Container(width=8,height=8,bgcolor="#60A5FA",border_radius=4),
                        ft.Text("Section header",size=11,color=C["dim"])],spacing=6),
                ft.Row([ft.Icon(ft.Icons.LOCATION_ON_ROUNDED,size=12,color="#60A5FA"),
                        ft.Text("Page + Line reference",size=11,color=C["dim"])],spacing=4),
            ], spacing=20),
            padding=pad_only(bottom=10),
        )

        return ft.Container(
            expand=True, padding=pad_all(32),
            content=ft.Column([
                top_bar, action_bar, mode_bar, legend,
                ft.Container(
                    content=results_scroll, expand=True, bgcolor=C["card"],
                    padding=pad_all(24), border_radius=14, border=border_all(1,C["border"])),
            ], expand=True, spacing=0))

    # ── LIBRARY VIEW ──────────────────────────────────────────────────────────
    def build_library_view():
        MODE_ICONS = {m: (icon, color) for m,_,icon,color in MODES}
        if not audit_history:
            body = centered_box([
                ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=48, color=C["darkest"]),
                ft.Text("No audits yet",size=15,color=C["darker"],italic=True),
                ft.Text("Run an analysis — it will appear here.",size=11,color=C["dim"]),
            ])
        else:
            rows = []
            for i, item in enumerate(reversed(audit_history)):
                ic, col = MODE_ICONS.get(item.get("mode","contract"),
                                         (ft.Icons.DESCRIPTION_ROUNDED, C["blue"]))
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Icon(ic, size=18, color=col),
                            width=36, height=36, bgcolor=C["bg"],
                            border_radius=8, alignment=ALIGN_CENTER,
                            border=border_all(1, C["border"])),
                        ft.Column([
                            ft.Text(item["filename"],size=13,color=C["text"],
                                    weight=ft.FontWeight.W_600),
                            ft.Row([
                                ft.Text(item.get("mode","contract").upper(),
                                        size=9,color=col,weight=ft.FontWeight.W_700),
                                ft.Text("·",size=9,color=C["dim"]),
                                ft.Text(item["timestamp"],size=11,color=C["dim"]),
                            ], spacing=6),
                        ], spacing=2, expand=True),
                        ft.TextButton("View",
                            on_click=lambda e, idx=i: view_history(idx),
                            style=ft.ButtonStyle(color=C["blue"])),
                    ], spacing=12),
                    bgcolor=C["card"], padding=pad_all(14), border_radius=10,
                    border=border_all(1,C["border"]), margin=ft.Margin(0,0,0,8)))
            body = ft.Column(rows, scroll=ft.ScrollMode.AUTO, expand=True)

        return ft.Container(
            expand=True, padding=pad_all(36),
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Text("Audit Library",size=26,weight=ft.FontWeight.W_700,color="white"),
                        ft.Text(f"{len(audit_history)} analysis session(s) this run",
                                size=12,color=C["dim"]),
                    ], spacing=2),
                    padding=pad_only(bottom=24), border=border_bottom(1,C["border2"]),
                    margin=ft.Margin(0,0,0,24)),
                body,
            ], expand=True, spacing=0))

    def view_history(idx: int):
        item = list(reversed(audit_history))[idx]
        cur_view[0] = "audit"
        cur_mode[0] = item.get("mode", "contract")
        mode_label_ref.value = next((l for m,l,_,_ in MODES if m==cur_mode[0]), "Audit")
        rebuild_mode_chips()
        content_panel.content = build_audit_view()
        file_name_lbl.value = f"📄  {item['filename']}"
        file_name_lbl.color = "#60A5FA"
        set_status("COMPLETE", C["green"])
        render_results(item["result"])
        refresh_nav()
        page.update()

    # ── REPORTS VIEW ──────────────────────────────────────────────────────────
    def build_reports_view():
        if not audit_history:
            body = centered_box([
                ft.Icon(ft.Icons.BAR_CHART_ROUNDED, size=48, color=C["darkest"]),
                ft.Text("No reports yet",size=15,color=C["darker"],italic=True),
                ft.Text("Complete an analysis to generate a report.",size=11,color=C["dim"]),
            ])
        else:
            # Show selector for all audits, not just latest
            selected_idx = [len(audit_history) - 1]  # default to latest

            def get_report(idx):
                item = audit_history[idx]
                result = item["result"]

                # ── accurate parsing ──────────────────────────────────────
                # Find risk score line properly
                risk_word = "UNKNOWN"
                in_risk_section = False
                for line in result.splitlines():
                    if "OVERALL RISK SCORE" in line.upper():
                        in_risk_section = True
                        after = line.split(":")[-1].strip() if ":" in line else ""
                        if after:
                            risk_word = after.split()[0].upper()
                            break
                        continue
                    if in_risk_section and line.strip():
                        risk_word = line.strip().split()[0].upper()
                        break

                # Count bullets per section accurately
                sections = {}
                cur_section = "other"
                for line in result.splitlines():
                    s = line.strip()
                    if s.endswith(":") and s == s.upper() and len(s) < 70:
                        cur_section = s.rstrip(":")
                    elif s.startswith(("•", "-", "*", "·", "–")):
                        sections[cur_section] = sections.get(cur_section, 0) + 1
                    elif s.startswith("→"):
                        # count suggestions separately
                        sections["__suggestions__"] = \
                            sections.get("__suggestions__", 0) + 1

                total_bullets   = sum(v for k, v in sections.items()
                                      if not k.startswith("__"))
                risk_items      = sections.get("KEY RISK FLAGS", 0)
                liability_items = sections.get("LIABILITY & INDEMNIFICATION", 0)
                termination_items = sections.get("TERMINATION CONDITIONS", 0)
                suggestion_items  = sections.get("__suggestions__", 0)

                risk_color = {
                    "LOW": C["green"], "MEDIUM": C["yellow"],
                    "HIGH": C["orange"], "CRITICAL": C["red"],
                }.get(risk_word, C["dim"])

                return item, risk_word, risk_color, total_bullets, risk_items, \
                       liability_items, termination_items, suggestion_items

            item, risk_word, risk_color, total_bullets, risk_items, \
                liability_items, termination_items, suggestion_items = \
                get_report(selected_idx[0])

            def export_pdf(e):
                try:
                    from reportlab.lib.pagesizes import A4
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                    from reportlab.lib.units import cm
                    from reportlab.lib import colors
                    from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                                    Spacer, HRFlowable, Table, TableStyle)
                    from reportlab.lib.enums import TA_LEFT, TA_CENTER

                    safe_name = item['filename'].replace(' ','_').replace('/','_')[:40]
                    save_path = os.path.expanduser(f"~/Desktop/VerifAI_{safe_name}.pdf")

                    doc = SimpleDocTemplate(save_path, pagesize=A4,
                                            leftMargin=2*cm, rightMargin=2*cm,
                                            topMargin=2*cm, bottomMargin=2*cm)
                    styles = getSampleStyleSheet()

                    # Custom styles
                    title_style  = ParagraphStyle('T', fontSize=18, fontName='Helvetica-Bold',
                                                   spaceAfter=4, textColor=colors.HexColor('#1a1a2e'))
                    sub_style    = ParagraphStyle('S', fontSize=10, fontName='Helvetica',
                                                   spaceAfter=12, textColor=colors.HexColor('#555555'))
                    heading_style= ParagraphStyle('H', fontSize=11, fontName='Helvetica-Bold',
                                                   spaceBefore=14, spaceAfter=4,
                                                   textColor=colors.HexColor('#1a56db'))
                    body_style   = ParagraphStyle('B', fontSize=9, fontName='Helvetica',
                                                   spaceAfter=4, leading=13,
                                                   textColor=colors.HexColor('#333333'))
                    risk_style   = ParagraphStyle('R', fontSize=9, fontName='Helvetica',
                                                   spaceAfter=4, leading=13,
                                                   textColor=colors.HexColor('#dc2626'))
                    tip_style    = ParagraphStyle('TIP', fontSize=9, fontName='Helvetica',
                                                   spaceAfter=4, leading=13,
                                                   textColor=colors.HexColor('#059669'))

                    story = []

                    # Header
                    story.append(Paragraph("VerifAI — Legal Intelligence Report", title_style))
                    story.append(Paragraph(
                        f"Document: {item['filename']}  ·  "
                        f"Mode: {item.get('mode','contract').upper()}  ·  "
                        f"Date: {item['timestamp']}  ·  "
                        f"Risk Score: <b>{risk_word}</b>",
                        sub_style))
                    story.append(HRFlowable(width="100%", thickness=1,
                                            color=colors.HexColor('#e5e7eb')))
                    story.append(Spacer(1, 8))

                    # Summary stats table
                    stat_data = [
                        ['Total Findings', 'Risk Flags', 'Liability', 'Termination', 'Suggestions'],
                        [str(total_bullets), str(risk_items), str(liability_items),
                         str(termination_items), str(suggestion_items)],
                    ]
                    tbl = Table(stat_data, colWidths=[3.2*cm]*5)
                    tbl.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f3f4f6')),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,-1), 8),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white]),
                        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#d1d5db')),
                        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d1d5db')),
                        ('TOPPADDING', (0,0), (-1,-1), 6),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                    ]))
                    story.append(tbl)
                    story.append(Spacer(1, 12))

                    # Full audit content
                    in_recommendations = False
                    for line in item['result'].splitlines():
                        s = line.strip()
                        if not s:
                            story.append(Spacer(1, 3)); continue

                        if s.endswith(":") and s == s.upper() and len(s) < 70:
                            in_recommendations = "RECOMMENDATION" in s
                            story.append(Paragraph(s, heading_style))
                        elif s.startswith(("•","-","*","·","–")):
                            body = s.lstrip("•-*·– ").strip()
                            is_risk = any(k in body.lower() for k in RISK_KW)
                            style = tip_style if in_recommendations else \
                                    (risk_style if is_risk else body_style)
                            bullet = "→" if in_recommendations else ("⚠" if is_risk else "•")
                            story.append(Paragraph(f"{bullet}  {body}", style))
                        else:
                            story.append(Paragraph(s, body_style))

                    story.append(Spacer(1, 16))
                    story.append(HRFlowable(width="100%", thickness=0.5,
                                            color=colors.HexColor('#e5e7eb')))
                    story.append(Paragraph(
                        "Generated by VerifAI — local AI legal intelligence. "
                        "This report is for informational purposes only and does not "
                        "constitute legal advice.", sub_style))

                    doc.build(story)
                    set_status(f"PDF saved to Desktop", C["green"])

                except Exception as err:
                    set_status(f"PDF export failed: {err}", C["red"])

            body = ft.Column([
                # Audit selector (if multiple)
                ft.Container(
                    content=ft.Column([
                        ft.Text("SELECT AUDIT", size=10, weight=ft.FontWeight.W_700,
                                color=C["dim"]),
                        ft.Container(height=6),
                        ft.Column([
                            ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.DESCRIPTION_ROUNDED,
                                            size=14, color=C["blue"]),
                                    ft.Text(f"{h['filename']} · {h.get('mode','contract').upper()} · {h['timestamp']}",
                                            size=11, color=C["text"] if i==selected_idx[0] else C["dim"],
                                            expand=True),
                                    ft.Container(width=8, height=8,
                                                 bgcolor=C["blue"] if i==selected_idx[0] else "transparent",
                                                 border_radius=4),
                                ], spacing=8),
                                bgcolor=C["blue_dim"] if i==selected_idx[0] else "transparent",
                                padding=ft.Padding(10,6,10,6), border_radius=8,
                                ink=True,
                            )
                            for i, h in enumerate(reversed(audit_history))
                        ], spacing=4),
                    ]),
                    bgcolor=C["card"], padding=pad_all(16),
                    border_radius=12, border=border_all(1,C["border"]),
                    margin=ft.Margin(0,0,0,16),
                    visible=len(audit_history) > 1,
                ),

                # ── stats card ─────────────────────────────────────────
                ft.Container(
                    content=ft.Column([
                        ft.Text("AUDIT SUMMARY", size=10,
                                weight=ft.FontWeight.W_700, color=C["dim"]),
                        ft.Container(height=12),
                        ft.Row([
                            _stat_card("Document",
                                       item["filename"][:26]+"…"
                                       if len(item["filename"])>26 else item["filename"],
                                       C["blue"]),
                            _stat_card("Mode", item.get("mode","contract").upper(), C["purple"]),
                            _stat_card("Risk Score", risk_word, risk_color),
                        ], spacing=12),
                        ft.Container(height=10),
                        ft.Row([
                            _stat_card("Total Findings", str(total_bullets), C["teal"]),
                            _stat_card("Risk Flags", str(risk_items), C["red"]),
                            _stat_card("Suggestions", str(suggestion_items), C["green"]),
                        ], spacing=12),
                    ]),
                    bgcolor=C["card"], padding=pad_all(24),
                    border_radius=12, border=border_all(1,C["border"]),
                    margin=ft.Margin(0,0,0,16)),

                # ── export card ────────────────────────────────────────
                ft.Container(
                    content=ft.Column([
                        ft.Text("EXPORT REPORT", size=10, weight=ft.FontWeight.W_700,
                                color=C["dim"]),
                        ft.Container(height=8),
                        ft.Text("Save the full audit as a formatted PDF to your Desktop.",
                                size=12, color=C["muted"]),
                        ft.Container(height=12),
                        ft.FilledButton(
                            content=ft.Row([
                                ft.Icon(ft.Icons.PICTURE_AS_PDF_ROUNDED, size=16),
                                ft.Text("Export as PDF", size=13, weight=ft.FontWeight.W_600),
                            ], spacing=8, tight=True),
                            on_click=export_pdf,
                            style=ft.ButtonStyle(
                                bgcolor=C["red"], color="white",
                                padding=pad_sym(h=20, v=12),
                                shape=ft.RoundedRectangleBorder(radius=10)),
                        ),
                    ]),
                    bgcolor=C["card"], padding=pad_all(24),
                    border_radius=12, border=border_all(1,C["border"])),
            ], scroll=ft.ScrollMode.AUTO, expand=True)

        return ft.Container(
            expand=True, padding=pad_all(36),
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Text("Reports",size=26,weight=ft.FontWeight.W_700,color="white"),
                        ft.Text("Audit summaries and PDF export",size=12,color=C["dim"]),
                    ], spacing=2),
                    padding=pad_only(bottom=24), border=border_bottom(1,C["border2"]),
                    margin=ft.Margin(0,0,0,24)),
                body,
            ], expand=True, spacing=0))

    def _stat_card(label, value, color):
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=9, color=C["dim"], weight=ft.FontWeight.W_700),
                ft.Container(height=4),
                ft.Text(value, size=14, color=color, weight=ft.FontWeight.W_700,
                        selectable=True),
            ], spacing=0),
            bgcolor=C["bg"], padding=pad_all(14), border_radius=10,
            border=border_all(1, C["border"]), expand=True)

    # ── SETTINGS VIEW ─────────────────────────────────────────────────────────
    def _info_row(icon, color, title, subtitle):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=16, color=color),
                ft.Column([
                    ft.Text(title, size=13, color=C["text"], weight=ft.FontWeight.W_600),
                    ft.Text(subtitle, size=11, color=C["dim"]),
                ], spacing=2, expand=True)], spacing=12),
            padding=pad_only(bottom=14))

    def build_settings_view():
        import engine as eng
        all_models  = ["llama3.2:3b","mistral","llama3","gemma3","llama3.1"]
        installed   = eng.get_available_models()
        cur_mdl_txt = ft.Text(eng.MODEL, size=13, color=C["blue"])

        def change_model(e):
            chosen = e.control.value
            if not eng.is_model_available(chosen):
                cur_mdl_txt.value = f"⚠ Not installed — run: ollama pull {chosen}"
                cur_mdl_txt.color = C["yellow"]
            else:
                eng.MODEL = chosen
                cur_mdl_txt.value = chosen
                cur_mdl_txt.color = C["blue"]
            page.update()

        def model_row(m):
            pulled = any(m in av or av in m for av in installed)
            return ft.Container(
                content=ft.Row([
                    ft.Radio(value=m, label=m, fill_color=C["blue"] if pulled else C["dim"],
                             label_style=ft.TextStyle(
                                 color=C["text"] if pulled else C["dim"], size=13)),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text("✓ Installed" if pulled else "Not installed",
                                        size=10, color=C["green"] if pulled else C["dim"]),
                        bgcolor=C["green_bg"] if pulled else C["card"],
                        padding=ft.Padding(8,3,8,3), border_radius=10,
                        border=border_all(1, C["green_bdr"] if pulled else C["border"])),
                ], spacing=0),
                padding=pad_only(bottom=4))

        return ft.Container(
            expand=True, padding=pad_all(36),
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Text("Settings",size=26,weight=ft.FontWeight.W_700,color="white"),
                        ft.Text("Configure VerifAI",size=12,color=C["dim"]),
                    ], spacing=2),
                    padding=pad_only(bottom=24), border=border_bottom(1,C["border2"]),
                    margin=ft.Margin(0,0,0,24)),
                ft.Container(
                    content=ft.Column([
                        ft.Text("AI MODEL",size=10,weight=ft.FontWeight.W_700,color=C["dim"]),
                        ft.Container(height=6),
                        ft.Text("Only installed models work. To add: ollama pull <name>",
                                size=12,color=C["muted"]),
                        ft.Container(height=12),
                        ft.RadioGroup(value=eng.MODEL, on_change=change_model,
                            content=ft.Column([model_row(m) for m in all_models], spacing=2)),
                        ft.Container(height=8),
                        ft.Row([ft.Text("Active: ",size=12,color=C["dim"]), cur_mdl_txt]),
                    ]),
                    bgcolor=C["card"], padding=pad_all(24), border_radius=12,
                    border=border_all(1,C["border"]), margin=ft.Margin(0,0,0,16)),
                ft.Container(
                    content=ft.Column([
                        ft.Text("PRIVACY & SECURITY",size=10,weight=ft.FontWeight.W_700,color=C["dim"]),
                        ft.Container(height=8),
                        _info_row(ft.Icons.LOCK_ROUNDED,C["green"],"100% Local Inference",
                                  "All AI runs on your machine via Ollama."),
                        _info_row(ft.Icons.WIFI_OFF_ROUNDED,C["green"],"No Internet Required",
                                  "Fully offline once models are downloaded."),
                        _info_row(ft.Icons.CLOUD_OFF_ROUNDED,C["green"],"No Cloud Upload",
                                  "Your documents never leave your device."),
                        _info_row(ft.Icons.STORAGE_ROUNDED,C["blue"],"No Persistent Storage",
                                  "History clears when the app closes."),
                    ]),
                    bgcolor=C["card"], padding=pad_all(24), border_radius=12,
                    border=border_all(1,C["border"])),
            ], spacing=0, scroll=ft.ScrollMode.AUTO))

    # ── navigation ────────────────────────────────────────────────────────────
    sidebar_col = ft.Column([], expand=True)

    VIEW_MAP = {
        "audit":    (build_audit_view,    ft.Icons.DOCUMENT_SCANNER_ROUNDED, "Audit"),
        "library":  (build_library_view,  ft.Icons.FOLDER_OPEN_ROUNDED,      "Library"),
        "reports":  (build_reports_view,  ft.Icons.BAR_CHART_ROUNDED,        "Reports"),
        "settings": (build_settings_view, ft.Icons.SETTINGS_ROUNDED,         "Settings"),
    }

    def nav_btn(view_name):
        build_fn, icon, label = VIEW_MAP[view_name]
        active = cur_view[0] == view_name
        def clicked(e):
            cur_view[0] = view_name
            # When returning to audit view, NEVER reset results
            if view_name == "audit":
                content_panel.content = build_audit_view(reset_results=False)
            else:
                content_panel.content = build_fn()
            rebuild_sidebar()
            page.update()
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=18, color=C["blue"] if active else C["dim"]),
                ft.Text(label, size=13, weight=ft.FontWeight.W_500,
                        color=C["text"] if active else C["dim"]),
            ], spacing=12),
            padding=pad_sym(h=16,v=10), border_radius=10,
            bgcolor="#1E293B" if active else "transparent",
            ink=True, on_click=clicked)

    def rebuild_sidebar():
        sidebar_col.controls = [
            ft.Row([
                ft.Container(
                    content=ft.Text("V",size=16,weight=ft.FontWeight.W_900,color="white"),
                    width=32,height=32,bgcolor=C["blue"],border_radius=8,alignment=ALIGN_CENTER),
                ft.Column([
                    ft.Text("VerifAI",size=18,weight=ft.FontWeight.W_700,color="white"),
                    ft.Text("v2.0 · Local",size=10,color=C["darker"]),
                ], spacing=0),
            ], spacing=10),
            ft.Container(height=28),
            ft.Text("TOOLS",size=9,color=C["darker"],weight=ft.FontWeight.W_700),
            ft.Container(height=8),
            nav_btn("audit"),
            nav_btn("library"),
            nav_btn("reports"),
            nav_btn("settings"),
            ft.Container(expand=True),
            ft.Divider(height=1,color=C["border2"]),
            ft.Container(height=14),
            ft.Text("SECURITY",size=9,color=C["darker"],weight=ft.FontWeight.W_700),
            ft.Container(height=8),
            ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.LOCK_ROUNDED,size=13,color=C["green"]),
                                ft.Text("Local Inference",size=11,color=C["green"])],spacing=8),
                bgcolor=C["green_bg"],padding=pad_sym(h=12,v=8),border_radius=8,
                border=border_all(1,C["green_bdr"])),
            ft.Container(height=8),
            ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.WIFI_OFF_ROUNDED,size=13,color=C["dim"]),
                                ft.Text("No Cloud Upload",size=11,color=C["dim"])],spacing=8),
                bgcolor=C["sidebar"],padding=pad_sym(h=12,v=8),border_radius=8,
                border=border_all(1,C["darkest"])),
        ]
        page.update()

    def refresh_nav(): rebuild_sidebar()

    rebuild_sidebar()

    sidebar = ft.Container(
        width=210, bgcolor=C["sidebar"],
        border=border_right(1,C["border2"]),
        padding=pad_sym(h=20,v=28),
        content=sidebar_col)

    content_panel.content = build_audit_view()
    page.add(ft.Row([sidebar, content_panel], expand=True, spacing=0))


if __name__ == "__main__":
    ft.app(target=main)