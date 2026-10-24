"""Image cards for the bot (Pillow). Posted as normal attachments, so they show for everyone
no matter their Discord embed settings.

Everything is drawn at 2x and scaled down so edges are smooth. Fonts live in assets/fonts,
medal icons in emoji_assets (the same files uploaded as bot emojis)."""
import io
import os

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


def _font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        name = {"r": "Inter-Regular.otf", "s": "Inter-SemiBold.otf", "b": "Inter-Bold.otf"}[weight]
        path = os.path.join(FONT_DIR, name)
        try:
            _font_cache[key] = ImageFont.truetype(path, size * S)
        except Exception:
            try:
                _font_cache[key] = ImageFont.truetype("DejaVuSans.ttf", size * S)
            except Exception:
                _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


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
        self.d.text((x * S, y * S), str(s), font=_font(weight, size), fill=fill, anchor=anchor)

    def text_w(self, s, weight="r", size=16):
        return self.d.textlength(str(s), font=_font(weight, size)) / S

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

    def tile(self, x, y, w, h, label, value, accent, sub=None, rank=None, value_size=34):
        self.rect(x, y, w, h, PANEL)
        self.rect(x, y + 16, 5, h - 32, accent, r=3)
        self.text(x + 24, y + 18, label.upper(), "s", 13, MUTED)
        self.text(x + 24, y + 40, value, "b", value_size, TEXT)
        if sub:
            self.text(x + 24, y + h - 30, sub, "r", 14, accent)
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
    th = 124
    if d.get("power") or d.get("power_gain"):
        pv = _fmt(d["power"]) if d.get("power") else f"+{_fmt(d.get('power_gain'))}"
        if d.get("power") and d.get("power_gain"):
            sub = f"+{_fmt(d['power_gain'])} this season"
        elif d.get("power"):
            sub = "no new peak this season"
        else:
            sub = None
        c.tile(PAD, y, half, th, "Power", pv, GREEN if d.get("power_gain") else MUTED, sub, d.get("power_rank"))
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
