# -*- coding: utf-8 -*-
"""
HPDFTool Pro  —  PDF 工具箱
-----------------------------------------------------------
依赖:  pip install pymupdf pillow
功能:  原位编辑文字 / 合并 / 拆分 / 水印 / 转图片 / 加密解密

原位编辑原理:
  1. 用 PyMuPDF 提取每一行(或每个片段)文字的精确坐标、字号、颜色、字体风格
  2. 点击页面上的文字 -> 在原位置弹出输入框修改
  3. 保存时只擦除被修改的那一小块文字(背景/图片/矢量图形保留),
     再用相同的位置、字号、颜色写入新文字; 中文自动使用系统中文字体
"""
import os
import re
import sys
import ctypes
import platform
from collections import Counter

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk, simpledialog

import fitz  # PyMuPDF
from PIL import Image, ImageTk

APP_NAME = "HPDFTool Pro"

# ============================================================
#  主题配色
# ============================================================
C = dict(
    bg="#F3F5F9", side="#111827", side_hover="#1F2937", side_active="#2563EB",
    side_text="#9CA3AF", card="#FFFFFF", text="#111827", sub="#6B7280",
    accent="#2563EB", accent_h="#1D4ED8", border="#E5E7EB", canvas="#D5DAE3",
    ok="#16A34A", hover="#2563EB", edited="#16A34A",
)


def pick_ui_font():
    try:
        fams = set(tkfont.families())
    except Exception:
        return "TkDefaultFont"
    for f in ("Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC",
              "WenQuanYi Micro Hei", "Segoe UI", "Helvetica Neue", "Helvetica"):
        if f in fams:
            return f
    return "TkDefaultFont"


FONT = "TkDefaultFont"  # 在 App 初始化时赋值

# ============================================================
#  PDF 文字引擎 (与界面无关)
# ============================================================
CJK_RE = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f\uac00-\ud7af]")

CJK_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc", "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

BASE14 = {  # (常规, 粗体, 斜体, 粗斜体)
    "sans": ("helv", "hebo", "heit", "hebi"),
    "serif": ("tiro", "tibo", "tiit", "tibi"),
    "mono": ("cour", "cobo", "coit", "cobi"),
}


def has_cjk(s):
    return bool(CJK_RE.search(s))


def int_to_rgb(c):
    return (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)


def style_to_base14(fontname, flags):
    n = (fontname or "").lower()
    bold = bool(flags & 16) or any(k in n for k in ("bold", "black", "heavy", "semibold"))
    italic = bool(flags & 2) or any(k in n for k in ("italic", "oblique"))
    mono = bool(flags & 8) or any(k in n for k in ("courier", "mono", "consolas"))
    serif = any(k in n for k in ("times", "serif", "georgia", "garamond", "minion",
                                 "song", "ming", "roman", "palatino")) and "sans" not in n
    fam = "mono" if mono else ("serif" if serif else "sans")
    return BASE14[fam][(1 if bold else 0) + (2 if italic else 0)]


class FontKit:
    """字体缓存 + 中英文混排绘制"""

    def __init__(self):
        self._cache = {}
        self._cjk = None
        self._cjk_tried = False
        self.warnings = set()

    def get(self, name):
        if name not in self._cache:
            self._cache[name] = fitz.Font(name)
        return self._cache[name]

    def cjk(self):
        if not self._cjk_tried:
            self._cjk_tried = True
            for p in CJK_FONT_CANDIDATES:
                if os.path.exists(p):
                    try:
                        self._cjk = fitz.Font(fontfile=p)
                        break
                    except Exception:
                        continue
            if self._cjk is None:
                try:
                    self._cjk = fitz.Font("cjk")
                except Exception:
                    self._cjk = None
        return self._cjk

    def runs(self, text, base, cjk_primary):
        base_f = self.get(base)
        cjk_f = self.cjk() if (has_cjk(text) or cjk_primary) else None
        if has_cjk(text) and cjk_f is None:
            self.warnings.add("未找到系统中文字体，中文可能显示为方块")
        first, second = (cjk_f, base_f) if (cjk_primary and cjk_f) else (base_f, cjk_f)
        out = []
        for ch in text:
            f = first
            if not first.has_glyph(ord(ch)):
                if second is not None and second.has_glyph(ord(ch)):
                    f = second
            if out and out[-1][0] is f:
                out[-1][1].append(ch)
            else:
                out.append((f, [ch]))
        return [(f, "".join(cs)) for f, cs in out]

    def draw(self, page, origin, text, size, color, base="helv", cjk_primary=False,
             max_w=None, opacity=None, morph=None):
        runs = self.runs(text, base, cjk_primary)
        total = sum(f.text_length(t, size) for f, t in runs)
        if max_w and total > max_w and total > 0:
            size = max(size * max_w / total, size * 0.5)
        tw = fitz.TextWriter(page.rect)
        pos = fitz.Point(origin)
        for f, t in runs:
            tw.append(pos, t, font=f, fontsize=size)
            pos = tw.last_point
        kw = dict(color=color)
        if opacity is not None:
            kw["opacity"] = opacity
        if morph is not None:
            kw["morph"] = morph
        tw.write_text(page, **kw)
        return size


def extract_units(page, mode="line"):
    """提取页面上可编辑的文字单元 (按行 / 按片段)"""
    units = []
    if page.rotation != 0:
        return units
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            dx, dy = line.get("dir", (1, 0))
            if abs(dy) > 0.05 or dx < 0:  # 只支持水平文字
                continue
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            if mode == "span":
                groups = [[s] for s in spans]
            else:
                groups = [spans]
            for g in groups:
                text = "".join(s["text"] for s in g)
                main = max(g, key=lambda s: len(s["text"]))
                bbox = fitz.Rect(g[0]["bbox"])
                for s in g[1:]:
                    bbox |= fitz.Rect(s["bbox"])
                units.append(dict(
                    idx=len(units), bbox=tuple(bbox), origin=tuple(g[0]["origin"]),
                    text=text, size=main["size"], color=int_to_rgb(main["color"]),
                    font=main["font"], flags=main["flags"],
                ))
    return units


def sample_bg(img, rect, zoom):
    """取文字框外侧一圈像素的主色，用作覆盖色"""
    W, H = img.size
    x0, y0, x1, y1 = [int(v * zoom) for v in rect]
    pts = []
    for x in range(max(0, x0), min(W - 1, x1), 2):
        for y in (y0 - 2, y1 + 2):
            if 0 <= y < H:
                pts.append(img.getpixel((x, y)))
    for y in range(max(0, y0), min(H - 1, y1), 2):
        for x in (x0 - 2, x1 + 2):
            if 0 <= x < W:
                pts.append(img.getpixel((x, y)))
    if not pts:
        return (1, 1, 1)
    q = Counter((r // 8 * 8, g // 8 * 8, b // 8 * 8) for r, g, b in pts[:400])
    r, g, b = q.most_common(1)[0][0]
    return ((r + 4) / 255.0, (g + 4) / 255.0, (b + 4) / 255.0)


def apply_edits(src_bytes, edits, cover=False, fit_orig=False):
    """在原 PDF 上应用所有修改, 返回 (doc, warnings)"""
    doc = fitz.open("pdf", src_bytes)
    kit = FontKit()
    by_page = {}
    for e in edits:
        by_page.setdefault(e["page"], []).append(e)
    for pno, items in by_page.items():
        page = doc[pno]
        bg_img = None
        if cover:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            bg_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        for e in items:
            r = fitz.Rect(e["bbox"])
            if cover:
                page.add_redact_annot(r, fill=sample_bg(bg_img, r, 2))
            else:
                h = r.height * 0.12
                rr = fitz.Rect(r.x0 + 0.3, r.y0 + h, r.x1 - 0.3, r.y1 - h)
                page.add_redact_annot(rr, fill=False)  # 不填充 -> 背景保持不变
        try:
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0))
        except TypeError:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        for e in items:
            if not e["new"].strip():
                continue
            x0, y0, x1, y1 = e["bbox"]
            limit = page.rect.x1 - 12 - e["origin"][0]
            max_w = min(limit, x1 - x0) if fit_orig else limit
            kit.draw(page, e["origin"], e["new"], e["size"], e["color"],
                     base=style_to_base14(e["font"], e["flags"]),
                     cjk_primary=has_cjk(e["orig"]), max_w=max(max_w, 20))
    return doc, sorted(kit.warnings)


def parse_ranges(s, n):
    pages = []
    for part in re.split(r"[,，\s]+", s.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)?\s*[-~–]\s*(\d+)?", part)
        if m:
            a, b = int(m.group(1) or 1), int(m.group(2) or n)
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(f"无法识别的页码: {part}")
        if a < 1 or b > n or a > b:
            raise ValueError(f"页码超出范围: {part} (文档共 {n} 页)")
        pages.extend(range(a - 1, b))
    if not pages:
        raise ValueError("请输入页码范围，例如 1-3,5,8-")
    return pages


def add_watermark(page, kit, text, size, opacity, angle, color, tile):
    base = "hebo"
    prim = has_cjk(text)
    f_runs = kit.runs(text, base, prim)
    w = sum(f.text_length(t, size) for f, t in f_runs)
    rect = page.rect
    centers = []
    if tile:
        stepx, stepy = w + size * 2.5, size * 5
        y = stepy / 2
        row = 0
        while y < rect.height + stepy:
            x = (stepx / 2) + (stepx / 2 if row % 2 else 0) - stepx
            while x < rect.width + stepx:
                centers.append((x, y))
                x += stepx
            y += stepy
            row += 1
    else:
        centers.append((rect.width / 2, rect.height / 2))
    for cx, cy in centers:
        origin = fitz.Point(cx - w / 2, cy + size * 0.3)
        morph = (fitz.Point(cx, cy), fitz.Matrix(angle))
        kit.draw(page, origin, text, size, color, base=base, cjk_primary=prim,
                 opacity=opacity, morph=morph)


# ============================================================
#  界面辅助
# ============================================================
def make_card(parent, title=None):
    outer = tk.Frame(parent, bg=C["card"], highlightbackground=C["border"], highlightthickness=1)
    if title:
        tk.Label(outer, text=title, bg=C["card"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
    return outer


class App:
    PAD = 24

    def __init__(self, root):
        global FONT
        self.root = root
        FONT = pick_ui_font()
        root.title(f"{APP_NAME} — PDF 工具箱")
        root.geometry("1320x840")
        root.minsize(1100, 700)
        root.configure(bg=C["bg"])

        # ---- 编辑器状态 ----
        self.src_bytes = None
        self.src_path = None
        self.orig_doc = None
        self.view_doc = None
        self.page_no = 0
        self.zoom = 1.3
        self.tk_image = None
        self.edits = {}          # (page, idx) -> edit dict
        self.edit_order = []
        self.units_cache = {}
        self.units = []
        self.entry = None
        self.entry_key = None
        self.hover_id = None
        self.hover_unit = None

        self.mode_var = tk.StringVar(value="line")
        self.cover_var = tk.BooleanVar(value=False)
        self.fit_var = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="就绪")

        self.setup_style()
        self.build_shell()
        self.build_editor()
        self.build_merge()
        self.build_split()
        self.build_watermark()
        self.build_images()
        self.build_security()
        self.show_page("edit")

        root.bind("<Control-o>", lambda e: self.open_pdf())
        root.bind("<Control-s>", lambda e: self.save_pdf())
        root.bind("<Control-z>", lambda e: self.undo_last())

    # ------------------------------------------------------------
    #  样式
    # ------------------------------------------------------------
    def setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", font=(FONT, 10), background=C["bg"], foreground=C["text"])
        s.configure("TFrame", background=C["bg"])
        s.configure("Card.TFrame", background=C["card"])
        s.configure("TLabel", background=C["bg"], foreground=C["text"])
        s.configure("Card.TLabel", background=C["card"])
        s.configure("Sub.TLabel", background=C["card"], foreground=C["sub"], font=(FONT, 9))
        s.configure("TButton", padding=(14, 7), background=C["card"], foreground=C["text"],
                    bordercolor="#D1D5DB", lightcolor=C["card"], darkcolor=C["card"], relief="solid", borderwidth=1)
        s.map("TButton", background=[("active", "#EEF2FF"), ("disabled", "#F3F4F6")],
              foreground=[("disabled", "#9CA3AF")])
        s.configure("Accent.TButton", background=C["accent"], foreground="#FFFFFF",
                    bordercolor=C["accent"], lightcolor=C["accent"], darkcolor=C["accent"],
                    font=(FONT, 10, "bold"))
        s.map("Accent.TButton", background=[("active", C["accent_h"]), ("disabled", "#93C5FD")],
              foreground=[("disabled", "#FFFFFF")])
        s.configure("Tool.TButton", padding=(9, 5))
        s.configure("TEntry", fieldbackground="#FFFFFF", bordercolor=C["border"],
                    lightcolor="#FFFFFF", darkcolor="#FFFFFF", padding=6)
        s.configure("TCombobox", fieldbackground="#FFFFFF", bordercolor=C["border"], padding=5)
        s.configure("TSpinbox", fieldbackground="#FFFFFF", bordercolor=C["border"], padding=5)
        for w in ("TCheckbutton", "TRadiobutton"):
            s.configure(w, background=C["card"])
            s.map(w, background=[("active", C["card"]), ("disabled", C["card"])],
                  foreground=[("disabled", "#9CA3AF")])
        s.configure("Treeview", rowheight=30, background="#FFFFFF", fieldbackground="#FFFFFF",
                    bordercolor=C["border"], borderwidth=0, font=(FONT, 10))
        s.configure("Treeview.Heading", background="#F9FAFB", foreground=C["sub"],
                    font=(FONT, 9, "bold"), relief="flat", padding=6)
        s.map("Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", C["text"])])
        for o in ("Vertical", "Horizontal"):
            s.configure(f"{o}.TScrollbar", background="#C4CAD4", troughcolor=C["bg"],
                        bordercolor=C["bg"], lightcolor="#C4CAD4", darkcolor="#C4CAD4",
                        arrowsize=12, relief="flat")
        s.configure("Horizontal.TProgressbar", background=C["accent"], troughcolor="#E5E7EB",
                    bordercolor="#E5E7EB", lightcolor=C["accent"], darkcolor=C["accent"])
        s.configure("TScale", background=C["card"])
        s.configure("TSeparator", background=C["border"])

    # ------------------------------------------------------------
    #  外壳: 侧边栏 + 内容区 + 状态栏
    # ------------------------------------------------------------
    def build_shell(self):
        bar = tk.Frame(self.root, bg="#FFFFFF", height=28, highlightbackground=C["border"], highlightthickness=1)
        bar.pack(side="bottom", fill="x")
        side = tk.Frame(self.root, bg=C["side"], width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="📄  " + APP_NAME, bg=C["side"], fg="#FFFFFF",
                 font=(FONT, 14, "bold")).pack(anchor="w", padx=20, pady=(24, 2))
        tk.Label(side, text="让 PDF 处理更简单", bg=C["side"], fg=C["side_text"],
                 font=(FONT, 9)).pack(anchor="w", padx=22, pady=(0, 22))

        self.nav = {}
        items = [("edit", "✎   文字编辑"), ("merge", "⊕   合并 PDF"), ("split", "✂   拆分 / 提取"),
                 ("wm", "◈   添加水印"), ("img", "▣   导出图片"), ("sec", "🔒  加密 / 解密")]
        for key, label in items:
            lb = tk.Label(side, text=label, bg=C["side"], fg=C["side_text"], anchor="w",
                          font=(FONT, 11), padx=22, pady=11, cursor="hand2")
            lb.pack(fill="x", padx=10, pady=1)
            lb.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            lb.bind("<Enter>", lambda e, w=lb, k=key: w.config(bg=C["side_hover"]) if self.cur != k else None)
            lb.bind("<Leave>", lambda e, w=lb, k=key: w.config(bg=C["side"]) if self.cur != k else None)
            self.nav[key] = lb
        tk.Label(side, text="Ctrl+O 打开   Ctrl+S 保存\nCtrl+Z 撤销", bg=C["side"], fg="#6B7280",
                 font=(FONT, 8), justify="left").pack(side="bottom", anchor="w", padx=22, pady=18)

        right = tk.Frame(self.root, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)
        tk.Label(bar, textvariable=self.status, bg="#FFFFFF", fg=C["sub"], font=(FONT, 9),
                 anchor="w").pack(side="left", padx=14)
        self.header = tk.Label(right, text="", bg=C["bg"], fg=C["text"], font=(FONT, 17, "bold"), anchor="w")
        self.header.pack(fill="x", padx=26, pady=(20, 4))
        self.container = tk.Frame(right, bg=C["bg"])
        self.container.pack(fill="both", expand=True, padx=26, pady=(4, 16))
        self.pages = {}
        self.cur = None

    def page_frame(self, key):
        f = tk.Frame(self.container, bg=C["bg"])
        f.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.pages[key] = f
        return f

    TITLES = {"edit": "文字编辑", "merge": "合并 PDF", "split": "拆分 / 提取页面",
              "wm": "添加水印", "img": "导出为图片", "sec": "加密 / 解密"}

    def show_page(self, key):
        self.cur = key
        for k, lb in self.nav.items():
            lb.config(bg=C["side_active"] if k == key else C["side"],
                      fg="#FFFFFF" if k == key else C["side_text"])
        self.pages[key].tkraise()
        self.header.config(text=self.TITLES[key])

    def set_status(self, msg):
        self.status.set(msg)
        self.root.update_idletasks()

    def busy(self, on=True):
        self.root.config(cursor="watch" if on else "")
        self.root.update_idletasks()

    def file_row(self, parent, var, cmd, text="选择文件"):
        row = tk.Frame(parent, bg=C["card"])
        row.pack(fill="x", padx=16, pady=(6, 14))
        e = ttk.Entry(row, textvariable=var, state="readonly")
        e.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=text, command=cmd).pack(side="left", padx=(10, 0))

    def pick_pdf(self, var, after=None):
        p = filedialog.askopenfilename(title="选择 PDF", filetypes=[("PDF 文件", "*.pdf")])
        if p:
            var.set(p)
            if after:
                after(p)

    @staticmethod
    def ask_password(doc, path):
        if not doc.needs_pass:
            return True
        pw = simpledialog.askstring("需要密码", f"{os.path.basename(path)} 已加密，请输入密码：", show="*")
        return bool(pw) and bool(doc.authenticate(pw))

    # ============================================================
    #  1. 文字编辑
    # ============================================================
    def build_editor(self):
        page = self.page_frame("edit")

        tb = make_card(page)
        tb.pack(fill="x")
        inner = tk.Frame(tb, bg=C["card"])
        inner.pack(fill="x", padx=12, pady=10)
        ttk.Button(inner, text="📂 打开", style="Accent.TButton", command=self.open_pdf).pack(side="left")
        self.btn_save = ttk.Button(inner, text="💾 保存为…", command=self.save_pdf, state="disabled")
        self.btn_save.pack(side="left", padx=(8, 18))

        self.btn_prev = ttk.Button(inner, text="◀", width=3, style="Tool.TButton", command=lambda: self.goto(self.page_no - 1), state="disabled")
        self.btn_prev.pack(side="left")
        self.page_entry = ttk.Entry(inner, width=4, justify="center")
        self.page_entry.pack(side="left", padx=4)
        self.page_entry.bind("<Return>", lambda e: self.goto(self._page_from_entry()))
        self.page_total = tk.Label(inner, text="/ -", bg=C["card"], fg=C["sub"], font=(FONT, 10))
        self.page_total.pack(side="left")
        self.btn_next = ttk.Button(inner, text="▶", width=3, style="Tool.TButton", command=lambda: self.goto(self.page_no + 1), state="disabled")
        self.btn_next.pack(side="left", padx=(4, 18))

        ttk.Button(inner, text="－", width=3, style="Tool.TButton", command=lambda: self.set_zoom(self.zoom / 1.15)).pack(side="left")
        self.zoom_lbl = tk.Label(inner, text="130%", width=5, bg=C["card"], fg=C["text"], font=(FONT, 10))
        self.zoom_lbl.pack(side="left")
        ttk.Button(inner, text="＋", width=3, style="Tool.TButton", command=lambda: self.set_zoom(self.zoom * 1.15)).pack(side="left")
        ttk.Button(inner, text="适应宽度", style="Tool.TButton", command=self.fit_width).pack(side="left", padx=(8, 0))

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True, pady=(12, 0))

        # ---- 左: 画布 ----
        left = tk.Frame(body, bg=C["canvas"], highlightbackground=C["border"], highlightthickness=1)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, bg=C["canvas"], highlightthickness=0)
        vs = ttk.Scrollbar(left, orient="vertical", command=self.canvas.yview)
        hs = ttk.Scrollbar(left, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Leave>", lambda e: self.set_hover(None))
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.on_wheel(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self.on_wheel(e, -1))
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())
        self.draw_placeholder()

        # ---- 右: 面板 ----
        right = tk.Frame(body, bg=C["bg"], width=320)
        right.pack(side="left", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        guide = make_card(right, "使用方法")
        guide.pack(fill="x")
        tk.Label(guide, bg=C["card"], fg=C["sub"], font=(FONT, 9), justify="left", wraplength=290,
                 text="① 打开 PDF\n② 点击页面上的文字，原位置出现输入框\n③ 修改后按 Enter 确认 (Esc 取消)\n"
                      "④ 点击「保存为…」生成新 PDF\n\n只有被修改的文字会被替换，背景和图片保持不变。"
                 ).pack(anchor="w", padx=16, pady=(2, 12))

        opt = make_card(right, "编辑选项")
        opt.pack(fill="x", pady=(10, 0))
        ttk.Label(opt, text="编辑粒度", style="Sub.TLabel").pack(anchor="w", padx=16)
        r = tk.Frame(opt, bg=C["card"])
        r.pack(anchor="w", padx=12, pady=(2, 4))
        self.rb_line = ttk.Radiobutton(r, text="整行", value="line", variable=self.mode_var, command=self.on_mode_change)
        self.rb_span = ttk.Radiobutton(r, text="文本片段", value="span", variable=self.mode_var, command=self.on_mode_change)
        self.rb_line.pack(side="left", padx=4)
        self.rb_span.pack(side="left", padx=4)
        ttk.Checkbutton(opt, text="超宽时缩小字号以适应原宽度", variable=self.fit_var,
                        command=self.refresh_view).pack(anchor="w", padx=16, pady=2)
        ttk.Checkbutton(opt, text="用背景色覆盖旧文字 (图片上的字用)", variable=self.cover_var,
                        command=self.refresh_view).pack(anchor="w", padx=16, pady=(2, 12))

        lst = make_card(right, "已修改的内容")
        lst.pack(fill="both", expand=True, pady=(10, 0))
        bt = tk.Frame(lst, bg=C["card"])
        bt.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        self.tree = ttk.Treeview(lst, columns=("p", "old", "new"), show="headings", height=4, selectmode="browse")
        self.tree.heading("p", text="页")
        self.tree.heading("old", text="原文")
        self.tree.heading("new", text="修改后")
        self.tree.column("p", width=36, anchor="center", stretch=False)
        self.tree.column("old", width=110)
        self.tree.column("new", width=110)
        self.tree.pack(fill="both", expand=True, padx=12, pady=(4, 6))
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        ttk.Button(bt, text="撤销所选", style="Tool.TButton", command=self.undo_selected).pack(side="left")
        ttk.Button(bt, text="全部撤销", style="Tool.TButton", command=self.undo_all).pack(side="left", padx=6)

    def draw_placeholder(self):
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 600)
        self.canvas.create_text(w / 2, 220, text="📄", font=(FONT, 54), fill="#9AA3B2", tags="ph")
        self.canvas.create_text(w / 2, 300, text="点击左上角「打开」选择 PDF 文件", font=(FONT, 13), fill="#6B7280", tags="ph")
        self.canvas.create_text(w / 2, 328, text="支持文字、中文、多页文档的原位修改", font=(FONT, 10), fill="#9AA3B2", tags="ph")

    # ---------- 打开 / 保存 ----------
    def open_pdf(self):
        p = filedialog.askopenfilename(title="打开 PDF", filetypes=[("PDF 文件", "*.pdf")])
        if not p:
            return
        try:
            doc = fitz.open(p)
            if not self.ask_password(doc, p):
                messagebox.showerror("错误", "密码错误或已取消")
                return
            self.src_bytes = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
            doc.close()
            self.src_path = p
            self.orig_doc = fitz.open("pdf", self.src_bytes)
            self.view_doc = self.orig_doc
            self.edits.clear()
            self.edit_order.clear()
            self.units_cache.clear()
            self.page_no = 0
            self.btn_save.config(state="normal")
            self.update_tree()
            self.update_mode_lock()
            self.fit_width(render=False)
            self.render()
            self.set_status(f"已打开：{os.path.basename(p)}（共 {self.orig_doc.page_count} 页）")
        except Exception as ex:
            messagebox.showerror("错误", f"无法打开 PDF：{ex}")

    def save_pdf(self):
        if not self.orig_doc:
            return
        if not self.edits:
            messagebox.showinfo("提示", "还没有任何修改。\n点击页面上的文字即可开始编辑。")
            return
        base = os.path.splitext(os.path.basename(self.src_path))[0]
        out = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")],
            initialfile=f"{base}_edited.pdf", initialdir=os.path.dirname(self.src_path))
        if not out:
            return
        try:
            self.busy()
            doc, warns = apply_edits(self.src_bytes, list(self.edits.values()),
                                     self.cover_var.get(), self.fit_var.get())
            doc.save(out, garbage=3, deflate=True)
            doc.close()
            self.busy(False)
            msg = f"已保存 {len(self.edits)} 处修改：\n{out}"
            if warns:
                msg += "\n\n提示：" + "；".join(warns)
            messagebox.showinfo("保存成功", msg)
            self.set_status(f"已保存：{out}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("保存失败", str(ex))

    # ---------- 页面渲染 ----------
    def _page_from_entry(self):
        try:
            return int(self.page_entry.get()) - 1
        except ValueError:
            return self.page_no

    def goto(self, n):
        if not self.orig_doc:
            return
        n = max(0, min(n, self.orig_doc.page_count - 1))
        self.cancel_entry()
        self.page_no = n
        self.render()

    def set_zoom(self, z):
        if not self.orig_doc:
            return
        self.zoom = max(0.3, min(z, 4.0))
        self.cancel_entry()
        self.render()

    def fit_width(self, render=True):
        if not self.orig_doc:
            return
        cw = max(self.canvas.winfo_width(), 500)
        pw = self.orig_doc[self.page_no].rect.width
        self.zoom = max(0.3, min((cw - 2 * self.PAD - 20) / pw, 4.0))
        if render:
            self.cancel_entry()
            self.render()

    def get_units(self):
        key = self.page_no
        if key not in self.units_cache:
            self.units_cache[key] = extract_units(self.orig_doc[key], self.mode_var.get())
        return self.units_cache[key]

    def render(self):
        if not self.view_doc:
            return
        page = self.view_doc[self.page_no]
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tk_image = ImageTk.PhotoImage(img)
        P = self.PAD
        self.canvas.delete("all")
        self.canvas.create_rectangle(P + 4, P + 4, P + pix.width + 4, P + pix.height + 4, fill="#B8BFCB", outline="")
        self.canvas.create_image(P, P, anchor="nw", image=self.tk_image)
        self.canvas.config(scrollregion=(0, 0, pix.width + 2 * P, pix.height + 2 * P))
        self.units = self.get_units()
        # 已修改标记
        for u in self.units:
            if (self.page_no, u["idx"]) in self.edits:
                x0, y0, x1, y1 = self.to_canvas(u["bbox"])
                self.canvas.create_rectangle(x0 - 2, y0 - 1, x1 + 2, y1 + 1, outline=C["edited"], width=2, tags="edited")
        self.hover_id = self.canvas.create_rectangle(0, 0, 0, 0, outline=C["hover"], width=2, state="hidden")
        n = self.orig_doc.page_count
        self.page_entry.delete(0, tk.END)
        self.page_entry.insert(0, str(self.page_no + 1))
        self.page_total.config(text=f"/ {n}")
        self.btn_prev.config(state="normal" if self.page_no > 0 else "disabled")
        self.btn_next.config(state="normal" if self.page_no < n - 1 else "disabled")
        self.zoom_lbl.config(text=f"{int(self.zoom * 100)}%")
        if page.rotation != 0:
            self.set_status("该页面带旋转属性，暂不支持文字编辑")
        elif not self.units:
            self.set_status("该页没有可编辑的文字（可能是扫描件 / 图片页）")

    def refresh_view(self):
        """编辑内容或选项变化后，重新生成预览"""
        if not self.orig_doc:
            return
        if self.edits:
            try:
                self.busy()
                self.view_doc, warns = apply_edits(self.src_bytes, list(self.edits.values()),
                                                   self.cover_var.get(), self.fit_var.get())
                if warns:
                    self.set_status("提示：" + "；".join(warns))
            finally:
                self.busy(False)
        else:
            self.view_doc = self.orig_doc
        self.render()

    # ---------- 坐标 / 命中 ----------
    def to_canvas(self, b):
        z, P = self.zoom, self.PAD
        return (P + b[0] * z, P + b[1] * z, P + b[2] * z, P + b[3] * z)

    def unit_at(self, ev):
        x = (self.canvas.canvasx(ev.x) - self.PAD) / self.zoom
        y = (self.canvas.canvasy(ev.y) - self.PAD) / self.zoom
        best, area = None, 1e18
        for u in self.units:
            x0, y0, x1, y1 = u["bbox"]
            if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1:
                a = (x1 - x0) * (y1 - y0)
                if a < area:
                    best, area = u, a
        return best

    def set_hover(self, u):
        if self.hover_id is None:
            return
        self.hover_unit = u
        if u is None or self.entry:
            self.canvas.itemconfigure(self.hover_id, state="hidden")
            self.canvas.config(cursor="")
        else:
            x0, y0, x1, y1 = self.to_canvas(u["bbox"])
            self.canvas.coords(self.hover_id, x0 - 2, y0 - 1, x1 + 2, y1 + 1)
            self.canvas.itemconfigure(self.hover_id, state="normal")
            self.canvas.tag_raise(self.hover_id)
            self.canvas.config(cursor="xterm")

    def on_motion(self, ev):
        if self.orig_doc and self.units:
            self.set_hover(self.unit_at(ev))

    def on_wheel(self, ev, direction=None):
        d = direction if direction is not None else (1 if ev.delta > 0 else -1)
        if ev.state & 0x4:  # Ctrl
            self.set_zoom(self.zoom * (1.1 if d > 0 else 1 / 1.1))
        elif ev.state & 0x1:  # Shift
            self.canvas.xview_scroll(-d * 3, "units")
        else:
            self.canvas.yview_scroll(-d * 3, "units")

    # ---------- 就地编辑 ----------
    def on_click(self, ev):
        if not self.orig_doc:
            return
        u = self.unit_at(ev)
        self.commit_entry()
        if u:
            self.start_edit(u)

    def start_edit(self, u):
        key = (self.page_no, u["idx"])
        cur = self.edits[key]["new"] if key in self.edits else u["text"]
        x0, y0, x1, y1 = self.to_canvas(u["bbox"])
        px = max(10, int(u["size"] * self.zoom))
        fnt = tkfont.Font(family=FONT, size=-px)
        width = max(int(x1 - x0) + 24, 220)
        self.entry = tk.Entry(self.canvas, font=fnt, relief="flat", bg="#FFFBEB", fg="#111827",
                              insertbackground=C["accent"], highlightthickness=2,
                              highlightbackground=C["accent"], highlightcolor=C["accent"])
        self.entry.insert(0, cur)
        self.entry.select_range(0, tk.END)
        self.entry_key = (key, u)
        self.canvas.create_window(x0 - 3, y0 - 3, window=self.entry, anchor="nw", width=width,
                                  height=int(y1 - y0) + 8, tags="entry")
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self.commit_entry())
        self.entry.bind("<Escape>", lambda e: self.cancel_entry())
        self.entry.bind("<FocusOut>", lambda e: self.root.after(60, self.commit_entry))
        self.set_hover(None)
        self.set_status("修改后按 Enter 确认，Esc 取消")

    def cancel_entry(self):
        if self.entry:
            e, self.entry, self.entry_key = self.entry, None, None
            e.destroy()
            self.canvas.delete("entry")

    def commit_entry(self):
        if not self.entry:
            return
        key, u = self.entry_key
        new = self.entry.get()
        self.cancel_entry()
        old_edit = self.edits.get(key)
        prev = old_edit["new"] if old_edit else u["text"]
        if new == prev:
            return
        if new == u["text"]:
            self.edits.pop(key, None)
            if key in self.edit_order:
                self.edit_order.remove(key)
        else:
            self.edits[key] = dict(page=key[0], bbox=u["bbox"], origin=u["origin"], size=u["size"],
                                   color=u["color"], font=u["font"], flags=u["flags"],
                                   orig=u["text"], new=new)
            if key in self.edit_order:
                self.edit_order.remove(key)
            self.edit_order.append(key)
        self.update_tree()
        self.update_mode_lock()
        self.refresh_view()
        self.set_status(f"已修改 {len(self.edits)} 处，完成后点击「保存为…」")

    # ---------- 修改列表 / 撤销 ----------
    def update_tree(self):
        self.tree.delete(*self.tree.get_children())
        for key in self.edit_order:
            e = self.edits[key]
            short = lambda s: (s[:12] + "…") if len(s) > 12 else s
            self.tree.insert("", "end", iid=f"{key[0]}:{key[1]}", values=(key[0] + 1, short(e["orig"]), short(e["new"])))

    def on_tree_select(self, _):
        sel = self.tree.selection()
        if sel:
            p = int(sel[0].split(":")[0])
            if p != self.page_no:
                self.goto(p)

    def undo_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        p, i = map(int, sel[0].split(":"))
        self.edits.pop((p, i), None)
        if (p, i) in self.edit_order:
            self.edit_order.remove((p, i))
        self.after_undo()

    def undo_last(self):
        if self.edit_order and self.cur == "edit" and not self.entry:
            key = self.edit_order.pop()
            self.edits.pop(key, None)
            self.after_undo()

    def undo_all(self):
        if self.edits and messagebox.askyesno("确认", "撤销所有修改？"):
            self.edits.clear()
            self.edit_order.clear()
            self.after_undo()

    def after_undo(self):
        self.update_tree()
        self.update_mode_lock()
        self.refresh_view()

    def on_mode_change(self):
        self.units_cache.clear()
        if self.orig_doc:
            self.render()

    def update_mode_lock(self):
        st = "disabled" if self.edits else "normal"
        self.rb_line.config(state=st)
        self.rb_span.config(state=st)

    # ============================================================
    #  2. 合并
    # ============================================================
    def build_merge(self):
        page = self.page_frame("merge")
        card = make_card(page, "文件列表（按顺序合并）")
        card.pack(fill="both", expand=True)
        tb = tk.Frame(card, bg=C["card"])
        tb.pack(fill="x", padx=14, pady=(6, 8))
        ttk.Button(tb, text="＋ 添加文件", command=self.merge_add).pack(side="left")
        ttk.Button(tb, text="↑ 上移", style="Tool.TButton", command=lambda: self.merge_move(-1)).pack(side="left", padx=(14, 4))
        ttk.Button(tb, text="↓ 下移", style="Tool.TButton", command=lambda: self.merge_move(1)).pack(side="left", padx=4)
        ttk.Button(tb, text="移除", style="Tool.TButton", command=self.merge_remove).pack(side="left", padx=4)
        ttk.Button(tb, text="清空", style="Tool.TButton", command=lambda: self.merge_tree.delete(*self.merge_tree.get_children())).pack(side="left", padx=4)
        ttk.Button(tb, text="开始合并", style="Accent.TButton", command=self.merge_run).pack(side="right")
        self.merge_tree = ttk.Treeview(card, columns=("name", "pages", "path"), show="headings", selectmode="extended")
        self.merge_tree.heading("name", text="文件名")
        self.merge_tree.heading("pages", text="页数")
        self.merge_tree.heading("path", text="路径")
        self.merge_tree.column("name", width=280)
        self.merge_tree.column("pages", width=70, anchor="center", stretch=False)
        self.merge_tree.column("path", width=500)
        self.merge_tree.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def merge_add(self):
        for f in filedialog.askopenfilenames(title="选择 PDF", filetypes=[("PDF 文件", "*.pdf")]):
            try:
                with fitz.open(f) as d:
                    n = "加密" if d.needs_pass else d.page_count
            except Exception:
                n = "?"
            self.merge_tree.insert("", "end", values=(os.path.basename(f), n, f))

    def merge_move(self, d):
        sel = list(self.merge_tree.selection())
        if d > 0:
            sel.reverse()
        for iid in sel:
            self.merge_tree.move(iid, "", self.merge_tree.index(iid) + d)

    def merge_remove(self):
        for iid in self.merge_tree.selection():
            self.merge_tree.delete(iid)

    def merge_run(self):
        files = [self.merge_tree.item(i, "values")[2] for i in self.merge_tree.get_children()]
        if len(files) < 2:
            messagebox.showinfo("提示", "请至少添加两个 PDF 文件")
            return
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")], initialfile="merged.pdf")
        if not out:
            return
        try:
            self.busy()
            res = fitz.open()
            for f in files:
                with fitz.open(f) as src:
                    if not self.ask_password(src, f):
                        raise ValueError(f"无法打开加密文件：{os.path.basename(f)}")
                    res.insert_pdf(src)
            res.save(out, garbage=3, deflate=True)
            res.close()
            self.busy(False)
            self.set_status(f"已合并 {len(files)} 个文件 → {out}")
            messagebox.showinfo("成功", f"已合并 {len(files)} 个文件：\n{out}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("合并失败", str(ex))

    # ============================================================
    #  3. 拆分
    # ============================================================
    def build_split(self):
        page = self.page_frame("split")
        card = make_card(page, "选择文件")
        card.pack(fill="x")
        self.split_var = tk.StringVar()
        self.split_info = tk.StringVar(value="")
        self.file_row(card, self.split_var, lambda: self.pick_pdf(self.split_var, self.split_loaded))
        tk.Label(card, textvariable=self.split_info, bg=C["card"], fg=C["sub"], font=(FONT, 9)).pack(anchor="w", padx=16, pady=(0, 10))

        c2 = make_card(page, "页码设置")
        c2.pack(fill="x", pady=(12, 0))
        tk.Label(c2, text="页码范围（例：1-3,5,8-，留空尾部表示到末页）", bg=C["card"], fg=C["sub"], font=(FONT, 9)).pack(anchor="w", padx=16)
        self.split_range = ttk.Entry(c2)
        self.split_range.pack(fill="x", padx=16, pady=(4, 10))
        self.split_range.insert(0, "1-")
        self.split_mode = tk.StringVar(value="one")
        r = tk.Frame(c2, bg=C["card"])
        r.pack(anchor="w", padx=12, pady=(0, 14))
        ttk.Radiobutton(r, text="提取为一个新文件", value="one", variable=self.split_mode).pack(side="left", padx=4)
        ttk.Radiobutton(r, text="每页单独保存", value="each", variable=self.split_mode).pack(side="left", padx=14)
        ttk.Button(page, text="开始拆分", style="Accent.TButton", command=self.split_run).pack(anchor="e", pady=14)

    def split_loaded(self, p):
        try:
            with fitz.open(p) as d:
                self.split_info.set(f"共 {d.page_count} 页" if not d.needs_pass else "文件已加密，请先到「加密/解密」页解锁")
        except Exception as ex:
            self.split_info.set(str(ex))

    def split_run(self):
        f = self.split_var.get()
        if not f:
            messagebox.showinfo("提示", "请先选择 PDF 文件")
            return
        try:
            src = fitz.open(f)
            pages = parse_ranges(self.split_range.get(), src.page_count)
            base = os.path.splitext(os.path.basename(f))[0]
            self.busy()
            if self.split_mode.get() == "one":
                self.busy(False)
                out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")], initialfile=f"{base}_extract.pdf")
                if not out:
                    return
                self.busy()
                src.select(pages)
                src.save(out, garbage=3, deflate=True)
                msg = out
            else:
                self.busy(False)
                folder = filedialog.askdirectory(title="选择输出文件夹")
                if not folder:
                    return
                self.busy()
                for p in pages:
                    d = fitz.open()
                    d.insert_pdf(src, from_page=p, to_page=p)
                    d.save(os.path.join(folder, f"{base}_page{p + 1}.pdf"))
                    d.close()
                msg = f"{folder}（{len(pages)} 个文件）"
            src.close()
            self.busy(False)
            self.set_status("拆分完成")
            messagebox.showinfo("成功", f"拆分完成：\n{msg}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("拆分失败", str(ex))

    # ============================================================
    #  4. 水印
    # ============================================================
    def build_watermark(self):
        page = self.page_frame("wm")
        card = make_card(page, "选择文件")
        card.pack(fill="x")
        self.wm_var = tk.StringVar()
        self.file_row(card, self.wm_var, lambda: self.pick_pdf(self.wm_var))

        c2 = make_card(page, "水印设置")
        c2.pack(fill="x", pady=(12, 0))
        g = tk.Frame(c2, bg=C["card"])
        g.pack(fill="x", padx=16, pady=(6, 14))
        g.columnconfigure(1, weight=1)
        lab = lambda t, r: tk.Label(g, text=t, bg=C["card"], fg=C["sub"], font=(FONT, 10)).grid(row=r, column=0, sticky="w", pady=7, padx=(0, 16))
        lab("水印文字", 0)
        self.wm_text = ttk.Entry(g)
        self.wm_text.grid(row=0, column=1, sticky="ew")
        self.wm_text.insert(0, "CONFIDENTIAL 机密")
        lab("字号", 1)
        self.wm_size = tk.IntVar(value=48)
        ttk.Spinbox(g, from_=10, to=200, textvariable=self.wm_size, width=8).grid(row=1, column=1, sticky="w")
        lab("旋转角度", 2)
        self.wm_angle = tk.IntVar(value=45)
        ttk.Spinbox(g, from_=0, to=90, textvariable=self.wm_angle, width=8).grid(row=2, column=1, sticky="w")
        lab("透明度", 3)
        self.wm_op = tk.DoubleVar(value=0.25)
        ttk.Scale(g, from_=0.05, to=1.0, variable=self.wm_op).grid(row=3, column=1, sticky="ew", pady=7)
        lab("颜色", 4)
        self.wm_color = tk.StringVar(value="灰色")
        ttk.Combobox(g, textvariable=self.wm_color, values=["灰色", "红色", "蓝色", "黑色"], state="readonly", width=10).grid(row=4, column=1, sticky="w")
        self.wm_tile = tk.BooleanVar(value=False)
        ttk.Checkbutton(g, text="平铺整页", variable=self.wm_tile).grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Button(page, text="添加水印并保存", style="Accent.TButton", command=self.wm_run).pack(anchor="e", pady=14)

    def wm_run(self):
        f, text = self.wm_var.get(), self.wm_text.get().strip()
        if not f or not text:
            messagebox.showinfo("提示", "请选择文件并输入水印文字")
            return
        base = os.path.splitext(os.path.basename(f))[0]
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")], initialfile=f"{base}_watermark.pdf")
        if not out:
            return
        colors = {"灰色": (0.45, 0.45, 0.45), "红色": (0.85, 0.1, 0.1), "蓝色": (0.1, 0.3, 0.85), "黑色": (0, 0, 0)}
        try:
            self.busy()
            doc = fitz.open(f)
            if not self.ask_password(doc, f):
                raise ValueError("无法打开加密文件")
            kit = FontKit()
            for pg in doc:
                add_watermark(pg, kit, text, self.wm_size.get(), float(self.wm_op.get()),
                              self.wm_angle.get(), colors[self.wm_color.get()], self.wm_tile.get())
            doc.save(out, garbage=3, deflate=True)
            doc.close()
            self.busy(False)
            self.set_status(f"水印已添加 → {out}")
            messagebox.showinfo("成功", f"水印已添加：\n{out}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("失败", str(ex))

    # ============================================================
    #  5. 导出图片
    # ============================================================
    def build_images(self):
        page = self.page_frame("img")
        card = make_card(page, "选择文件")
        card.pack(fill="x")
        self.img_var = tk.StringVar()
        self.file_row(card, self.img_var, lambda: self.pick_pdf(self.img_var))
        c2 = make_card(page, "导出设置")
        c2.pack(fill="x", pady=(12, 0))
        g = tk.Frame(c2, bg=C["card"])
        g.pack(fill="x", padx=16, pady=(6, 14))
        tk.Label(g, text="清晰度 (DPI)", bg=C["card"], fg=C["sub"]).grid(row=0, column=0, sticky="w", pady=6, padx=(0, 16))
        self.img_dpi = tk.StringVar(value="200")
        ttk.Combobox(g, textvariable=self.img_dpi, values=["72", "150", "200", "300", "400"], width=8, state="readonly").grid(row=0, column=1, sticky="w")
        tk.Label(g, text="格式", bg=C["card"], fg=C["sub"]).grid(row=1, column=0, sticky="w", pady=6)
        self.img_fmt = tk.StringVar(value="PNG")
        ttk.Combobox(g, textvariable=self.img_fmt, values=["PNG", "JPG"], width=8, state="readonly").grid(row=1, column=1, sticky="w")
        self.img_prog = ttk.Progressbar(page, mode="determinate")
        self.img_prog.pack(fill="x", pady=(16, 0))
        ttk.Button(page, text="导出所有页面", style="Accent.TButton", command=self.img_run).pack(anchor="e", pady=14)

    def img_run(self):
        f = self.img_var.get()
        if not f:
            messagebox.showinfo("提示", "请先选择 PDF 文件")
            return
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if not folder:
            return
        try:
            doc = fitz.open(f)
            if not self.ask_password(doc, f):
                raise ValueError("无法打开加密文件")
            base = os.path.splitext(os.path.basename(f))[0]
            z = int(self.img_dpi.get()) / 72.0
            ext = "png" if self.img_fmt.get() == "PNG" else "jpg"
            self.img_prog.config(maximum=doc.page_count, value=0)
            self.busy()
            for i, pg in enumerate(doc):
                pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False).save(os.path.join(folder, f"{base}_page{i + 1}.{ext}"))
                self.img_prog.config(value=i + 1)
                self.set_status(f"导出中 {i + 1}/{doc.page_count}")
            n = doc.page_count
            doc.close()
            self.busy(False)
            self.set_status("导出完成")
            messagebox.showinfo("成功", f"已导出 {n} 张图片：\n{folder}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("导出失败", str(ex))

    # ============================================================
    #  6. 加密 / 解密
    # ============================================================
    def build_security(self):
        page = self.page_frame("sec")
        card = make_card(page, "选择文件")
        card.pack(fill="x")
        self.sec_var = tk.StringVar()
        self.file_row(card, self.sec_var, lambda: self.pick_pdf(self.sec_var))
        c2 = make_card(page, "密码")
        c2.pack(fill="x", pady=(12, 0))
        self.pwd = ttk.Entry(c2, show="●")
        self.pwd.pack(fill="x", padx=16, pady=(6, 4))
        tk.Label(c2, text="加密使用 AES-256；解密需要输入当前密码。", bg=C["card"], fg=C["sub"], font=(FONT, 9)).pack(anchor="w", padx=16, pady=(0, 14))
        r = tk.Frame(page, bg=C["bg"])
        r.pack(anchor="e", pady=14)
        ttk.Button(r, text="🔓 解除密码", command=self.sec_unlock).pack(side="left", padx=8)
        ttk.Button(r, text="🔒 加密", style="Accent.TButton", command=self.sec_lock).pack(side="left")

    def sec_lock(self):
        f, pw = self.sec_var.get(), self.pwd.get()
        if not f or not pw:
            messagebox.showinfo("提示", "请选择文件并输入密码")
            return
        base = os.path.splitext(os.path.basename(f))[0]
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")], initialfile=f"{base}_locked.pdf")
        if not out:
            return
        try:
            doc = fitz.open(f)
            if not self.ask_password(doc, f):
                raise ValueError("无法打开该文件")
            doc.save(out, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=pw, owner_pw=pw, garbage=3, deflate=True)
            doc.close()
            self.set_status(f"已加密 → {out}")
            messagebox.showinfo("成功", f"已加密：\n{out}")
        except Exception as ex:
            messagebox.showerror("失败", str(ex))

    def sec_unlock(self):
        f, pw = self.sec_var.get(), self.pwd.get()
        if not f:
            messagebox.showinfo("提示", "请先选择 PDF 文件")
            return
        base = os.path.splitext(os.path.basename(f))[0]
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")], initialfile=f"{base}_unlocked.pdf")
        if not out:
            return
        try:
            doc = fitz.open(f)
            if doc.needs_pass and not doc.authenticate(pw):
                raise ValueError("密码错误")
            doc.save(out, encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
            doc.close()
            self.set_status(f"已解除密码 → {out}")
            messagebox.showinfo("成功", f"已解除密码：\n{out}")
        except Exception as ex:
            messagebox.showerror("失败", str(ex))


def main():
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 高分屏清晰显示
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
