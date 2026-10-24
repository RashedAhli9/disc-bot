"""Image cards for the bot (Pillow). Posted as normal attachments, so they show for everyone
no matter their Discord embed settings.

Everything is drawn at 2x and scaled down so edges are smooth. Fonts live in assets/fonts,
medal icons in emoji_assets (the same files uploaded as bot emojis)."""
import functools
import io
import os
import unicodedata

from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(_HERE, "assets", "fonts")
ICON_DIR = os.path.join(_HERE, "emoji_assets")

S = 2                      # supersampling factor
W = 980                    # card width (1x pixels)
PAD = 32

BG = (14, 17, 23)
PANEL = (23, 27, 38)
PANEL2 = (30, 35, 50)
TRACK = (44, 50, 70)
TEXT = (232, 236, 244)
MUTED = (139, 147, 167)
GREEN = (61, 220, 132)
YELLOW = (245, 197, 66)
RED = (255, 92, 92)
BLUE = (90, 169, 255)
PURPLE = (181, 131, 255)
ORANGE = (255, 150, 70)
TEAL = (64, 214, 214)

_font_cache = {}
_icon_cache = {}


def _mpl_font_dir():
    try:
        import matplotlib
        return os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    except Exception:
        return ""


_MPL = _mpl_font_dir()

# Per weight: primary font first, then fallbacks that cover more of Unicode (symbols, math, Greek, Cyrillic...)
_CHAINS = {
    "r": [os.path.join(FONT_DIR, "Inter-Regular.otf"), os.path.join(_MPL, "DejaVuSans.ttf"),
          os.path.join(_MPL, "STIXGeneral.ttf")],
    "s": [os.path.join(FONT_DIR, "Inter-SemiBold.otf"), os.path.join(_MPL, "DejaVuSans-Bold.ttf"),
          os.path.join(_MPL, "STIXGeneralBol.ttf")],
    "b": [os.path.join(FONT_DIR, "Inter-Bold.otf"), os.path.join(_MPL, "DejaVuSans-Bold.ttf"),
          os.path.join(_MPL, "STIXGeneralBol.ttf")],
}


@functools.lru_cache(maxsize=None)
def _cmap(path):
    try:
        from fontTools.ttLib import TTFont
        return frozenset(TTFont(path, lazy=True).getBestCmap().keys())
    except Exception:
        return frozenset()


def _font_at(path, size):
    key = (path, size)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(path, size * S)
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _font(weight, size):
    return _font_at(_CHAINS[weight][0], size)


def _runs(text, weight):
    """Clean a string and split it into [(text, font_path)] runs, using the first font in the chain that has
    each character. Characters no font has (or invisible/private-use ones) are dropped instead of drawn as boxes."""
    text = unicodedata.normalize("NFKC", str(text))   # fancy styled letters -> plain letters where possible
    chain = _CHAINS[weight]
    out = []
    for ch in text:
        if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") or ch == "\ufe0f":
            continue
        if ch == " ":
            path = out[-1][1] if out else chain[0]
        else:
            path = next((fp for fp in chain if ord(ch) in _cmap(fp)), None)
            if path is None:
                continue
        if out and out[-1][1] == path:
            out[-1] = (out[-1][0] + ch, path)
        else:
            out.append((ch, path))
    if out:
        out[0] = (out[0][0].lstrip(), out[0][1])
        out[-1] = (out[-1][0].rstrip(), out[-1][1])
        out = [r for r in out if r[0]]
    return out


def _icon(name, size):
    key = (name, size)
    if key not in _icon_cache:
        try:
            im = Image.open(os.path.join(ICON_DIR, name + ".png")).convert("RGBA")
            _icon_cache[key] = im.resize((size * S, size * S), Image.LANCZOS)
        except Exception:
            _icon_cache[key] = None
    return _icon_cache[key]


class _Canvas:
    def __init__(self, height):
        self.im = Image.new("RGB", (W * S, height * S), BG)
        self.d = ImageDraw.Draw(self.im)

    # --- primitives (all coordinates in 1x pixels) ---
    def rect(self, x, y, w, h, fill, r=14, outline=None):
        self.d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=r * S, fill=fill,
                                 outline=outline, width=S if outline else 0)

    def text(self, x, y, s, weight="r", size=16, fill=TEXT, anchor="la"):
        runs = _runs(s, weight)
        if not runs:
            return
        if len(runs) == 1:
            self.d.text((x * S, y * S), runs[0][0], font=_font_at(runs[0][1], size), fill=fill, anchor=anchor)
            return
        # mixed fonts: lay the runs out left to right on a shared baseline
        total = sum(self.d.textlength(t, font=_font_at(fp, size)) for t, fp in runs)
        h, v = anchor[0], anchor[1]
        px = x * S
        px -= total if h == "r" else total / 2 if h == "m" else 0
        asc, desc = _font(weight, size).getmetrics()
        base = y * S + (asc if v == "a" else (asc - desc) / 2 if v == "m" else 0)
        for t, fp in runs:
            f = _font_at(fp, size)
            self.d.text((px, base), t, font=f, fill=fill, anchor="ls")
            px += self.d.textlength(t, font=f)

    def text_w(self, s, weight="r", size=16):
        return sum(self.d.textlength(t, font=_font_at(fp, size)) for t, fp in _runs(s, weight)) / S

    def bar(self, x, y, w, h, frac, color):
        self.rect(x, y, w, h, TRACK, r=h // 2)
        frac = max(0.0, min(1.0, frac))
        if frac > 0:
            self.rect(x, y, max(h, w * frac), h, color, r=h // 2)

    def rank_pill(self, right, y, rank):
        """Right-aligned rank badge ending at x=right. Medal icon for top 3, '#N' pill otherwise."""
        label = f"#{rank}"
        fw = self.text_w(label, "b", 15)
        medal = {1: "medal_1", 2: "medal_2", 3: "medal_3"}.get(rank)
        ic = _icon(medal, 22) if medal else None
        w = fw + 22 + (26 if ic else 0)
        x = right - w
        self.rect(x, y, w, 28, PANEL2 if not ic else (52, 46, 28) if rank == 1 else PANEL2, r=14)
        tx = x + 11
        if ic:
            self.im.paste(ic, (int((x + 8) * S), int((y + 3) * S)), ic)
            tx = x + 34
        self.text(tx, y + 14, label, "b", 15, TEXT if not ic else YELLOW if rank == 1 else TEXT, anchor="lm")
        return w

    def tile(self, x, y, w, h, label, value, accent, sub=None, rank=None, value_size=34, sub2=None, sub2_color=MUTED):
        self.rect(x, y, w, h, PANEL)
        self.rect(x, y + 16, 5, h - 32, accent, r=3)
        self.text(x + 24, y + 18, label.upper(), "s", 13, MUTED)
        self.text(x + 24, y + 40, value, "b", value_size, TEXT)
        if sub:
            self.text(x + 24, y + h - (52 if sub2 else 30), sub, "r", 14, accent)
        if sub2:
            self.text(x + 24, y + h - 30, sub2, "s", 14, sub2_color)
        if rank:
            self.rank_pill(x + w - 16, y + 14, rank)

    def finish(self, height):
        im = self.im.crop((0, 0, W * S, height * S))
        return im.resize((W, height), Image.LANCZOS)


def _fmt(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def render_progress_card(d):
    """d keys (all optional unless noted):
    tag, name(req), season(req), start, end, account_id, single_day
    power(int), power_gain(int), power_rank, merits(str), merits_pct(str), merits_rank
    kills, deads, healed (str), kills_rank, deads_rank, healed_rank
    deads_req: {deaths, required, level('good'|'mid'|'bad'), done}
    troops: [(label, int, rank)], others: [(label, int, rank|None)]
    rss: [(label, str)], rss_total(int), mana_est(int)
    coins(str), pets(str), decos(str)
    notes: [str]
    Returns BytesIO PNG."""
    c = _Canvas(1600)
    y = PAD

    # ---------- header ----------
    c.rect(PAD, y, W - 2 * PAD, 96, PANEL)
    title = f"{d.get('tag') or ''} {d.get('name') or 'Unknown'}".strip()
    size = 32
    while c.text_w(title, "b", size) > W - 2 * PAD - 300 and size > 20:
        size -= 2
    c.text(PAD + 28, y + 24, title, "b", size, TEXT)
    c.text(PAD + 28, y + 66, f"Season {d.get('season')}   ·   {d.get('start')} → {d.get('end')}", "r", 15, MUTED)
    c.text(W - PAD - 28, y + 28, "PROGRESS REPORT", "s", 13, MUTED, anchor="ra")
    if d.get("account_id"):
        c.text(W - PAD - 28, y + 52, f"ID {d['account_id']}", "s", 16, BLUE, anchor="ra")
    y += 96 + 16

    if d.get("single_day"):
        c.rect(PAD, y, W - 2 * PAD, 40, (58, 46, 20))
        c.text(PAD + 20, y + 20, "Only 1 day of data available, showing absolute values", "s", 15, YELLOW, anchor="lm")
        y += 40 + 16

    # ---------- hero tiles: power + merits ----------
    half = (W - 2 * PAD - 16) // 2
    th = 140 if (d.get('power_now') and d.get('power')) else 124
    if d.get("power") or d.get("power_gain"):
        pv = _fmt(d["power"]) if d.get("power") else f"+{_fmt(d.get('power_gain'))}"
        if d.get("power") and d.get("power_gain"):
            sub = f"+{_fmt(d['power_gain'])} this season"
        elif d.get("power"):
            sub = "no new peak this season"
        else:
            sub = None
        sub2, sub2c = None, MUTED
        now, peak = d.get("power_now"), d.get("power")
        if now and peak:
            diff = now - peak
            when = f" · as of {d['power_now_date']}" if d.get("power_now_date") else ""
            sub2 = f"Now {_fmt(now)} ({'+' if diff >= 0 else '−'}{_fmt(abs(diff))} vs peak){when}"
            sub2c = RED if diff < 0 else GREEN
        c.tile(PAD, y, half, th, "Power", pv, GREEN, sub, d.get("power_rank"), sub2=sub2, sub2_color=sub2c)
    if d.get("merits"):
        sub = f"{d['merits_pct']} of power" if d.get("merits_pct") else None
        c.tile(PAD + half + 16, y, half, th, "Merits", d["merits"].lstrip("+"), RED, sub, d.get("merits_rank"))
    y += th + 16

    # ---------- combat row ----------
    combat = []
    if d.get("kills"):
        combat.append(("Kills", d["kills"], ORANGE, d.get("kills_rank")))
    if d.get("deads"):
        combat.append(("Deads", d["deads"], RED, d.get("deads_rank")))
    if d.get("healed"):
        combat.append(("Healed", d["healed"], PURPLE, d.get("healed_rank")))
    if combat:
        n = len(combat)
        tw = (W - 2 * PAD - 16 * (n - 1)) // n
        for i, (lab, val, col, rk) in enumerate(combat):
            c.tile(PAD + i * (tw + 16), y, tw, 104, lab, str(val).lstrip("+"), col, None, rk, value_size=30)
        y += 104 + 16

    # ---------- deads requirement ----------
    dr = d.get("deads_req")
    if dr:
        col = {"good": GREEN, "mid": YELLOW, "bad": RED}.get(dr.get("level"), RED)
        ph = 112
        c.rect(PAD, y, W - 2 * PAD, ph, PANEL)
        c.text(PAD + 28, y + 20, "DEADS REQUIREMENT", "s", 13, MUTED)
        if dr.get("done"):
            c.text(W - PAD - 28, y + 18, "DONE", "b", 18, GREEN, anchor="ra")
        else:
            c.text(W - PAD - 28, y + 18, f"{_m(dr['required'] - dr['deaths'])} to go", "b", 18, col, anchor="ra")
        c.text(PAD + 28, y + 42, f"{_m(dr['deaths'])} / {_m(dr['required'])}", "b", 26, TEXT)
        pct = dr["deaths"] / dr["required"] if dr["required"] else 0
        c.bar(PAD + 28, y + 84, W - 2 * PAD - 56, 14, pct, col)
        y += ph + 16

    # ---------- troop merits ----------
    troops = [t for t in (d.get("troops") or []) if t[1]]
    others = d.get("others") or []
    if troops or others:
        rows = max(len(troops), 1) + (len(others) and 1 or 0)
        hh = 60 + len(troops) * 40 + (36 if others else 0)
        c.rect(PAD, y, W - 2 * PAD, hh, PANEL)
        c.text(PAD + 28, y + 22, "TROOP MERITS", "s", 13, MUTED)
        top = max([t[1] for t in troops] or [1])
        colors = {"Infantry": BLUE, "Cavalry": ORANGE, "Archer": GREEN, "Magic": PURPLE}
        ry = y + 54
        for lab, val, rk in troops:
            col = colors.get(lab, TEAL)
            c.text(PAD + 28, ry + 10, lab, "s", 16, TEXT, anchor="lm")
            c.bar(PAD + 150, ry + 3, 420, 14, val / top, col)
            c.text(PAD + 590, ry + 10, _fmt(val), "b", 17, TEXT, anchor="lm")
            if rk:
                c.rank_pill(W - PAD - 24, ry - 4, rk)
            ry += 40
        if others:
            ox = PAD + 28
            for lab, val, rk in others:
                txt = f"{lab}  {_fmt(val)}" + (f"  #{rk}" if rk else "")
                c.text(ox, ry + 14, txt, "s", 15, MUTED, anchor="lm")
                ox += c.text_w(txt, "s", 15) + 40
        y += hh + 16

    # ---------- resources + achievements ----------
    chips = []
    for lab, val in d.get("rss") or []:
        chips.append((lab, val))
    if chips or d.get("mana_est"):
        hh = 96 if d.get("mana_est") else 72
        c.rect(PAD, y, W - 2 * PAD, hh, PANEL)
        c.text(PAD + 28, y + 18, "RESOURCES GATHERED", "s", 13, MUTED)
        cx = PAD + 28
        for lab, val in chips:
            c.text(cx, y + 44, lab, "r", 14, MUTED)
            lw = c.text_w(lab, "r", 14)
            c.text(cx + lw + 8, y + 44, str(val).lstrip("+"), "b", 16, TEXT)
            cx += lw + 8 + c.text_w(str(val).lstrip("+"), "b", 16) + 32
        if d.get("rss_total"):
            c.text(W - PAD - 28, y + 18, f"Total {_fmt(d['rss_total'])}", "b", 15, GREEN, anchor="ra")
        if d.get("mana_est"):
            c.text(PAD + 28, y + 72, f"Mana spent (est., assuming T5)  +{_fmt(d['mana_est'])}", "s", 14, PURPLE)
        y += hh + 16

    ach = [("Coins spent", d.get("coins")), ("Max pets", d.get("pets")), ("Max decorations", d.get("decos"))]
    ach = [(a, b) for a, b in ach if b not in (None, "")]
    if ach:
        c.rect(PAD, y, W - 2 * PAD, 72, PANEL)
        c.text(PAD + 28, y + 18, "ACHIEVEMENTS", "s", 13, MUTED)
        cx = PAD + 28
        for lab, val in ach:
            c.text(cx, y + 44, lab, "r", 14, MUTED)
            lw = c.text_w(lab, "r", 14)
            c.text(cx + lw + 8, y + 44, val, "b", 16, TEXT)
            cx += lw + 8 + c.text_w(val, "b", 16) + 32
        y += 72 + 16

    # ---------- footer ----------
    notes = d.get("notes") or []
    for n in notes:
        c.text(PAD + 4, y + 4, n, "r", 13, MUTED)
        y += 22
    y += 12

    out = io.BytesIO()
    c.finish(max(y, 200)).save(out, "PNG", optimize=True)
    out.seek(0)
    return out


def _m(n):
    n = float(n)
    return f"{n / 1e6:.2f}M" if abs(n) >= 1e6 else f"{n:,.0f}"


# ============================================================
# LEADERBOARD CARD
# ============================================================
def render_leaderboard_card(d):
    """d: title, subtitle, accent(rgb), group(bool), unit_prefix('+'),
    rows: [{name, val, delta(int|None: +up/-down rank change), level('good'|'mid'|'bad'|None), me(bool)}] sorted desc,
    me_row: optional {rank, name, val} pinned at the bottom when the viewer is outside the list,
    footer: str. Returns BytesIO PNG."""
    rows = d.get("rows") or []
    accent = d.get("accent") or GOLD_DEFAULT
    c = _Canvas(2400)
    y = PAD

    # header
    c.rect(PAD, y, W - 2 * PAD, 96, PANEL)
    c.rect(PAD, y + 20, 5, 56, accent, r=3)
    c.text(PAD + 28, y + 22, d.get("title", "Leaderboard"), "b", 30, TEXT)
    c.text(PAD + 28, y + 62, d.get("subtitle", ""), "r", 15, MUTED)
    if d.get("group"):
        w = c.text_w("GROUP", "b", 13) + 28
        c.rect(W - PAD - 28 - w, y + 34, w, 28, PANEL2, r=14)
        c.text(W - PAD - 28 - w / 2, y + 48, "GROUP", "b", 13, accent, anchor="mm")
    y += 96 + 16

    # one list, medals for the top 3
    rest = rows
    if rest:
        rh = 54
        panel_h = 20 + len(rest) * rh + 10 + (64 if d.get("me_row") else 0)
        c.rect(PAD, y, W - 2 * PAD, panel_h, PANEL)
        top = rows[0]["val"] or 1
        ry = y + 20
        for i, r in enumerate(rest):
            rank = i + 1
            if r.get("me"):
                c.rect(PAD + 10, ry - 4, W - 2 * PAD - 20, rh - 4, PANEL2, r=12, outline=accent)
            medal = _icon(f"medal_{rank}", 30) if rank <= 3 else None
            if medal:
                c.im.paste(medal, (int((PAD + 25) * S), int((ry + 5) * S)), medal)
            else:
                c.text(PAD + 40, ry + 21, f"{rank}", "b", 16, MUTED, anchor="mm")
            nm = _fit(c, r["name"], "b" if rank <= 3 else "s", 19 if rank <= 3 else 17, 230)
            c.text(PAD + 80, ry + 21, nm[0], "b" if rank <= 3 else "s", nm[1], TEXT, anchor="lm")
            col = {"good": GREEN, "mid": YELLOW, "bad": RED}.get(r.get("level"), accent)
            c.bar(PAD + 330, ry + 14, 330, 14, r["val"] / top, col)
            c.text(PAD + 690, ry + 21, f"{d.get('unit_prefix', '+')}{_fmt(r['val'])}", "b", 18 if rank <= 3 else 17, TEXT, anchor="lm")
            if r.get("delta"):
                _delta(c, W - PAD - 28, ry + 9, r["delta"])
            ry += rh
        if d.get("me_row"):
            m = d["me_row"]
            c.d.line([(PAD + 28) * S, (ry + 4) * S, (W - PAD - 28) * S, (ry + 4) * S], fill=TRACK, width=S)
            ry += 14
            c.rect(PAD + 10, ry, W - 2 * PAD - 20, 44, PANEL2, r=12, outline=accent)
            c.text(PAD + 40, ry + 22, f"{m['rank']}", "b", 16, accent, anchor="mm")
            c.text(PAD + 80, ry + 22, f"{m['name']}  (you)", "s", 17, TEXT, anchor="lm")
            c.text(PAD + 690, ry + 22, f"{d.get('unit_prefix', '+')}{_fmt(m['val'])}", "b", 17, TEXT, anchor="lm")
        y += panel_h + 16

    if d.get("footer"):
        c.text(PAD + 4, y + 2, d["footer"], "r", 13, MUTED)
        y += 26
    y += 10
    out = io.BytesIO()
    c.finish(max(y, 200)).save(out, "PNG", optimize=True)
    out.seek(0)
    return out


GOLD_DEFAULT = (245, 197, 66)


def _fit(c, s, weight, size, max_w):
    """Shrink font size until text fits max_w (min 12); returns (text, size)."""
    s = str(s)
    while c.text_w(s, weight, size) > max_w and size > 12:
        size -= 1
    return s, size


def _delta(c, right, y, delta, **kw):
    up = delta > 0
    col = GREEN if up else RED
    txt = f"{'▲' if up else '▼'} {abs(delta)}"
    c.text(right, y + 12, txt, "b", 14, col, anchor="rm")


# ============================================================
# COMPARE CARD (head to head)
# ============================================================
def render_compare_card(d):
    """d: a{name,tag}, b{name,tag}, subtitle, rows: [(label, a_val, b_val)], higher_is_better default True."""
    rows = d["rows"]
    c = _Canvas(1600)
    y = PAD
    half = (W - 2 * PAD - 120) // 2
    c.rect(PAD, y, W - 2 * PAD, 110, PANEL)
    ax = PAD + 28
    bx = W - PAD - 28
    c.text(ax, y + 22, f"{d['a'].get('tag', '')}", "s", 14, MUTED)
    na = _fit(c, d["a"]["name"], "b", 30, 340)
    c.text(ax, y + 44, na[0], "b", na[1], BLUE)
    c.text(bx, y + 22, f"{d['b'].get('tag', '')}", "s", 14, MUTED, anchor="ra")
    nb = _fit(c, d["b"]["name"], "b", 30, 340)
    c.text(bx, y + 44, nb[0], "b", nb[1], ORANGE, anchor="ra")
    c.text(W / 2, y + 40, "VS", "b", 26, MUTED, anchor="mm")
    c.text(W / 2, y + 80, d.get("subtitle", ""), "r", 13, MUTED, anchor="mm")
    y += 110 + 16

    wins_a = wins_b = 0
    rh = 74
    panel_h = 20 + len(rows) * rh
    c.rect(PAD, y, W - 2 * PAD, panel_h, PANEL)
    ry = y + 14
    mid = W / 2
    bar_w = half - 150
    for label, av, bv in rows:
        aw, bw = av > bv, bv > av
        wins_a += aw
        wins_b += bw
        top = max(av, bv, 1)
        c.text(mid, ry + 8, label.upper(), "s", 12, MUTED, anchor="mm")
        # left bar grows leftwards from center, right bar rightwards
        by = ry + 24
        lx = mid - 24
        c.rect(lx - bar_w, by, bar_w, 14, TRACK, r=7)
        fw = max(14, bar_w * av / top) if av else 0
        if fw:
            c.rect(lx - fw, by, fw, 14, BLUE if aw or av == bv else (60, 100, 150), r=7)
        rx = mid + 24
        c.rect(rx, by, bar_w, 14, TRACK, r=7)
        fw = max(14, bar_w * bv / top) if bv else 0
        if fw:
            c.rect(rx, by, fw, 14, ORANGE if bw or av == bv else (150, 95, 50), r=7)
        c.text(PAD + 28, ry + 31, _fmt(av), "b" if aw else "s", 19 if aw else 17, TEXT if aw else MUTED, anchor="lm")
        c.text(W - PAD - 28, ry + 31, _fmt(bv), "b" if bw else "s", 19 if bw else 17, TEXT if bw else MUTED, anchor="rm")
        ry += rh
    y += panel_h + 16

    # verdict
    c.rect(PAD, y, W - 2 * PAD, 64, PANEL)
    if wins_a == wins_b:
        verdict, vcol = f"Dead even, {wins_a} categories each", MUTED
    else:
        w, n = (d["a"]["name"], wins_a) if wins_a > wins_b else (d["b"]["name"], wins_b)
        verdict, vcol = f"{w} takes it, {n} of {len(rows)} categories", YELLOW
    c.text(W / 2, y + 32, verdict, "b", 20, vcol, anchor="mm")
    y += 64 + 24
    out = io.BytesIO()
    c.finish(y).save(out, "PNG", optimize=True)
    out.seek(0)
    return out


# ============================================================
# EVENTS CARD (timeline)
# ============================================================
def _chip(c, x, y, text, color=MUTED, fill=PANEL2):
    w = c.text_w(text, "s", 13) + 22
    c.rect(x, y, w, 26, fill, r=13)
    c.text(x + 11, y + 13, text, "s", 13, color, anchor="lm")
    return w + 8


def _human_delta(seconds):
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def render_events_card(d):
    """d: now (datetime, UTC), events: [{name, dt (datetime UTC), repeat(str|None), lead(int minutes|None),
    channel(str), ping(str)}] sorted by time, tz_label (str), total (int)."""
    from datetime import timedelta
    now = d["now"]
    evs = d["events"]
    c = _Canvas(3000)
    y = PAD

    c.rect(PAD, y, W - 2 * PAD, 96, PANEL)
    c.rect(PAD, y + 20, 5, 56, BLUE, r=3)
    c.text(PAD + 28, y + 22, "Upcoming Events", "b", 30, TEXT)
    c.text(PAD + 28, y + 62, f"{d.get('tz_label', 'UTC')}  ·  as of {now.strftime('%a %d %b, %H:%M')}", "r", 15, MUTED)
    cnt = f"{d.get('total', len(evs))} scheduled"
    w = c.text_w(cnt, "b", 13) + 28
    c.rect(W - PAD - 28 - w, y + 34, w, 28, PANEL2, r=14)
    c.text(W - PAD - 28 - w / 2, y + 48, cnt, "b", 13, BLUE, anchor="mm")
    y += 96 + 16

    if not evs:
        c.rect(PAD, y, W - 2 * PAD, 90, PANEL)
        c.text(W / 2, y + 45, "Nothing scheduled", "s", 18, MUTED, anchor="mm")
        y += 106
    else:
        # hero: next event
        e = evs[0]
        secs = (e["dt"] - now).total_seconds()
        soon = secs < 3600
        accent = ORANGE if soon else GREEN
        hh = 132
        c.rect(PAD, y, W - 2 * PAD, hh, PANEL)
        c.rect(PAD, y, 6, hh, accent, r=3)
        c.text(PAD + 30, y + 20, "NEXT UP", "s", 13, MUTED)
        nm = _fit(c, e["name"], "b", 32, 560)
        c.text(PAD + 30, y + 44, nm[0], "b", nm[1], TEXT)
        c.text(W - PAD - 30, y + 24, _human_delta(secs), "b", 44, accent, anchor="ra")
        c.text(W - PAD - 30, y + 80, "until it starts", "r", 14, MUTED, anchor="ra")
        c.text(PAD + 30, y + 92, f"{e['dt'].strftime('%a %d %b · %H:%M')}", "s", 16, MUTED)
        cx = PAD + 30 + c.text_w(f"{e['dt'].strftime('%a %d %b · %H:%M')}", "s", 16) + 20
        for chip in _event_chips(e):
            cx += _chip(c, cx, y + 88, *chip) if False else _chip(c, cx, y + 88, chip[0], chip[1])
        y += hh + 16

        # grouped by day
        groups = {}
        for e in evs[1:]:
            groups.setdefault(e["dt"].date(), []).append(e)
        for day, items in groups.items():
            delta_days = (day - now.date()).days
            label = "TODAY" if delta_days == 0 else "TOMORROW" if delta_days == 1 else day.strftime("%A").upper()
            c.text(PAD + 6, y + 6, f"{label}  ·  {day.strftime('%d %b')}", "s", 13, MUTED)
            y += 28
            rh = 70
            ph = len(items) * rh + 8
            c.rect(PAD, y, W - 2 * PAD, ph, PANEL)
            ry = y + 4
            for i, e in enumerate(items):
                c.text(PAD + 28, ry + 22, e["dt"].strftime("%H:%M"), "b", 22, BLUE, anchor="lm")
                nm = _fit(c, e["name"], "b", 19, 380)
                c.text(PAD + 130, ry + 22, nm[0], "b", nm[1], TEXT, anchor="lm")
                c.text(W - PAD - 28, ry + 22, f"in {_human_delta((e['dt'] - now).total_seconds())}", "s", 15, MUTED, anchor="rm")
                cx = PAD + 130
                for chip in _event_chips(e):
                    cx += _chip(c, cx, ry + 36, chip[0], chip[1])
                if i < len(items) - 1:
                    c.d.line([(PAD + 28) * S, (ry + rh - 2) * S, (W - PAD - 28) * S, (ry + rh - 2) * S], fill=TRACK, width=S)
                ry += rh
            y += ph + 14

    more = d.get("total", len(evs)) - len(evs)
    if more > 0:
        c.text(PAD + 6, y + 4, f"+ {more} more not shown", "r", 13, MUTED)
        y += 24
    y += 14
    out = io.BytesIO()
    c.finish(max(y, 200)).save(out, "PNG", optimize=True)
    out.seek(0)
    return out


def _event_chips(e):
    chips = []
    if e.get("repeat"):
        chips.append((f"↻ {e['repeat']}", PURPLE))
    chips.append((f"{e['lead']}m before" if e.get("lead") else "no reminder", MUTED if not e.get("lead") else TEAL))
    if e.get("channel"):
        chips.append((f"#{e['channel']}", MUTED))
    if e.get("ping"):
        chips.append((e["ping"], YELLOW))
    return chips
