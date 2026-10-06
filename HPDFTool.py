# -*- coding: utf-8 -*-
# Copyright (c) 2026 HIUWAHWONG. All rights reserved.
# Licensed under the MIT License.
"""
HPDFTool Pro - PDF Toolkit
-----------------------------------------------------------
Dependencies: pip install pymupdf pillow
Features: in-place text editing / merge / split / watermark preview / pages to images / encryption

In-place editing:
  1. Extract text coordinates, sizes, colors, and font styles with PyMuPDF.
  2. Click page text to edit it at its original position.
  3. Remove only edited text when saving; preserve images and vector graphics.
     Draw replacement text with matching styling and automatic CJK font fallback.     
"""
import os
import re
import sys
import difflib
import unicodedata
import ctypes
import platform
from collections import Counter

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk, simpledialog

try:
    import pymupdf as fitz  # Current PyMuPDF package name
except ImportError:  # Legacy package name
    import fitz
from PIL import Image, ImageTk, ImageDraw

APP_NAME = "HPDFTool Pro"

# ============================================================
#  Theme colors
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
    preferred = {"Windows": ("Segoe UI", "Arial"),
                 "Darwin": ("SF Pro Text", "Helvetica Neue", "Arial")}.get(platform.system(), ())
    for f in preferred + ("Noto Sans", "DejaVu Sans", "Liberation Sans", "Helvetica",
                           "Segoe UI", "Microsoft YaHei UI", "Noto Sans CJK SC"):
        if f in fams:
            return f
    return tkfont.nametofont("TkDefaultFont").actual("family")


FONT = "TkDefaultFont"  # Set during App initialization
UI_SCALE = 1.0


def ui_px(value):
    """Scale layout dimensions with system DPI; font sizes use Tk points."""
    return max(1, round(value * UI_SCALE))


def ui_fonts():
    return dict(body=(FONT, 10), caption=(FONT, 9), section=(FONT, 11, "bold"),
                title=(FONT, 18, "bold"), nav=(FONT, 10), brand=(FONT, 13, "bold"))


UI = ui_fonts()

# ============================================================
#  PDF text engine (independent of the UI)
# ============================================================
CJK_RE = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f\uac00-\ud7af]")
OPEN_P = set("（［｛《〈「『【〔“‘")
CLOSE_P = set("，。、！？；：）］｝》〉」』】〕”’…％")

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

BASE14 = {  # (regular, bold, italic, bold italic)
    "sans": ("helv", "hebo", "heit", "hebi"),
    "serif": ("tiro", "tibo", "tiit", "tibi"),
    "mono": ("cour", "cobo", "coit", "cobi"),
}

# Common font names -> lowercase system font stems: regular, bold, italic, bold italic
_LIB = lambda n: tuple(f"liberation{n}-{v}" for v in ("regular", "bold", "italic", "bolditalic"))
_MAC = lambda n: (n, n + " bold", n + " italic", n + " bold italic")
FONT_ALIASES = {
    "arialnarrow": [("arialn", "arialnb", "arialni", "arialnbi")],
    "arialblack": [("ariblk",) * 4],
    "arial": [("arial", "arialbd", "ariali", "arialbi"), _MAC("arial"), _LIB("sans")],
    "helvetica": [_MAC("helvetica"), _LIB("sans")],
    "timesnewroman": [("times", "timesbd", "timesi", "timesbi"), _MAC("times new roman"), _LIB("serif")],
    "times": [("times", "timesbd", "timesi", "timesbi"), _LIB("serif")],
    "couriernew": [("cour", "courbd", "couri", "courbi"), _MAC("courier new"), _LIB("mono")],
    "calibri": [("calibri", "calibrib", "calibrii", "calibriz")],
    "cambria": [("cambria", "cambriab", "cambriai", "cambriaz")],
    "verdana": [("verdana", "verdanab", "verdanai", "verdanaz")],
    "tahoma": [("tahoma", "tahomabd", "tahoma", "tahomabd")],
    "segoeui": [("segoeui", "segoeuib", "segoeuii", "segoeuiz")],
    "georgia": [("georgia", "georgiab", "georgiai", "georgiaz")],
    "consolas": [("consola", "consolab", "consolai", "consolaz")],
    "trebuchetms": [("trebuc", "trebucbd", "trebucit", "trebucbi")],
    "microsoftyahei": [("msyh", "msyhbd", "msyh", "msyhbd")],
    "simsun": [("simsun", "simsunb", "simsun", "simsunb")],
    "nsimsun": [("simsun", "simsunb", "simsun", "simsunb")],
    "simhei": [("simhei",) * 4],
    "kaiti": [("simkai",) * 4],
    "simkai": [("simkai",) * 4],
    "fangsong": [("simfang",) * 4],
    "simfang": [("simfang",) * 4],
    "dengxian": [("deng", "dengb", "deng", "dengb")],
    "pingfang": [("pingfang",) * 4],
    "songti": [("songti",) * 4],
    "stheiti": [("stheiti light", "stheiti medium", "stheiti light", "stheiti medium")],
}


def has_cjk(s):
    return bool(CJK_RE.search(s))


def int_to_rgb(c):
    return (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)


def norm_raw(name):
    name = re.sub(r"^[A-Za-z]{6}\+", "", name or "")
    return re.sub(r"[^a-z0-9]", "", name.lower())


def style_flags(name, flags):
    n = (name or "").lower()
    bold = bool(flags & 16) or any(k in n for k in ("bold", "black", "heavy", "semibold", "-bd"))
    italic = bool(flags & 2) or any(k in n for k in ("italic", "oblique"))
    return bold, italic


def style_to_base14(fontname, flags):
    n = (fontname or "").lower()
    bold, italic = style_flags(fontname, flags)
    mono = bool(flags & 8) or any(k in n for k in ("courier", "mono", "consolas"))
    serif = any(k in n for k in ("times", "serif", "georgia", "garamond", "minion",
                                 "song", "ming", "roman", "palatino")) and "sans" not in n
    fam = "mono" if mono else ("serif" if serif else "sans")
    return BASE14[fam][(1 if bold else 0) + (2 if italic else 0)]


_SYS_INDEX = None
_SYS_CACHE = {}
_EMB_CACHE = {}


def system_font_index():
    """Index system fonts by lowercase filename stem."""
    global _SYS_INDEX
    if _SYS_INDEX is not None:
        return _SYS_INDEX
    dirs = []
    sysname = platform.system()
    if sysname == "Windows":
        dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Windows\Fonts")]
    elif sysname == "Darwin":
        dirs = ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    else:
        dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                os.path.expanduser("~/.local/share/fonts")]
    idx = {}
    for d in dirs:
        if d and os.path.isdir(d):
            for root_, _, files in os.walk(d):
                for f in files:
                    stem, ext = os.path.splitext(f)
                    if ext.lower() in (".ttf", ".ttc", ".otf"):
                        idx.setdefault(stem.lower(), os.path.join(root_, f))
    _SYS_INDEX = idx
    return idx


def system_font_for(style):
    """Find a system font matching the original font name."""
    fam = norm_raw(style["font"])
    for suf in ("bolditalic", "boldoblique", "semibold", "bold", "italic", "oblique", "regular"):
        fam = fam.replace(suf, "")
    for suf in ("psmt", "mt", "ps"):
        if fam.endswith(suf):
            fam = fam[: -len(suf)]
    bold, italic = style_flags(style["font"], style["flags"])
    ck = (fam, bold, italic)
    if ck in _SYS_CACHE:
        return _SYS_CACHE[ck]
    idx = system_font_index()
    found = None
    for key in sorted(FONT_ALIASES, key=len, reverse=True):
        if fam.startswith(key):
            for stems in FONT_ALIASES[key]:
                stem = stems[(1 if bold else 0) + (2 if italic else 0)]
                if stem in idx:
                    try:
                        found = fitz.Font(fontfile=idx[stem])
                    except Exception:
                        found = None
                    if found:
                        break
            break
    if found is None:  # Fuzzy match the family name after removing style suffixes; preserve weight and slant.
        base = _core_name(fam)
        for core, sb, si, path in _fuzzy_index():
            if core == base and sb == bold and si == italic:
                try:
                    found = fitz.Font(fontfile=path)
                except Exception:
                    found = None
                if found:
                    break
    _SYS_CACHE[ck] = found
    return found


_FUZZY = None


def _core_name(n):
    for w in ("bolditalic", "boldoblique", "semibold", "bold", "italic", "oblique", "regular", "book", "medium"):
        n = n.replace(w, "")
    return n


def _fuzzy_index():
    global _FUZZY
    if _FUZZY is None:
        _FUZZY = []
        for stem, path in system_font_index().items():
            n = re.sub(r"[^a-z0-9]", "", stem)
            sb = "bold" in n or n.endswith("bd")
            si = "italic" in n or "oblique" in n
            _FUZZY.append((_core_name(n[:-2] if n.endswith("bd") else n), sb, si, path))
    return _FUZZY


class FontKit:
    """Font cache and mixed Latin/CJK drawing for watermarks and other simple text."""

    def __init__(self):
        self._cache = {}
        self._cjk = None
        self._cjk_tried = False
        self._stamp_doc = None
        self._stamp_key = None

    def close(self):
        if self._stamp_doc is not None:
            self._stamp_doc.close()
            self._stamp_doc = None
            self._stamp_key = None

    def watermark_stamp(self, text, size, opacity, color):
        """Build upright text; rotate the PDF Form rather than applying TextWriter morph."""
        key = (text, size, opacity, tuple(color))
        if key != self._stamp_key:
            self.close()
            runs = self.runs(text, "hebo", has_cjk(text))
            width = sum(f.text_length(t, size) for f, t in runs)
            ascent = max(f.ascender for f, _ in runs) * size
            descent = min(f.descender for f, _ in runs) * size
            pad = max(2, size * 0.08)
            doc = fitz.open()
            try:
                pg = doc.new_page(width=width + pad * 2, height=ascent - descent + pad * 2)
                self.draw(pg, (pad, pad + ascent), text, size, color,
                          base="hebo", cjk_primary=has_cjk(text), opacity=opacity)
            except Exception:
                doc.close()
                raise
            self._stamp_doc, self._stamp_key = doc, key
        return self._stamp_doc

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
        first, second = (cjk_f, base_f) if (cjk_primary and cjk_f) else (base_f, cjk_f)
        out = []
        for ch in text:
            f = first
            if not first.has_glyph(ord(ch)) and second is not None and second.has_glyph(ord(ch)):
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


class FontResolver:
    """Resolve each style: embedded font -> matching system font -> user fallback -> standard/CJK font."""

    def __init__(self, doc, cache_key, user_font=None):
        self.doc = doc
        self.ck = cache_key
        self.kit = FontKit()
        self.user = None
        if user_font and os.path.exists(user_font):
            try:
                self.user = fitz.Font(fontfile=user_font)
            except Exception:
                self.user = None
        self._pf = {}

    def embedded(self, page, name):
        """Return every embedded subset of the requested font on this page."""
        if page.number not in self._pf:
            self._pf[page.number] = page.get_fonts(full=True)
        target = norm_raw(name)
        found = []
        for f in self._pf[page.number]:
            if norm_raw(f[3]) != target:
                continue
            key = (self.ck, f[0])
            if key not in _EMB_CACHE:
                font = None
                try:
                    content = self.doc.extract_font(f[0])[3]
                    if content:
                        font = fitz.Font(fontbuffer=content)
                except Exception:
                    font = None
                _EMB_CACHE[key] = font
            if _EMB_CACHE[key] is not None:
                found.append(_EMB_CACHE[key])
        return found

    def chain(self, page, style, orig_chars):
        chain = []
        embs = self.embedded(page, style["font"])
        probe = {c for c in orig_chars if not c.isspace()}
        # Use an embedded font only when its character map covers all original characters.
        covers = [(sum(1 for c in probe if f.has_glyph(ord(c))), f) for f in embs]
        if probe and all(any(f.has_glyph(ord(c)) for f in embs) for c in probe):
            for n, f in sorted(covers, key=lambda x: -x[0]):
                if n:
                    chain.append((f, "orig"))
        same = system_font_for(style)
        if same is not None:
            chain.append((same, "orig"))
        if self.user is not None:
            chain.append((self.user, "alt"))
        base = self.kit.get(style_to_base14(style["font"], style["flags"]))
        cjk = self.kit.cjk()
        if has_cjk(orig_chars) and cjk is not None:
            chain += [(cjk, "alt"), (base, "alt")]
        else:
            chain.append((base, "alt"))
            if cjk is not None:
                chain.append((cjk, "alt"))
        return chain


# ---------- Text unit extraction ----------
def _norm_char(ch):
    """Normalize CJK compatibility ideographs (U+F900-FAFF) for find and replace."""
    if "\uf900" <= ch <= "\ufaff":
        n = unicodedata.normalize("NFC", ch)
        if len(n) == 1:
            return n
    return ch


def _build_unit(idx, mode, lines):
    styles, skey, toks, rects, origins = [], {}, [], [], []
    for li, spans in enumerate(lines):
        r = fitz.Rect(spans[0]["bbox"])
        for s in spans:
            key = (s["font"], s["flags"], round(s["size"], 2), s["color"])
            if key not in skey:
                skey[key] = len(styles)
                styles.append(dict(font=s["font"], flags=s["flags"], size=s["size"], color=int_to_rgb(s["color"])))
            sid = skey[key]
            toks.extend((_norm_char(ch), sid) for ch in s["text"])
            r |= fitz.Rect(s["bbox"])
        rects.append(tuple(r))
        origins.append(tuple(spans[0]["origin"]))
        if li < len(lines) - 1 and toks:
            last = toks[-1]
            nxt = lines[li + 1][0]["text"][:1]
            if not last[0].isspace() and not (has_cjk(last[0]) or has_cjk(nxt)):
                toks.append((" ", last[1]))
    text = "".join(c for c, _ in toks)
    if not text.strip():
        return None
    cnt = Counter(sid for _, sid in toks)
    main = styles[cnt.most_common(1)[0][0]]
    bbox = fitz.Rect(rects[0])
    for r in rects[1:]:
        bbox |= fitz.Rect(r)
    n = len(lines)
    pitch = (origins[-1][1] - origins[0][1]) / (n - 1) if n > 1 else main["size"] * 1.2
    return dict(idx=idx, mode=mode, bbox=tuple(bbox), rects=rects, tokens=toks, styles=styles,
                text=text, size=main["size"], x_first=origins[0][0], y_first=origins[0][1],
                x_rest=min(o[0] for o in origins[1:]) if n > 1 else origins[0][0],
                pitch=pitch, right=max(r[2] for r in rects), n_lines=n)


def extract_units(page, mode="line"):
    """Modes: line (split at large horizontal gaps), span, or paragraph."""
    units = []
    if page.rotation != 0:
        return units
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        good = []
        for line in block.get("lines", []):
            dx, dy = line.get("dir", (1, 0))
            spans = [s for s in line.get("spans", []) if s.get("text", "")]
            if abs(dy) > 0.05 or dx < 0 or not spans:
                good.append(None)
            else:
                good.append(spans)
        if mode == "para":
            if good and all(g is not None for g in good):
                u = _build_unit(len(units), mode, good)
                if u:
                    units.append(u)
            continue
        for spans in good:
            if spans is None:
                continue
            if mode == "span":
                groups = [[s] for s in spans if s["text"].strip()]
            else:  # Split at large tab/column gaps to keep distant text segments separate.
                groups, cur = [], [spans[0]]
                for prev, s in zip(spans, spans[1:]):
                    gap = s["bbox"][0] - prev["bbox"][2]
                    if gap > 0.7 * max(prev["size"], s["size"]):
                        groups.append(cur)
                        cur = [s]
                    else:
                        cur.append(s)
                groups.append(cur)
            for g in groups:
                u = _build_unit(len(units), mode, [g])
                if u:
                    units.append(u)
    return units


# ---------- Replacement text layout ----------
def diff_tokens(old_tokens, new_text):
    """Map original styles by character diff; inserted text inherits neighboring styles."""
    old = "".join(c for c, _ in old_tokens)
    if not old_tokens:
        return [(c, 0) for c in new_text]
    out = []
    sm = difflib.SequenceMatcher(None, old, new_text, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out += [(new_text[j1 + k], old_tokens[i1 + k][1]) for k in range(i2 - i1)]
        elif tag in ("replace", "insert"):
            if tag == "replace" and i1 < len(old_tokens):
                sid = old_tokens[i1][1]
            else:
                sid = old_tokens[max(i1 - 1, 0)][1]
            out += [(c, sid) for c in new_text[j1:j2]]
    return out


def can_break(prev, cur):
    if prev == " ":
        return cur != " "
    if cur in CLOSE_P or prev in OPEN_P:
        return False
    return has_cjk(prev) or has_cjk(cur)


def layout_tokens(toks, wrap, first_limit, rest_limit, width_of):
    lines, cur_w, limit = [[]], 0.0, first_limit
    for t in toks:
        ch = t[0]
        if ch == "\n":
            lines.append([])
            cur_w, limit = 0.0, rest_limit
            continue
        w = width_of(t)
        line = lines[-1]
        if wrap and line and ch != " " and cur_w + w > limit + 0.01:
            cand = line + [t]
            brk = None
            for k in range(len(cand) - 1, 0, -1):
                if can_break(cand[k - 1][0], cand[k][0]):
                    brk = k
                    break
            if brk is None:
                brk = len(line)
            lines[-1] = cand[:brk]
            new_line = cand[brk:]
            lines.append(new_line)
            limit = rest_limit
            cur_w = sum(width_of(x) for x in new_line)
            continue
        line.append(t)
        cur_w += w
    return lines


def plan_edit(page, e, resolver, fit, warnings):
    u, new = e["unit"], e["new"]
    toks = diff_tokens(u["tokens"], new)
    chars_by_sid = {}
    for c, sid in u["tokens"]:
        chars_by_sid[sid] = chars_by_sid.get(sid, "") + c
    chains = {sid: resolver.chain(page, st, chars_by_sid.get(sid, ""))
              for sid, st in enumerate(u["styles"])}
    cache = {}

    def pick(sid, ch):
        k = (sid, ch)
        if k not in cache:
            sel = None
            for f, src in chains[sid]:
                if f.has_glyph(ord(ch)):
                    sel = (f, src)
                    break
            if sel is None:
                sel = chains[sid][0]
                if not ch.isspace():
                    warnings.add("Some characters have no available glyph and may appear as boxes.")
            cache[k] = sel
        return cache[k]

    wrap = u["mode"] == "para"
    pr = page.rect
    page_right = pr.x1 - 12
    orig_w = u["bbox"][2] - u["bbox"][0]

    def run(scale):
        def width_of(t):
            f, _ = pick(t[1], t[0])
            return f.text_length(t[0], u["styles"][t[1]]["size"] * scale)
        if wrap:
            right = min(u["right"], page_right) if u["right"] <= page_right else u["right"]
            return layout_tokens(toks, True, right - u["x_first"], right - u["x_rest"], width_of)
        lines = layout_tokens(toks, False, 1e9, 1e9, width_of)
        return lines

    scale = 1.0
    lines = run(scale)
    if wrap:
        last_orig = u["y_first"] + (u["n_lines"] - 1) * u["pitch"]
        if fit:
            while scale > 0.7:
                y_last = u["y_first"] + (len(lines) - 1) * u["pitch"] * scale
                if y_last <= last_orig + 0.3 * u["pitch"]:
                    break
                scale -= 0.04
                lines = run(scale)
        y_last = u["y_first"] + (len(lines) - 1) * u["pitch"] * scale
        if y_last > pr.y1 - 10:
            warnings.add("An expanded paragraph extends beyond the bottom of the page.")
        elif not fit and len(lines) > u["n_lines"]:
            warnings.add("Expanded text may overlap content below. Enable Auto-shrink long text if needed.")
    else:
        def line_w(sc):
            return sum(pick(t[1], t[0])[0].text_length(t[0], u["styles"][t[1]]["size"] * sc)
                       for l in lines for t in l)
        w = line_w(1.0)
        avail = page_right - u["x_first"]
        if fit:
            avail = min(avail, max(orig_w, 10))
        if w > avail > 0:
            scale = max(avail / w, 0.5)

    out_lines, used = [], set()
    for l in lines:
        row = []
        for ch, sid in l:
            f, src = pick(sid, ch)
            row.append((ch, sid, f, src))
            if not ch.isspace():
                used.add(src)
        out_lines.append(row)
    if not used or "alt" not in used:
        label = "✓ Original"
    elif used == {"alt"}:
        label = "≈ Fallback"
    else:
        label = "≈ Mixed"
    return dict(lines=out_lines, scale=scale, label=label)


def draw_plan(page, u, plan):
    scale = plan["scale"]
    for li, line in enumerate(plan["lines"]):
        x = u["x_first"] if li == 0 else u["x_rest"]
        y = u["y_first"] + li * u["pitch"] * scale
        i = 0
        while i < len(line):
            _, sid, font, _ = line[i]
            j = i
            while j < len(line) and line[j][1] == sid and line[j][2] is font:
                j += 1
            s = "".join(c for c, *_ in line[i:j])
            st = u["styles"][sid]
            size = st["size"] * scale
            if s.strip():
                tw = fitz.TextWriter(page.rect)
                tw.append(fitz.Point(x, y), s, font=font, fontsize=size)
                tw.write_text(page, color=st["color"])
            x += font.text_length(s, size)
            i = j


def sample_bg(img, rect, zoom):
    """Sample the dominant color around a text box for background coverage."""
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


def apply_edits(src_bytes, edits, cover=False, fit=False, user_font=None):
    """Apply edits to the original PDF and return (doc, warnings, labels)."""
    doc = fitz.open("pdf", src_bytes)
    resolver = FontResolver(doc, hash(src_bytes), user_font)
    warnings, labels = set(), [""] * len(edits)
    by_page = {}
    for i, e in enumerate(edits):
        by_page.setdefault(e["page"], []).append((i, e))
    for pno, items in by_page.items():
        page = doc[pno]
        plans = []
        for i, e in items:  # Lay out text while fonts are available, then erase and redraw.
            plan = plan_edit(page, e, resolver, fit, warnings)
            labels[i] = plan["label"]
            plans.append((e["unit"], plan))
        bg_img = None
        if cover:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            bg_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        for u, _ in plans:
            for rt in u["rects"]:
                r = fitz.Rect(rt)
                if cover:
                    page.add_redact_annot(r, fill=sample_bg(bg_img, r, 2))
                else:
                    h = r.height * 0.12
                    page.add_redact_annot(fitz.Rect(r.x0 + 0.3, r.y0 + h, r.x1 - 0.3, r.y1 - h), fill=False)
        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                  graphics=getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0))
        except TypeError:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        for u, plan in plans:
            draw_plan(page, u, plan)
    return doc, sorted(warnings), labels


def words_to_text(words, merge=True):
    """Reconstruct selected words; merge=True combines paragraph lines."""
    def join(parts, dehyphen=False):
        out = ""
        for p in parts:
            if not p:
                continue
            if out:
                if dehyphen and out.endswith("-") and p[0].islower() and len(out) > 1 and out[-2].isalpha():
                    out = out[:-1]
                elif not (has_cjk(out[-1]) or has_cjk(p[0])):
                    out += " "
            out += p
        return out

    lines, order = {}, []
    for w in sorted(words, key=lambda w: (w[5], w[6], w[7])):
        k = (w[5], w[6])
        if k not in lines:
            lines[k] = []
            order.append(k)
        lines[k].append(w[4])
    blocks = {}
    for k in order:
        blocks.setdefault(k[0], []).append(join(lines[k]))
    out = []
    for ls in blocks.values():
        out.append(join(ls, dehyphen=True) if merge else "\n".join(ls))
    return "\n".join(out)


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
            raise ValueError(f"Invalid page range: {part}")
        if a < 1 or b > n or a > b:
            raise ValueError(f"Page range out of bounds: {part} (document has {n} pages)")
        pages.extend(range(a - 1, b))
    if not pages:
        raise ValueError("Enter a page range, such as 1-3,5,8-.")
    return pages


def add_watermark(page, kit, text, size, opacity, angle, color, tile):
    if not text:
        return
    if size <= 0:
        raise ValueError("Watermark font size must be greater than 0.")
    stamp = kit.watermark_stamp(text, size, opacity, color)
    w = stamp[0].rect.width
    rect = page.rect
    rotation = page.rotation
    derotation = page.derotation_matrix
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
    # Rotate the PDF Form without reflection and compensate for the page display rotation.
    turn = (angle + rotation) % 360
    bounds = stamp[0].rect * fitz.Matrix(turn)
    try:
        page.set_rotation(0)
        for cx, cy in centers:
            center = fitz.Point(cx, cy) * derotation
            target = fitz.Rect(center.x - bounds.width / 2, center.y - bounds.height / 2,
                               center.x + bounds.width / 2, center.y + bounds.height / 2)
            page.show_pdf_page(target, stamp, rotate=turn, keep_proportion=True, overlay=True)
    finally:
        page.set_rotation(rotation)


# ============================================================
#  UI helpers
# ============================================================
def make_card(parent, title=None):
    outer = tk.Frame(parent, bg=C["card"], highlightbackground=C["border"], highlightthickness=1)
    if title:
        tk.Label(outer, text=title, bg=C["card"], fg=C["text"],
                 font=UI["section"]).pack(anchor="w", padx=ui_px(16), pady=(ui_px(12), ui_px(4)))
    return outer


def wrapped_label(parent, **kwargs):
    opts = dict(bg=C["card"], fg=C["sub"], font=UI["caption"],
                anchor="w", justify="left", wraplength=ui_px(260))
    opts.update(kwargs)
    label = tk.Label(parent, **opts)
    label.bind("<Configure>", lambda e: label.config(wraplength=max(ui_px(80), e.width)), add="+")
    return label


def scrollable_area(parent):
    """Fill available space; allow scrolling when the panel is too small."""
    outer = tk.Frame(parent, bg=C["card"])
    outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer, bg=C["card"], highlightthickness=0, width=1, height=1)
    bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.configure(yscrollcommand=bar.set)
    content = tk.Frame(canvas, bg=C["card"])
    item = canvas.create_window(0, 0, window=content, anchor="nw")
    visible = [True]

    def resize(event=None):
        width, height = canvas.winfo_width(), canvas.winfo_height()
        requested = content.winfo_reqheight()
        canvas.itemconfigure(item, width=max(width, 1), height=max(height, requested))
        canvas.configure(scrollregion=(0, 0, width, max(height, requested)))
        need_scroll = requested > height + 1
        if need_scroll != visible[0]:
            if need_scroll:
                bar.pack(side="right", fill="y", before=canvas)
            else:
                bar.pack_forget()
            visible[0] = need_scroll

    canvas.bind("<Configure>", resize)
    content.bind("<Configure>", resize)

    def wheel(event, direction=None):
        widget = event.widget
        if widget.winfo_class() in ("Text", "Treeview", "Listbox", "TCombobox", "TSpinbox"):
            return None  # These widgets handle their own scrolling and selection.
        while widget is not None:
            if widget is content or widget is canvas:
                if visible[0]:
                    step = direction if direction is not None else (-1 if event.delta > 0 else 1)
                    canvas.yview_scroll(step * 3, "units")
                    return "break"
                return None
            widget = getattr(widget, "master", None)
        return None

    top = parent.winfo_toplevel()
    top.bind("<MouseWheel>", wheel, add="+")
    top.bind("<Button-4>", lambda e: wheel(e, -1), add="+")
    top.bind("<Button-5>", lambda e: wheel(e, 1), add="+")
    return content


class App:
    PAD = 24

    def __init__(self, root):
        global FONT, UI, UI_SCALE
        self.root = root
        FONT = pick_ui_font()
        UI = ui_fonts()
        UI_SCALE = max(0.85, min(root.winfo_fpixels("1i") / 96.0, 3.0))
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkTooltipFont"):
            tkfont.nametofont(name).configure(family=FONT, size=10)
        root.option_add("*Font", UI["body"])
        root.title(f"{APP_NAME} - PDF Toolkit")
        available_w = max(800, root.winfo_screenwidth() - ui_px(64))
        available_h = max(540, root.winfo_screenheight() - ui_px(90))
        width, height = min(ui_px(1320), available_w), min(ui_px(840), available_h)
        root.geometry(f"{width}x{height}")
        root.minsize(min(ui_px(1000), available_w), min(ui_px(640), available_h))
        root.configure(bg=C["bg"])

        # ---- Editor state ----
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

        self.user_font = None
        # ---- Selection and copy ----
        self.tool = tk.StringVar(value="edit")
        self.merge_var = tk.BooleanVar(value=True)
        self.autocopy_var = tk.BooleanVar(value=True)
        self.sel_words, self.sel_rects = [], []
        self.words = None
        self.base_img = None
        self.img_item = None
        self.drag_start = None
        self.rubber = None
        self.mode_var = tk.StringVar(value="line")
        self.cover_var = tk.BooleanVar(value=False)
        self.fit_var = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready")

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
    #  Styles
    # ------------------------------------------------------------
    def setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", font=UI["body"], background=C["bg"], foreground=C["text"])
        s.configure("TFrame", background=C["bg"])
        s.configure("Card.TFrame", background=C["card"])
        s.configure("TLabel", background=C["bg"], foreground=C["text"])
        s.configure("Card.TLabel", background=C["card"])
        s.configure("Sub.TLabel", background=C["card"], foreground=C["sub"], font=UI["caption"])
        s.configure("TButton", padding=(ui_px(12), ui_px(7)), background=C["card"], foreground=C["text"],
                    bordercolor="#D1D5DB", lightcolor=C["card"], darkcolor=C["card"], relief="solid", borderwidth=1)
        s.map("TButton", background=[("active", "#EEF2FF"), ("disabled", "#F3F4F6")],
              foreground=[("disabled", "#9CA3AF")])
        s.configure("Accent.TButton", background=C["accent"], foreground="#FFFFFF",
                    bordercolor=C["accent"], lightcolor=C["accent"], darkcolor=C["accent"],
                    font=(FONT, 10, "bold"))
        s.map("Accent.TButton", background=[("active", C["accent_h"]), ("disabled", "#93C5FD")],
              foreground=[("disabled", "#FFFFFF")])
        s.configure("Tool.TButton", padding=(ui_px(8), ui_px(5)))
        s.configure("TEntry", fieldbackground="#FFFFFF", bordercolor=C["border"],
                    lightcolor="#FFFFFF", darkcolor="#FFFFFF", padding=ui_px(6))
        s.configure("TCombobox", fieldbackground="#FFFFFF", bordercolor=C["border"], padding=ui_px(5))
        s.configure("TSpinbox", fieldbackground="#FFFFFF", bordercolor=C["border"], padding=ui_px(5))
        for w in ("TCheckbutton", "TRadiobutton"):
            s.configure(w, background=C["card"])
            s.map(w, background=[("active", C["card"]), ("disabled", C["card"])],
                  foreground=[("disabled", "#9CA3AF")])
        s.configure("Treeview", rowheight=ui_px(30), background="#FFFFFF", fieldbackground="#FFFFFF",
                    bordercolor=C["border"], borderwidth=0, font=UI["body"])
        s.configure("Treeview.Heading", background="#F9FAFB", foreground=C["text"],
                    font=UI["body"], relief="flat", padding=ui_px(6))
        s.map("Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", C["text"])])
        for o in ("Vertical", "Horizontal"):
            s.configure(f"{o}.TScrollbar", background="#C4CAD4", troughcolor=C["bg"],
                        bordercolor=C["bg"], lightcolor="#C4CAD4", darkcolor="#C4CAD4",
                        arrowsize=ui_px(12), relief="flat")
        s.configure("Horizontal.TProgressbar", background=C["accent"], troughcolor="#E5E7EB",
                    bordercolor="#E5E7EB", lightcolor=C["accent"], darkcolor=C["accent"])
        s.configure("TScale", background=C["card"])
        s.configure("TSeparator", background=C["border"])

    # ------------------------------------------------------------
    #  Shell: sidebar, content area, and status bar
    # ------------------------------------------------------------
    def build_shell(self):
        bar = tk.Frame(self.root, bg="#FFFFFF", height=ui_px(30), highlightbackground=C["border"], highlightthickness=1)
        bar.pack(side="bottom", fill="x")
        side = tk.Frame(self.root, bg=C["side"], width=ui_px(192))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text=APP_NAME, bg=C["side"], fg="#FFFFFF",
                 font=UI["brand"]).pack(anchor="w", padx=ui_px(18), pady=(ui_px(24), 2))
        tk.Label(side, text="Everyday PDF tools", bg=C["side"], fg=C["side_text"],
                 font=UI["caption"]).pack(anchor="w", padx=ui_px(18), pady=(0, ui_px(22)))

        self.nav = {}
        items = [("edit", "Text editor"), ("merge", "Merge PDFs"), ("split", "Split PDF"),
                 ("wm", "Watermark"), ("img", "Pages to images"), ("sec", "Security")]
        for key, label in items:
            lb = tk.Label(side, text=label, bg=C["side"], fg=C["side_text"], anchor="w",
                          font=UI["nav"], padx=ui_px(16), pady=ui_px(11), cursor="hand2")
            lb.pack(fill="x", padx=ui_px(10), pady=2)
            lb.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            lb.bind("<Enter>", lambda e, w=lb, k=key: w.config(bg=C["side_hover"]) if self.cur != k else None)
            lb.bind("<Leave>", lambda e, w=lb, k=key: w.config(bg=C["side"]) if self.cur != k else None)
            self.nav[key] = lb
        tk.Label(side, text="Ctrl+O  Open PDF\nCtrl+S  Save edits\nCtrl+Z  Undo edit", bg=C["side"], fg=C["side_text"],
                 font=UI["caption"], justify="left").pack(side="bottom", anchor="w", padx=ui_px(18), pady=ui_px(18))

        right = tk.Frame(self.root, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)
        tk.Label(bar, textvariable=self.status, bg="#FFFFFF", fg=C["sub"], font=UI["caption"],
                 anchor="w", width=1).pack(fill="x", padx=ui_px(14), pady=ui_px(5))
        self.header = tk.Label(right, text="", bg=C["bg"], fg=C["text"], font=UI["title"], anchor="w")
        self.header.pack(fill="x", padx=ui_px(20), pady=(ui_px(18), ui_px(3)))
        self.page_hint = wrapped_label(right, text="", bg=C["bg"])
        self.page_hint.pack(fill="x", padx=ui_px(20), pady=(0, ui_px(12)))
        self.container = tk.Frame(right, bg=C["bg"])
        self.container.pack(fill="both", expand=True, padx=ui_px(20), pady=(0, ui_px(16)))
        self.pages = {}
        self.cur = None

    def page_frame(self, key):
        f = tk.Frame(self.container, bg=C["bg"])
        f.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.pages[key] = f
        return f

    TITLES = {"edit": "Text editor", "merge": "Merge PDFs", "split": "Split / extract pages",
              "wm": "Watermark", "img": "Export pages as images", "sec": "Security"}
    HINTS = {"edit": "Edit text in place, or select and copy full paragraphs.",
             "merge": "Arrange PDF files in order and merge them into one document.",
             "split": "Extract a page range or save each page as a separate PDF.",
             "wm": "Adjust the watermark on the left; preview it on the right. Save applies it to every page.",
             "img": "Export each complete page as a separate PNG or JPG image.",
             "sec": "Protect a PDF with a password or remove existing password protection."}

    def show_page(self, key):
        self.cur = key
        for k, lb in self.nav.items():
            lb.config(bg=C["side_active"] if k == key else C["side"],
                      fg="#FFFFFF" if k == key else C["side_text"])
        self.pages[key].tkraise()
        self.header.config(text=self.TITLES[key])
        self.page_hint.config(text=self.HINTS[key])
        if key == "wm":
            self.wm_schedule_preview()

    def set_status(self, msg):
        self.status.set(msg)
        self.root.update_idletasks()

    def busy(self, on=True):
        self.root.config(cursor="watch" if on else "")
        self.root.update_idletasks()

    def file_row(self, parent, var, cmd, text="Choose file"):
        row = tk.Frame(parent, bg=C["card"])
        row.pack(fill="x", padx=ui_px(16), pady=(ui_px(6), ui_px(14)))
        e = ttk.Entry(row, textvariable=var, state="readonly")
        e.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=text, command=cmd).pack(side="left", padx=(ui_px(10), 0))

    def pick_pdf(self, var, after=None):
        p = filedialog.askopenfilename(title="Choose PDF", filetypes=[("PDF files", "*.pdf")])
        if p:
            var.set(p)
            if after:
                after(p)

    @staticmethod
    def ask_password(doc, path):
        if not doc.needs_pass:
            return True
        pw = simpledialog.askstring("Password required", f"Enter the password for {os.path.basename(path)}:", show="*")
        return bool(pw) and bool(doc.authenticate(pw))

    # ============================================================
    #  1. Text editor
    # ============================================================
    def build_editor(self):
        page = self.page_frame("edit")

        tb = make_card(page)
        tb.pack(fill="x")
        inner = tk.Frame(tb, bg=C["card"])
        inner.pack(fill="x", padx=ui_px(12), pady=(ui_px(10), ui_px(6)))
        ttk.Button(inner, text="Open PDF", style="Accent.TButton", command=self.open_pdf).pack(side="left")
        self.btn_save = ttk.Button(inner, text="Save as...", command=self.save_pdf, state="disabled")
        self.btn_save.pack(side="left", padx=(ui_px(8), 0))
        ttk.Button(inner, text="Find and replace", style="Tool.TButton", command=self.find_replace).pack(side="right")
        inner = tk.Frame(tb, bg=C["card"])
        inner.pack(fill="x", padx=ui_px(12), pady=(0, ui_px(10)))

        self.btn_prev = ttk.Button(inner, text="◀", width=3, style="Tool.TButton", command=lambda: self.goto(self.page_no - 1), state="disabled")
        self.btn_prev.pack(side="left")
        self.page_entry = ttk.Entry(inner, width=4, justify="center")
        self.page_entry.pack(side="left", padx=4)
        self.page_entry.bind("<Return>", lambda e: self.goto(self._page_from_entry()))
        self.page_total = tk.Label(inner, text="/ -", bg=C["card"], fg=C["sub"], font=UI["body"])
        self.page_total.pack(side="left")
        self.btn_next = ttk.Button(inner, text="▶", width=3, style="Tool.TButton", command=lambda: self.goto(self.page_no + 1), state="disabled")
        self.btn_next.pack(side="left", padx=(4, ui_px(16)))
        ttk.Separator(inner, orient="vertical").pack(side="left", fill="y", padx=(0, ui_px(16)))

        ttk.Button(inner, text="－", width=3, style="Tool.TButton", command=lambda: self.set_zoom(self.zoom / 1.15)).pack(side="left")
        self.zoom_lbl = tk.Label(inner, text="130%", width=5, bg=C["card"], fg=C["text"], font=UI["body"])
        self.zoom_lbl.pack(side="left")
        ttk.Button(inner, text="＋", width=3, style="Tool.TButton", command=lambda: self.set_zoom(self.zoom * 1.15)).pack(side="left")
        ttk.Button(inner, text="Fit width", style="Tool.TButton", command=self.fit_width).pack(side="left", padx=(ui_px(8), 0))

        body = tk.PanedWindow(page, orient="horizontal", bg=C["bg"], borderwidth=0,
                              sashwidth=ui_px(10), sashrelief="flat", opaqueresize=True)
        body.pack(fill="both", expand=True, pady=(ui_px(12), 0))

        # ---- Left: document canvas ----
        left = tk.Frame(body, bg=C["canvas"], highlightbackground=C["border"], highlightthickness=1)
        body.add(left, minsize=ui_px(260), stretch="always")
        self.canvas = tk.Canvas(left, bg=C["canvas"], highlightthickness=0)
        vs = ttk.Scrollbar(left, orient="vertical", command=self.canvas.yview)
        hs = ttk.Scrollbar(left, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Control-a>", lambda e: self.select_all())
        self.canvas.bind("<Control-c>", lambda e: self.copy_selection())
        self.canvas.bind("<Leave>", lambda e: self.set_hover(None))
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.on_wheel(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self.on_wheel(e, -1))
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())
        self.canvas.bind("<Configure>", lambda e: self.draw_placeholder() if self.view_doc is None else None)
        self.draw_placeholder()

        # ---- Right: tools panel ----
        right = tk.Frame(body, bg=C["bg"], width=ui_px(326))
        body.add(right, minsize=ui_px(290), width=ui_px(326), stretch="never")
        right.pack_propagate(False)
        sw = tk.Frame(right, bg=C["bg"])
        sw.pack(fill="x", pady=(0, 10))
        sw.columnconfigure((0, 1), weight=1, uniform="sw")
        self.btn_tool_edit = ttk.Button(sw, text="Edit text", style="Accent.TButton", command=lambda: self.set_tool("edit"))
        self.btn_tool_edit.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_tool_sel = ttk.Button(sw, text="Select & copy", command=lambda: self.set_tool("select"))
        self.btn_tool_sel.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        edit_panel = tk.Frame(right, bg=C["bg"])
        edit_panel.pack(fill="both", expand=True)
        self.edit_panel = edit_panel
        self.build_select_panel(right)
        edit_content = scrollable_area(edit_panel)

        guide = make_card(edit_content, "How to edit")
        guide.pack(fill="x")
        wrapped_label(guide, text="Click text to edit. Enter confirms; Esc cancels.\nUse Shift+Enter for a paragraph line break."
                      ).pack(fill="x", padx=ui_px(16), pady=(2, ui_px(12)))

        opt = make_card(edit_content, "Editing options")
        opt.pack(fill="x", pady=(10, 0))
        ttk.Label(opt, text="Edit unit", style="Sub.TLabel").pack(anchor="w", padx=16)
        r = tk.Frame(opt, bg=C["card"])
        r.pack(anchor="w", padx=12, pady=(2, 4))
        self.mode_btns = []
        for txt, val in (("Line", "line"), ("Span", "span"), ("Paragraph", "para")):
            rb = ttk.Radiobutton(r, text=txt, value=val, variable=self.mode_var, command=self.on_mode_change)
            rb.pack(side="left", padx=4)
            self.mode_btns.append(rb)
        ttk.Checkbutton(opt, text="Auto-shrink long text", variable=self.fit_var,
                        command=self.refresh_view).pack(anchor="w", padx=16, pady=2)
        ttk.Checkbutton(opt, text="Cover text on image backgrounds", variable=self.cover_var,
                        command=self.refresh_view).pack(anchor="w", padx=16, pady=2)
        fr = tk.Frame(opt, bg=C["card"])
        fr.pack(fill="x", padx=16, pady=(4, 12))
        ttk.Button(fr, text="Fallback font...", style="Tool.TButton", command=self.choose_font).pack(side="left")
        self.font_lbl = wrapped_label(fr, text="Automatic")
        self.font_lbl.pack(side="left", fill="x", expand=True, padx=8)

        lst = make_card(edit_content, "Changes")
        lst.pack(fill="both", expand=True, pady=(10, 0))
        bt = tk.Frame(lst, bg=C["card"])
        bt.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        tree_frame = tk.Frame(lst, bg=C["card"])
        tree_frame.pack(fill="both", expand=True, padx=ui_px(12), pady=(4, 6))
        self.tree = ttk.Treeview(tree_frame, columns=("p", "old", "new", "font"), show="headings", height=4, selectmode="browse")
        self.tree.heading("p", text="Page")
        self.tree.heading("old", text="Original")
        self.tree.heading("new", text="New text")
        self.tree.heading("font", text="Font")
        self.tree.column("p", width=ui_px(44), anchor="center", stretch=False)
        self.tree.column("old", width=ui_px(78))
        self.tree.column("new", width=ui_px(78))
        self.tree.column("font", width=ui_px(70), stretch=False)
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        ttk.Button(bt, text="Undo selected", style="Tool.TButton", command=self.undo_selected).pack(side="left")
        ttk.Button(bt, text="Undo all", style="Tool.TButton", command=self.undo_all).pack(side="left", padx=6)

    def draw_placeholder(self):
        self.canvas.delete("all")
        w, h = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        self.canvas.create_text(w / 2, h / 2 - ui_px(18), text="Open a PDF to get started", font=UI["section"],
                                fill=C["sub"], width=max(80, w - ui_px(40)), tags="ph")
        self.canvas.create_text(w / 2, h / 2 + ui_px(14), text="Edit text or select and copy paragraphs", font=UI["caption"],
                                fill=C["sub"], width=max(80, w - ui_px(40)), tags="ph")

    # ---------- Open / save ----------
    def open_pdf(self):
        p = filedialog.askopenfilename(title="Open PDF", filetypes=[("PDF files", "*.pdf")])
        if not p:
            return
        try:
            doc = fitz.open(p)
            if not self.ask_password(doc, p):
                messagebox.showerror("Error", "Incorrect password or canceled.")
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
            self.clear_selection(repaint=False)
            self.btn_save.config(state="normal")
            self.update_tree()
            self.update_mode_lock()
            self.fit_width(render=False)
            self.render()
            self.set_status(f"Opened {os.path.basename(p)} ({self.orig_doc.page_count} pages)")
        except Exception as ex:
            messagebox.showerror("Error", f"Cannot open PDF: {ex}")

    def save_pdf(self):
        if not self.orig_doc:
            return
        if not self.edits:
            messagebox.showinfo("Notice", "No changes to save.\nClick text on a page to start editing.")
            return
        base = os.path.splitext(os.path.basename(self.src_path))[0]
        out = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
            initialfile=f"{base}_edited.pdf", initialdir=os.path.dirname(self.src_path))
        if not out:
            return
        try:
            self.busy()
            doc, warns, labels = apply_edits(self.src_bytes, list(self.edits.values()),
                                             self.cover_var.get(), self.fit_var.get(), self.user_font)
            doc.save(out, garbage=3, deflate=True)
            doc.close()
            self.busy(False)
            msg = f"Saved {len(self.edits)} edits:\n{out}"
            alt = sum(1 for l in labels if l.startswith("≈"))
            if alt:
                msg += f"\n\n{alt} edits use fallback fonts (marked with ≈). Choose a fallback font for a closer match."
            if warns:
                msg += "\n\nNote: " + "; ".join(warns)
            messagebox.showinfo("Saved", msg)
            self.set_status(f"Saved: {out}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("Save failed", str(ex))

    # ---------- Page rendering ----------
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
        self.clear_selection(repaint=False)
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

    def get_units(self, page_no=None):
        key = self.page_no if page_no is None else page_no
        if key not in self.units_cache:
            self.units_cache[key] = extract_units(self.orig_doc[key], self.mode_var.get())
        return self.units_cache[key]

    def render(self):
        if not self.view_doc:
            return
        page = self.view_doc[self.page_no]
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        self.base_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.words = None
        self._compose()
        P = self.PAD
        self.canvas.delete("all")
        self.canvas.create_rectangle(P + 4, P + 4, P + pix.width + 4, P + pix.height + 4, fill="#B8BFCB", outline="")
        self.img_item = self.canvas.create_image(P, P, anchor="nw", image=self.tk_image)
        self.canvas.config(scrollregion=(0, 0, pix.width + 2 * P, pix.height + 2 * P))
        self.units = self.get_units()
        # Edited text indicators
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
            self.set_status("Text editing is unavailable on rotated pages.")
        elif not self.units:
            self.set_status("This page has no editable text; it may be a scan or image.")

    def refresh_view(self):
        """Rebuild the preview after edits or option changes."""
        if not self.orig_doc:
            return
        self.clear_selection(repaint=False)
        if self.edits:
            try:
                self.busy()
                vals = [self.edits[k] for k in self.edits]
                self.view_doc, warns, labels = apply_edits(self.src_bytes, vals, self.cover_var.get(),
                                                           self.fit_var.get(), self.user_font)
                for e, l in zip(vals, labels):
                    e["label"] = l
                if warns:
                    self.set_status("Note: " + "; ".join(warns))
            finally:
                self.busy(False)
        else:
            self.view_doc = self.orig_doc
        self.update_tree()
        self.render()

    # ---------- Coordinates / hit testing ----------
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
            self.canvas.config(cursor="xterm" if self.tool.get() == "select" else "")
        else:
            x0, y0, x1, y1 = self.to_canvas(u["bbox"])
            self.canvas.coords(self.hover_id, x0 - 2, y0 - 1, x1 + 2, y1 + 1)
            self.canvas.itemconfigure(self.hover_id, state="normal")
            self.canvas.tag_raise(self.hover_id)
            self.canvas.config(cursor="xterm")

    def on_motion(self, ev):
        if not self.orig_doc:
            return
        if self.tool.get() == "select":
            self.hover_block(ev)
        elif self.units:
            self.set_hover(self.unit_at(ev))

    def on_wheel(self, ev, direction=None):
        d = direction if direction is not None else (1 if ev.delta > 0 else -1)
        if ev.state & 0x4:  # Ctrl
            self.set_zoom(self.zoom * (1.1 if d > 0 else 1 / 1.1))
        elif ev.state & 0x1:  # Shift
            self.canvas.xview_scroll(-d * 3, "units")
        else:
            self.canvas.yview_scroll(-d * 3, "units")

    # ============================================================
    #  Selection and copy (drag area / click paragraph / Ctrl+A)
    # ============================================================
    def build_select_panel(self, parent):
        p = tk.Frame(parent, bg=C["bg"])
        self.select_panel = p
        content = scrollable_area(p)
        g = make_card(content, "Select and copy")
        g.pack(fill="x")
        wrapped_label(g, text="Drag to select an area or click a paragraph.\nCtrl+A selects this page; Ctrl+C copies."
                      ).pack(fill="x", padx=ui_px(16), pady=(2, 6))
        ttk.Checkbutton(g, text="Merge paragraph line breaks", variable=self.merge_var,
                        command=self.update_preview).pack(anchor="w", padx=16, pady=2)
        ttk.Checkbutton(g, text="Copy automatically on selection", variable=self.autocopy_var).pack(anchor="w", padx=16, pady=(2, 12))

        card = make_card(content, "Selected text")
        card.pack(fill="both", expand=True, pady=(10, 0))
        self.sel_info = wrapped_label(card, text="Nothing selected")
        self.sel_info.pack(fill="x", padx=ui_px(16))
        btns = tk.Frame(card, bg=C["card"])
        btns.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="Copy", style="Accent.TButton", command=self.copy_selection).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        ttk.Button(btns, text="Copy page", style="Tool.TButton", command=self.copy_page).grid(row=1, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(btns, text="Copy all", style="Tool.TButton", command=self.copy_all).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(btns, text="Clear", style="Tool.TButton", command=self.clear_selection).grid(row=1, column=2, sticky="ew", padx=(4, 0))
        for c in range(3):
            btns.columnconfigure(c, weight=1)
        text_frame = tk.Frame(card, bg=C["card"])
        text_frame.pack(fill="both", expand=True, padx=ui_px(12), pady=(6, ui_px(10)))
        self.sel_text = tk.Text(text_frame, wrap="word", font=UI["body"], relief="flat", bg="#F9FAFB", fg=C["text"],
                                highlightthickness=1, highlightbackground=C["border"], padx=8, pady=6, height=8)
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.sel_text.yview)
        text_scroll.pack(side="right", fill="y")
        self.sel_text.configure(yscrollcommand=text_scroll.set)
        self.sel_text.pack(side="left", fill="both", expand=True)

    def set_tool(self, tool):
        self.tool.set(tool)
        self.cancel_entry()
        self.set_hover(None)
        if tool == "edit":
            self.select_panel.pack_forget()
            self.edit_panel.pack(fill="both", expand=True)
            self.btn_tool_edit.config(style="Accent.TButton")
            self.btn_tool_sel.config(style="TButton")
            self.canvas.config(cursor="")
            self.set_status("Edit mode: click page text to change it.")
        else:
            self.edit_panel.pack_forget()
            self.select_panel.pack(fill="both", expand=True)
            self.btn_tool_edit.config(style="TButton")
            self.btn_tool_sel.config(style="Accent.TButton")
            self.canvas.config(cursor="xterm")
            self.set_status("Select mode: drag an area or click a paragraph.")

    def page_words(self):
        if self.words is None and self.view_doc:
            ws = self.view_doc[self.page_no].get_text("words")
            self.words = sorted(ws, key=lambda w: (w[5], w[6], w[7]))
        return self.words or []

    def _compose(self):
        img = self.base_img
        if self.sel_rects:
            z = self.zoom
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            for x0, y0, x1, y1 in self.sel_rects:
                d.rectangle([x0 * z - 1, y0 * z - 1, x1 * z + 1, y1 * z + 1], fill=(37, 99, 235, 80))
            img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        self.tk_image = ImageTk.PhotoImage(img)

    def _repaint(self):
        if self.base_img is not None and self.img_item is not None:
            self._compose()
            self.canvas.itemconfigure(self.img_item, image=self.tk_image)

    def _to_pdf(self, cx, cy):
        return (cx - self.PAD) / self.zoom, (cy - self.PAD) / self.zoom

    def word_at(self, x, y, margin=2.5):
        best, dist = None, 1e9
        for w in self.page_words():
            if w[0] - margin <= x <= w[2] + margin and w[1] - margin <= y <= w[3] + margin:
                d = abs((w[0] + w[2]) / 2 - x) + abs((w[1] + w[3]) / 2 - y)
                if d < dist:
                    best, dist = w, d
        return best

    def block_rect(self, block_no):
        ws = [w for w in self.page_words() if w[5] == block_no]
        if not ws:
            return None
        return (min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws))

    def hover_block(self, ev):
        if self.drag_start or self.hover_id is None:
            return
        x, y = self._to_pdf(self.canvas.canvasx(ev.x), self.canvas.canvasy(ev.y))
        w = self.word_at(x, y)
        r = self.block_rect(w[5]) if w else None
        if r is None:
            self.canvas.itemconfigure(self.hover_id, state="hidden")
        else:
            x0, y0, x1, y1 = self.to_canvas(r)
            self.canvas.coords(self.hover_id, x0 - 3, y0 - 2, x1 + 3, y1 + 2)
            self.canvas.itemconfigure(self.hover_id, state="normal")
            self.canvas.tag_raise(self.hover_id)

    def on_press(self, ev):
        if not self.orig_doc:
            return
        if self.tool.get() == "edit":
            self.on_click(ev)
            return
        self.canvas.focus_set()
        self.drag_start = (self.canvas.canvasx(ev.x), self.canvas.canvasy(ev.y))

    def on_drag(self, ev):
        if self.tool.get() != "select" or not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = self.canvas.canvasx(ev.x), self.canvas.canvasy(ev.y)
        if self.rubber is None:
            self.rubber = self.canvas.create_rectangle(x0, y0, x1, y1, outline=C["accent"], width=1, dash=(4, 3))
            if self.hover_id is not None:
                self.canvas.itemconfigure(self.hover_id, state="hidden")
        else:
            self.canvas.coords(self.rubber, x0, y0, x1, y1)

    def on_release(self, ev):
        if self.tool.get() != "select" or not self.drag_start:
            return
        sx, sy = self.drag_start
        ex, ey = self.canvas.canvasx(ev.x), self.canvas.canvasy(ev.y)
        self.drag_start = None
        if self.rubber is not None:
            self.canvas.delete(self.rubber)
            self.rubber = None
        if abs(ex - sx) < 4 and abs(ey - sy) < 4:  # Click -> select the full paragraph
            x, y = self._to_pdf(ex, ey)
            w = self.word_at(x, y)
            if w:
                self.set_selection([v for v in self.page_words() if v[5] == w[5]])
            else:
                self.clear_selection()
            return
        ax, ay = self._to_pdf(min(sx, ex), min(sy, ey))
        bx, by = self._to_pdf(max(sx, ex), max(sy, ey))
        ws = [w for w in self.page_words()
              if ax <= (w[0] + w[2]) / 2 <= bx and ay <= (w[1] + w[3]) / 2 <= by]
        if ws:
            self.set_selection(ws)
        else:
            self.clear_selection()

    def select_all(self):
        if self.orig_doc and self.tool.get() == "select":
            self.set_selection(list(self.page_words()))
        return "break"

    def set_selection(self, words):
        self.sel_words = words
        lines = {}
        for w in words:
            k = (w[5], w[6])
            r = lines.get(k)
            lines[k] = (min(r[0], w[0]), min(r[1], w[1]), max(r[2], w[2]), max(r[3], w[3])) if r else (w[0], w[1], w[2], w[3])
        self.sel_rects = list(lines.values())
        self._repaint()
        self.update_preview()
        if self.autocopy_var.get() and words:
            self.copy_selection(quiet=True)

    def clear_selection(self, repaint=True):
        self.sel_words, self.sel_rects = [], []
        if hasattr(self, "sel_text"):
            self.sel_text.delete("1.0", tk.END)
            self.sel_info.config(text="Nothing selected")
        if repaint:
            self._repaint()

    def update_preview(self):
        if not self.sel_words:
            return
        text = words_to_text(self.sel_words, self.merge_var.get())
        self.sel_text.delete("1.0", tk.END)
        self.sel_text.insert("1.0", text)
        self.sel_info.config(text=f"{len(text.replace(chr(10), ''))} characters selected. Edit below before copying.")

    def _clip(self, text, note):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.set_status(note)

    def copy_selection(self, quiet=False):
        text = self.sel_text.get("1.0", "end-1c") if self.sel_words else ""
        if not text.strip():
            if not quiet:
                self.set_status("Nothing selected. Drag an area or click a paragraph.")
            return "break"
        self._clip(text, f"Copied {len(text)} characters to the clipboard.")
        return "break"

    def copy_page(self):
        if self.orig_doc:
            t = words_to_text(self.page_words(), self.merge_var.get())
            self._clip(t, f"Copied page {self.page_no + 1} ({len(t)} characters).") if t.strip() else self.set_status("This page has no text to copy.")

    def copy_all(self):
        if not self.view_doc:
            return
        parts = []
        for pg in self.view_doc:
            ws = sorted(pg.get_text("words"), key=lambda w: (w[5], w[6], w[7]))
            if ws:
                parts.append(words_to_text(ws, self.merge_var.get()))
        t = "\n\n".join(parts)
        self._clip(t, f"Copied all text ({self.view_doc.page_count} pages, {len(t)} characters).") if t.strip() else self.set_status("This document has no text to copy.")

    # ---------- In-place editing ----------
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
        para = u["mode"] == "para"
        width = int(x1 - x0) + 16 if para else max(int(x1 - x0) + 24, 220)
        height = int(y1 - y0) + 14 if para else int(y1 - y0) + 8
        self.entry = tk.Text(self.canvas, font=fnt, relief="flat", bg="#FFFBEB", fg="#111827",
                             insertbackground=C["accent"], highlightthickness=2, padx=3, pady=1,
                             highlightbackground=C["accent"], highlightcolor=C["accent"],
                             wrap="word" if para else "none", undo=True)
        self.entry.insert("1.0", cur)
        self.entry.tag_add("sel", "1.0", "end-1c")
        self.entry_key = (key, u)
        self.canvas.create_window(x0 - 3, y0 - 3, window=self.entry, anchor="nw", width=width,
                                  height=height, tags="entry")
        self.entry.focus_set()

        def on_return(_):
            self.commit_entry()
            return "break"

        def on_shift_return(_):
            if para:
                self.entry.insert("insert", "\n")
            return "break"
        self.entry.bind("<Return>", on_return)
        self.entry.bind("<KP_Enter>", on_return)
        self.entry.bind("<Shift-Return>", on_shift_return)
        self.entry.bind("<Escape>", lambda e: self.cancel_entry())
        self.entry.bind("<FocusOut>", lambda e: self.root.after(60, self.commit_entry))
        self.set_hover(None)
        self.set_status("Press Enter to confirm or Esc to cancel." + (" Shift+Enter inserts a line break." if para else ""))

    def cancel_entry(self):
        if self.entry:
            e, self.entry, self.entry_key = self.entry, None, None
            e.destroy()
            self.canvas.delete("entry")

    def commit_entry(self):
        if not self.entry:
            return
        key, u = self.entry_key
        new = self.entry.get("1.0", "end-1c")
        self.cancel_entry()
        if self.set_edit(key[0], u, new):
            self.update_mode_lock()
            self.refresh_view()
            self.set_status(f"{len(self.edits)} edits pending. Use Save as... when finished.")

    def set_edit(self, page_no, u, new):
        """Record one edit and return whether it changed."""
        key = (page_no, u["idx"])
        old = self.edits.get(key)
        prev = old["new"] if old else u["text"]
        if new == prev:
            return False
        if key in self.edit_order:
            self.edit_order.remove(key)
        if new == u["text"]:
            self.edits.pop(key, None)
        else:
            self.edits[key] = dict(page=page_no, unit=u, new=new, label="")
            self.edit_order.append(key)
        return True

    # ---------- Find and replace ----------
    def find_replace(self):
        if not self.orig_doc:
            messagebox.showinfo("Notice", "Open a PDF first.")
            return
        self.cancel_entry()
        dlg = tk.Toplevel(self.root)
        dlg.title("Find and replace")
        dlg.configure(bg=C["card"])
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry(f"+{self.root.winfo_rootx() + 300}+{self.root.winfo_rooty() + 160}")
        body = tk.Frame(dlg, bg=C["card"])
        body.pack(padx=22, pady=18)
        tk.Label(body, text="Find", bg=C["card"], fg=C["sub"]).grid(row=0, column=0, sticky="w", pady=6)
        e1 = ttk.Entry(body, width=36)
        e1.grid(row=0, column=1, padx=(12, 0))
        tk.Label(body, text="Replace with", bg=C["card"], fg=C["sub"]).grid(row=1, column=0, sticky="w", pady=6)
        e2 = ttk.Entry(body, width=36)
        e2.grid(row=1, column=1, padx=(12, 0))
        case = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text="Match case", variable=case).grid(row=2, column=1, sticky="w", pady=4)
        tk.Label(body, text="Scope: all pages. Match the current edit unit; use Paragraph for multiline text.",
                 bg=C["card"], fg=C["sub"], font=UI["caption"], wraplength=ui_px(420),
                 justify="left").grid(row=3, column=0, columnspan=2, sticky="w")
        res = tk.Label(body, text="", bg=C["card"], fg=C["ok"], font=UI["caption"])
        res.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def go():
            find, repl = e1.get(), e2.get()
            if not find:
                return
            pat = re.compile(re.escape(find), 0 if case.get() else re.IGNORECASE)
            n_units = n_hits = 0
            for p in range(self.orig_doc.page_count):
                for u in self.get_units(p):
                    cur = self.edits[(p, u["idx"])]["new"] if (p, u["idx"]) in self.edits else u["text"]
                    hits = len(pat.findall(cur))
                    if hits and self.set_edit(p, u, pat.sub(lambda m: repl, cur)):
                        n_units += 1
                        n_hits += hits
            if n_hits:
                self.update_mode_lock()
                self.refresh_view()
                res.config(text=f"Replaced {n_hits} matches in {n_units} text units.", fg=C["ok"])
                self.set_status(f"Find and replace: {n_hits} matches replaced.")
            else:
                res.config(text="No matching text found.", fg="#DC2626")
        bt = tk.Frame(dlg, bg=C["card"])
        bt.pack(fill="x", padx=22, pady=(0, 18))
        ttk.Button(bt, text="Replace all", style="Accent.TButton", command=go).pack(side="right")
        ttk.Button(bt, text="Close", command=dlg.destroy).pack(side="right", padx=8)
        e1.focus_set()
        dlg.bind("<Return>", lambda e: go())

    def choose_font(self):
        p = filedialog.askopenfilename(title="Choose a fallback font for missing glyphs",
                                       filetypes=[("Font files", "*.ttf *.ttc *.otf"), ("All files", "*.*")])
        if p:
            self.user_font = p
            self.font_lbl.config(text=os.path.basename(p))
            self.refresh_view()

    # ---------- Change list / undo ----------
    def update_tree(self):
        self.tree.delete(*self.tree.get_children())
        for key in self.edit_order:
            e = self.edits[key]
            short = lambda t: (t.replace("\n", " ")[:10] + "…") if len(t) > 10 else t.replace("\n", " ")
            self.tree.insert("", "end", iid=f"{key[0]}:{key[1]}",
                             values=(key[0] + 1, short(e["unit"]["text"]), short(e["new"]), e.get("label", "")))

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
        if self.edits and messagebox.askyesno("Confirm", "Undo all changes?"):
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
        for rb in self.mode_btns:
            rb.config(state=st)

    # ============================================================
    #  2. Merge PDFs
    # ============================================================
    def build_merge(self):
        page = self.page_frame("merge")
        card = make_card(page, "Files in merge order")
        card.pack(fill="both", expand=True)
        tb = tk.Frame(card, bg=C["card"])
        tb.pack(fill="x", padx=14, pady=(6, 8))
        ttk.Button(tb, text="Add files", command=self.merge_add).pack(side="left")
        ttk.Button(tb, text="Move up", style="Tool.TButton", command=lambda: self.merge_move(-1)).pack(side="left", padx=(14, 4))
        ttk.Button(tb, text="Move down", style="Tool.TButton", command=lambda: self.merge_move(1)).pack(side="left", padx=4)
        ttk.Button(tb, text="Remove", style="Tool.TButton", command=self.merge_remove).pack(side="left", padx=4)
        ttk.Button(tb, text="Clear", style="Tool.TButton", command=lambda: self.merge_tree.delete(*self.merge_tree.get_children())).pack(side="left", padx=4)
        ttk.Button(tb, text="Merge PDFs", style="Accent.TButton", command=self.merge_run).pack(side="right")
        table = tk.Frame(card, bg=C["card"])
        table.pack(fill="both", expand=True, padx=ui_px(14), pady=(0, ui_px(14)))
        self.merge_tree = ttk.Treeview(table, columns=("name", "pages", "path"), show="headings", selectmode="extended")
        self.merge_tree.heading("name", text="File name")
        self.merge_tree.heading("pages", text="Pages")
        self.merge_tree.heading("path", text="Path")
        self.merge_tree.column("name", width=ui_px(230), minwidth=ui_px(120))
        self.merge_tree.column("pages", width=ui_px(60), anchor="center", stretch=False)
        self.merge_tree.column("path", width=ui_px(400), minwidth=ui_px(180))
        vbar = ttk.Scrollbar(table, orient="vertical", command=self.merge_tree.yview)
        hbar = ttk.Scrollbar(table, orient="horizontal", command=self.merge_tree.xview)
        vbar.pack(side="right", fill="y")
        hbar.pack(side="bottom", fill="x")
        self.merge_tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.merge_tree.pack(side="left", fill="both", expand=True)

    def merge_add(self):
        for f in filedialog.askopenfilenames(title="Choose PDF", filetypes=[("PDF files", "*.pdf")]):
            try:
                with fitz.open(f) as d:
                    n = "Encrypted" if d.needs_pass else d.page_count
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
            messagebox.showinfo("Notice", "Add at least two PDF files.")
            return
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], initialfile="merged.pdf")
        if not out:
            return
        try:
            self.busy()
            res = fitz.open()
            for f in files:
                with fitz.open(f) as src:
                    if not self.ask_password(src, f):
                        raise ValueError(f"Cannot open encrypted PDF: {os.path.basename(f)}")
                    res.insert_pdf(src)
            res.save(out, garbage=3, deflate=True)
            res.close()
            self.busy(False)
            self.set_status(f"Merged {len(files)} files: {out}")
            messagebox.showinfo("Success", f"Merged {len(files)} files:\n{out}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("Merge failed", str(ex))

    # ============================================================
    #  3. Split PDF
    # ============================================================
    def build_split(self):
        page = self.page_frame("split")
        card = make_card(page, "Choose file")
        card.pack(fill="x")
        self.split_var = tk.StringVar()
        self.split_info = tk.StringVar(value="")
        self.file_row(card, self.split_var, lambda: self.pick_pdf(self.split_var, self.split_loaded))
        tk.Label(card, textvariable=self.split_info, bg=C["card"], fg=C["sub"], font=UI["caption"]).pack(anchor="w", padx=16, pady=(0, 10))

        c2 = make_card(page, "Page settings")
        c2.pack(fill="x", pady=(12, 0))
        wrapped_label(c2, text="Page range, e.g. 1-3,5,8-. An open end includes the last page."
                      ).pack(fill="x", padx=ui_px(16))
        self.split_range = ttk.Entry(c2)
        self.split_range.pack(fill="x", padx=16, pady=(4, 10))
        self.split_range.insert(0, "1-")
        self.split_mode = tk.StringVar(value="one")
        r = tk.Frame(c2, bg=C["card"])
        r.pack(anchor="w", padx=12, pady=(0, 14))
        ttk.Radiobutton(r, text="Extract to one PDF", value="one", variable=self.split_mode).pack(side="left", padx=4)
        ttk.Radiobutton(r, text="Save each page separately", value="each", variable=self.split_mode).pack(side="left", padx=14)
        ttk.Button(page, text="Split PDF", style="Accent.TButton", command=self.split_run).pack(anchor="e", pady=14)

    def split_loaded(self, p):
        try:
            with fitz.open(p) as d:
                self.split_info.set(f"{d.page_count} pages" if not d.needs_pass else "Encrypted PDF. Unlock it in Security first.")
        except Exception as ex:
            self.split_info.set(str(ex))

    def split_run(self):
        f = self.split_var.get()
        if not f:
            messagebox.showinfo("Notice", "Choose a PDF file first.")
            return
        try:
            src = fitz.open(f)
            pages = parse_ranges(self.split_range.get(), src.page_count)
            base = os.path.splitext(os.path.basename(f))[0]
            self.busy()
            if self.split_mode.get() == "one":
                self.busy(False)
                out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], initialfile=f"{base}_extract.pdf")
                if not out:
                    return
                self.busy()
                src.select(pages)
                src.save(out, garbage=3, deflate=True)
                msg = out
            else:
                self.busy(False)
                folder = filedialog.askdirectory(title="Choose output folder")
                if not folder:
                    return
                self.busy()
                for p in pages:
                    d = fitz.open()
                    d.insert_pdf(src, from_page=p, to_page=p)
                    d.save(os.path.join(folder, f"{base}_page{p + 1}.pdf"))
                    d.close()
                msg = f"{folder} ({len(pages)} files)"
            src.close()
            self.busy(False)
            self.set_status("Split complete")
            messagebox.showinfo("Success", f"Split complete:\n{msg}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("Split failed", str(ex))

    # ============================================================
    #  4. Watermark
    # ============================================================
    def build_watermark(self):
        page = self.page_frame("wm")
        self.wm_doc = None
        self.wm_loaded_path = None
        self.wm_page_no = 0
        self.wm_tk_image = None
        self.wm_preview_job = None
        self.wm_kit = FontKit()
        self.root.bind("<Destroy>", self.wm_cleanup, add="+")

        card = make_card(page, "PDF files")
        card.pack(fill="x")
        self.wm_var = tk.StringVar()
        self.file_row(card, self.wm_var, lambda: self.pick_pdf(self.wm_var, self.wm_load_pdf))
        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True, pady=(ui_px(12), 0))
        body.columnconfigure(0, minsize=ui_px(282))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        settings = make_card(body, "Watermark settings")
        settings.grid(row=0, column=0, sticky="nsew", padx=(0, ui_px(12)))
        actions = tk.Frame(settings, bg=C["card"])
        actions.pack(side="bottom", fill="x", padx=ui_px(16), pady=(ui_px(10), ui_px(14)))
        ttk.Button(actions, text="Save watermarked PDF", style="Accent.TButton",
                   command=self.wm_run).pack(fill="x")
        wrapped_label(actions, text="Saving adds the watermark to every page."
                      ).pack(fill="x", pady=(ui_px(6), 0))
        content = scrollable_area(settings)
        form = tk.Frame(content, bg=C["card"])
        form.pack(fill="x", padx=ui_px(16), pady=(ui_px(6), ui_px(12)))

        tk.Label(form, text="Watermark text", bg=C["card"], fg=C["text"],
                 font=UI["body"]).pack(anchor="w", pady=(0, ui_px(5)))
        self.wm_text_var = tk.StringVar(value="CONFIDENTIAL")
        self.wm_text = ttk.Entry(form, textvariable=self.wm_text_var, width=22)
        self.wm_text.pack(fill="x")

        numbers = tk.Frame(form, bg=C["card"])
        numbers.pack(fill="x", pady=(ui_px(14), ui_px(12)))
        numbers.columnconfigure((0, 1), weight=1, uniform="wm_numbers")
        self.wm_size = tk.IntVar(value=48)
        self.wm_angle = tk.IntVar(value=45)
        for col, (title, var, low, high) in enumerate((
                ("Font size (pt)", self.wm_size, 10, 200),
                ("Angle (°)", self.wm_angle, 0, 90))):
            field = tk.Frame(numbers, bg=C["card"])
            field.grid(row=0, column=col, sticky="ew", padx=(0, ui_px(10)) if col == 0 else 0)
            tk.Label(field, text=title, bg=C["card"], fg=C["text"],
                     font=UI["body"]).pack(anchor="w", pady=(0, ui_px(5)))
            ttk.Spinbox(field, from_=low, to=high, textvariable=var, width=6).pack(fill="x")

        opacity_head = tk.Frame(form, bg=C["card"])
        opacity_head.pack(fill="x")
        tk.Label(opacity_head, text="Opacity", bg=C["card"], fg=C["text"],
                 font=UI["body"]).pack(side="left")
        self.wm_op = tk.DoubleVar(value=0.25)
        self.wm_op_text = tk.StringVar(value="25%")
        tk.Label(opacity_head, textvariable=self.wm_op_text, bg=C["card"], fg=C["accent"],
                 font=UI["body"]).pack(side="right")
        ttk.Scale(form, from_=0.05, to=1.0, variable=self.wm_op).pack(fill="x", pady=(ui_px(6), ui_px(12)))
        tk.Label(form, text="Color", bg=C["card"], fg=C["text"],
                 font=UI["body"]).pack(anchor="w", pady=(0, ui_px(5)))
        self.wm_color = tk.StringVar(value="Gray")
        ttk.Combobox(form, textvariable=self.wm_color, values=["Gray", "Red", "Blue", "Black"],
                     state="readonly", width=10).pack(fill="x")
        self.wm_tile = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Tile across page", variable=self.wm_tile).pack(anchor="w", pady=(ui_px(14), 0))

        preview = make_card(body, "Preview")
        preview.grid(row=0, column=1, sticky="nsew")
        toolbar = tk.Frame(preview, bg=C["card"])
        toolbar.pack(fill="x", padx=ui_px(12), pady=(ui_px(6), ui_px(4)))
        self.wm_prev = ttk.Button(toolbar, text="Previous", style="Tool.TButton",
                                  state="disabled", command=lambda: self.wm_goto(self.wm_page_no - 1))
        self.wm_prev.pack(side="left")
        self.wm_page_var = tk.StringVar(value="1")
        self.wm_page_entry = ttk.Entry(toolbar, textvariable=self.wm_page_var, width=4,
                                      justify="center", state="disabled")
        self.wm_page_entry.pack(side="left", padx=(ui_px(8), 2))
        self.wm_page_entry.bind("<Return>", self.wm_page_from_entry)
        self.wm_total = tk.Label(toolbar, text="/ 0", bg=C["card"], fg=C["sub"], font=UI["body"])
        self.wm_total.pack(side="left", padx=(0, ui_px(8)))
        self.wm_next = ttk.Button(toolbar, text="Next", style="Tool.TButton",
                                  state="disabled", command=lambda: self.wm_goto(self.wm_page_no + 1))
        self.wm_next.pack(side="left")
        ttk.Button(toolbar, text="Refresh", style="Tool.TButton",
                   command=lambda: self.wm_schedule_preview(0)).pack(side="right")
        self.wm_show = tk.BooleanVar(value=True)
        ttk.Checkbutton(preview, text="Show watermark (uncheck to compare original)",
                        variable=self.wm_show).pack(anchor="w", padx=ui_px(12), pady=(ui_px(4), ui_px(8)))
        self.wm_preview_info = tk.StringVar(value="Choose a PDF file to preview the watermark.")
        wrapped_label(preview, textvariable=self.wm_preview_info
                      ).pack(side="bottom", fill="x", padx=ui_px(12), pady=ui_px(8))
        self.wm_canvas = tk.Canvas(preview, bg=C["canvas"], highlightthickness=0, width=1, height=1)
        self.wm_canvas.pack(fill="both", expand=True, padx=ui_px(12))
        self.wm_canvas.bind("<Configure>", lambda e: self.wm_schedule_preview())

        self.wm_op.trace_add("write", self.wm_update_opacity)
        for var in (self.wm_text_var, self.wm_size, self.wm_angle, self.wm_op,
                    self.wm_color, self.wm_tile, self.wm_show):
            var.trace_add("write", lambda *args: self.wm_schedule_preview())

    def wm_update_opacity(self, *args):
        try:
            self.wm_op_text.set(f"{self.wm_op.get():.0%}")
        except (ValueError, tk.TclError):
            self.wm_op_text.set("—")

    def wm_cleanup(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self.wm_preview_job is not None:
            self.root.after_cancel(self.wm_preview_job)
            self.wm_preview_job = None
        if self.wm_doc is not None:
            self.wm_doc.close()
            self.wm_doc = None
        self.wm_kit.close()

    def wm_load_pdf(self, path):
        self.wm_cleanup()
        self.wm_loaded_path = None
        self.wm_page_no = 0
        self.wm_kit = FontKit()
        self.wm_update_navigation()
        self.wm_placeholder("Loading PDF...")
        doc = None
        try:
            # Keep a snapshot matching the preview without locking the source file.
            with open(path, "rb") as source:
                doc = fitz.open(stream=source.read(), filetype="pdf")
            if not self.ask_password(doc, path):
                self.wm_placeholder("Incorrect password or canceled. Choose the file again.")
                return False
            if not doc.page_count:
                raise ValueError("The PDF has no pages to preview.")
            self.wm_doc, doc = doc, None
            self.wm_loaded_path = path
            self.wm_update_navigation()
            self.wm_schedule_preview(0)
            return True
        except Exception as ex:
            self.wm_placeholder(f"Cannot open PDF: {ex}")
            messagebox.showerror("Cannot open PDF", str(ex))
            return False
        finally:
            if doc is not None:
                doc.close()

    def wm_update_navigation(self):
        n = self.wm_doc.page_count if self.wm_doc is not None else 0
        self.wm_page_var.set(str(self.wm_page_no + 1))
        self.wm_total.config(text=f"/ {n}")
        self.wm_page_entry.config(state="normal" if n else "disabled")
        self.wm_prev.config(state="normal" if n and self.wm_page_no > 0 else "disabled")
        self.wm_next.config(state="normal" if n and self.wm_page_no < n - 1 else "disabled")

    def wm_goto(self, n):
        if self.wm_doc is None:
            return
        self.wm_page_no = max(0, min(n, self.wm_doc.page_count - 1))
        self.wm_update_navigation()
        self.wm_schedule_preview(0)

    def wm_page_from_entry(self, event=None):
        try:
            self.wm_goto(int(self.wm_page_var.get()) - 1)
        except ValueError:
            self.wm_update_navigation()
        return "break"

    def wm_schedule_preview(self, delay=250):
        # Debounce typing, slider movements, and resizes to avoid redundant rendering.
        if self.wm_preview_job is not None:
            self.root.after_cancel(self.wm_preview_job)
            self.wm_preview_job = None
        if self.cur == "wm":
            self.wm_preview_job = self.root.after(delay, self.wm_render_preview)

    def wm_options(self, require_text=False):
        text = self.wm_text.get().strip()
        if require_text and not text:
            raise ValueError("Enter watermark text.")
        try:
            size, angle, opacity = self.wm_size.get(), self.wm_angle.get(), float(self.wm_op.get())
        except (ValueError, tk.TclError):
            raise ValueError("Enter a valid font size, angle, and opacity.") from None
        if not 10 <= size <= 200:
            raise ValueError("Font size must be between 10 and 200 pt.")
        if not 0 <= angle <= 90:
            raise ValueError("Angle must be between 0 and 90 degrees.")
        if not 0.05 <= opacity <= 1:
            raise ValueError("Opacity must be between 5% and 100%.")
        colors = {"Gray": (0.45, 0.45, 0.45), "Red": (0.85, 0.1, 0.1),
                  "Blue": (0.1, 0.3, 0.85), "Black": (0, 0, 0)}
        return dict(text=text, size=size, opacity=opacity, angle=angle,
                    color=colors[self.wm_color.get()], tile=self.wm_tile.get())

    def wm_placeholder(self, message):
        self.wm_tk_image = None
        self.wm_canvas.delete("all")
        self.wm_canvas.create_text(max(self.wm_canvas.winfo_width(), 100) / 2,
                                   max(self.wm_canvas.winfo_height(), 100) / 2,
                                   text=message, fill=C["sub"], font=(FONT, 11),
                                   width=max(self.wm_canvas.winfo_width() - 32, 100),
                                   justify="center")
        self.wm_preview_info.set(message)

    def wm_render_preview(self):
        self.wm_preview_job = None
        if self.cur != "wm":
            return
        if self.wm_doc is None:
            self.wm_placeholder("Choose a PDF file to preview the watermark.")
            return
        try:
            options = self.wm_options()
            show = self.wm_show.get() and bool(options["text"])
            # Start from the original page so settings never accumulate watermarks.
            with fitz.open() as preview:
                preview.insert_pdf(self.wm_doc, from_page=self.wm_page_no, to_page=self.wm_page_no)
                pg = preview[0]
                if show:
                    add_watermark(pg, self.wm_kit, **options)
                cw, ch = self.wm_canvas.winfo_width(), self.wm_canvas.winfo_height()
                margin = ui_px(16)
                if cw < margin * 2 + 8 or ch < margin * 2 + 8:
                    return  # Wait for a Configure event after the canvas is laid out.
                z = min((cw - margin * 2) / pg.rect.width, (ch - margin * 2) / pg.rect.height, 2.0 * UI_SCALE)
                pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csRGB, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            self.wm_tk_image = ImageTk.PhotoImage(img, master=self.root)
            self.wm_canvas.delete("all")
            x, y = (cw - pix.width) / 2, (ch - pix.height) / 2
            self.wm_canvas.create_rectangle(x + 4, y + 4, x + pix.width + 4, y + pix.height + 4,
                                            fill="#B8BFCB", outline="")
            self.wm_canvas.create_image(x, y, anchor="nw", image=self.wm_tk_image)
            kind = "Watermarked" if show else "Original"
            self.wm_preview_info.set(f"Page {self.wm_page_no + 1} / {self.wm_doc.page_count} · {kind}")
        except Exception as ex:
            self.wm_placeholder(f"Preview unavailable: {ex}")

    def wm_run(self):
        f = self.wm_var.get()
        if not f:
            messagebox.showinfo("Notice", "Choose a PDF file first.")
            return
        if self.wm_doc is None or self.wm_loaded_path != f:
            if not self.wm_load_pdf(f):
                return
        try:
            options = self.wm_options(require_text=True)
        except ValueError as ex:
            messagebox.showinfo("Notice", str(ex))
            return
        base = os.path.splitext(os.path.basename(f))[0]
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], initialfile=f"{base}_watermark.pdf")
        if not out:
            return
        try:
            self.busy()
            # Keep the source read-only; save and preview share fonts, parameters, and drawing.
            with fitz.open(stream=self.wm_doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE), filetype="pdf") as doc:
                for pg in doc:
                    add_watermark(pg, self.wm_kit, **options)
                doc.save(out, garbage=3, deflate=True)
            self.set_status(f"Watermarked PDF saved: {out}")
            messagebox.showinfo("Success", f"Watermarked PDF saved:\n{out}")
        except Exception as ex:
            messagebox.showerror("Failed", str(ex))
        finally:
            self.busy(False)

    # ============================================================
    #  5. Export pages as images
    # ============================================================
    def build_images(self):
        page = self.page_frame("img")
        card = make_card(page, "Choose file")
        card.pack(fill="x")
        self.img_var = tk.StringVar()
        self.file_row(card, self.img_var, lambda: self.pick_pdf(self.img_var))
        c2 = make_card(page, "Image export settings")
        c2.pack(fill="x", pady=(12, 0))
        wrapped_label(c2, text="Each file contains a complete page, including its text, images, and layout. Embedded images are not extracted separately."
                      ).pack(fill="x", padx=ui_px(16), pady=(6, 0))
        g = tk.Frame(c2, bg=C["card"])
        g.pack(fill="x", padx=16, pady=(6, 14))
        tk.Label(g, text="Resolution (DPI)", bg=C["card"], fg=C["sub"]).grid(row=0, column=0, sticky="w", pady=6, padx=(0, 16))
        self.img_dpi = tk.StringVar(value="200")
        ttk.Combobox(g, textvariable=self.img_dpi, values=["72", "150", "200", "300", "400"], width=8, state="readonly").grid(row=0, column=1, sticky="w")
        tk.Label(g, text="Format", bg=C["card"], fg=C["sub"]).grid(row=1, column=0, sticky="w", pady=6)
        self.img_fmt = tk.StringVar(value="PNG")
        ttk.Combobox(g, textvariable=self.img_fmt, values=["PNG", "JPG"], width=8, state="readonly").grid(row=1, column=1, sticky="w")
        self.img_prog = ttk.Progressbar(page, mode="determinate")
        self.img_prog.pack(fill="x", pady=(16, 0))
        ttk.Button(page, text="Export all pages as images", style="Accent.TButton", command=self.img_run).pack(anchor="e", pady=14)

    def img_run(self):
        f = self.img_var.get()
        if not f:
            messagebox.showinfo("Notice", "Choose a PDF file first.")
            return
        folder = filedialog.askdirectory(title="Choose output folder")
        if not folder:
            return
        try:
            doc = fitz.open(f)
            if not self.ask_password(doc, f):
                raise ValueError("Cannot open encrypted PDF.")
            base = os.path.splitext(os.path.basename(f))[0]
            z = int(self.img_dpi.get()) / 72.0
            ext = "png" if self.img_fmt.get() == "PNG" else "jpg"
            self.img_prog.config(maximum=doc.page_count, value=0)
            self.busy()
            for i, pg in enumerate(doc):
                pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False).save(os.path.join(folder, f"{base}_page{i + 1}.{ext}"))
                self.img_prog.config(value=i + 1)
                self.set_status(f"Exporting page {i + 1}/{doc.page_count}")
            n = doc.page_count
            doc.close()
            self.busy(False)
            self.set_status(f"Exported {n} pages as images.")
            messagebox.showinfo("Success", f"Exported {n} pages as {n} images (one per page):\n{folder}")
        except Exception as ex:
            self.busy(False)
            messagebox.showerror("Image export failed", str(ex))

    # ============================================================
    #  6. Security
    # ============================================================
    def build_security(self):
        page = self.page_frame("sec")
        card = make_card(page, "Choose file")
        card.pack(fill="x")
        self.sec_var = tk.StringVar()
        self.file_row(card, self.sec_var, lambda: self.pick_pdf(self.sec_var))
        c2 = make_card(page, "Password")
        c2.pack(fill="x", pady=(12, 0))
        self.pwd = ttk.Entry(c2, show="●")
        self.pwd.pack(fill="x", padx=16, pady=(6, 4))
        wrapped_label(c2, text="Encryption uses AES-256. Unlocking requires the current password."
                      ).pack(fill="x", padx=ui_px(16), pady=(0, ui_px(14)))
        r = tk.Frame(page, bg=C["bg"])
        r.pack(anchor="e", pady=14)
        ttk.Button(r, text="Unlock PDF", command=self.sec_unlock).pack(side="left", padx=8)
        ttk.Button(r, text="Encrypt PDF", style="Accent.TButton", command=self.sec_lock).pack(side="left")

    def sec_lock(self):
        f, pw = self.sec_var.get(), self.pwd.get()
        if not f or not pw:
            messagebox.showinfo("Notice", "Choose a PDF file and enter a password.")
            return
        base = os.path.splitext(os.path.basename(f))[0]
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], initialfile=f"{base}_locked.pdf")
        if not out:
            return
        try:
            doc = fitz.open(f)
            if not self.ask_password(doc, f):
                raise ValueError("Cannot open this PDF.")
            doc.save(out, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=pw, owner_pw=pw, garbage=3, deflate=True)
            doc.close()
            self.set_status(f"Encrypted PDF saved: {out}")
            messagebox.showinfo("Success", f"Encrypted PDF saved:\n{out}")
        except Exception as ex:
            messagebox.showerror("Failed", str(ex))

    def sec_unlock(self):
        f, pw = self.sec_var.get(), self.pwd.get()
        if not f:
            messagebox.showinfo("Notice", "Choose a PDF file first.")
            return
        base = os.path.splitext(os.path.basename(f))[0]
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], initialfile=f"{base}_unlocked.pdf")
        if not out:
            return
        try:
            doc = fitz.open(f)
            if doc.needs_pass and not doc.authenticate(pw):
                raise ValueError("Incorrect password.")
            doc.save(out, encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
            doc.close()
            self.set_status(f"Unlocked PDF saved: {out}")
            messagebox.showinfo("Success", f"Unlocked PDF saved:\n{out}")
        except Exception as ex:
            messagebox.showerror("Failed", str(ex))


def main():
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Enable high-DPI rendering on Windows.
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
