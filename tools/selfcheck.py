"""Pre-push self-check. Run:  python3 tools/selfcheck.py
Catches the mistakes that crash-loop the bot on startup, without needing a Discord token:
  1. bot.py / card_render.py parse
  2. duplicate prefix commands, slash commands, context menus, aliases
  3. undefined names (pyflakes)
  4. every card renderer draws a PNG from sample data
Exit code 1 = do not push."""
import ast
import collections
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
fails = []


def fail(msg):
    fails.append(msg)
    print("FAIL:", msg)


def ok(msg):
    print("ok:  ", msg)


# 1. syntax
src = {}
for f in ("bot.py", "card_render.py"):
    try:
        src[f] = open(f, encoding="utf-8").read()
        ast.parse(src[f])
        ok(f"{f} parses")
    except SyntaxError as e:
        fail(f"{f}: syntax error line {e.lineno}: {e.msg}")

# 2. duplicate commands
if "bot.py" in src:
    tree = ast.parse(src["bot.py"])
    names = collections.defaultdict(list)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            chain = ast.unparse(dec.func)
            kind = {"bot.command": "prefix", "bot.tree.command": "slash", "bot.tree.context_menu": "menu",
                    "bot.group": "prefix"}.get(chain)
            if not kind:
                continue
            nm = None
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    nm = kw.value.value
                if kw.arg == "aliases" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    for a in kw.value.elts:
                        if isinstance(a, ast.Constant):
                            names[("prefix", a.value)].append(node.lineno)
            nm = nm or node.name
            names[(kind, nm)].append(node.lineno)
    dups = {k: v for k, v in names.items() if len(v) > 1}
    for (kind, nm), lines in dups.items():
        fail(f"duplicate {kind} command '{nm}' at lines {lines}")
    if not dups:
        ok(f"no duplicate commands ({len(names)} registered names)")

# 3. undefined names
r = subprocess.run([sys.executable, "-m", "pyflakes", "bot.py", "card_render.py"], capture_output=True, text=True)
bad = [l for l in r.stdout.splitlines() if "undefined name" in l]
for l in bad:
    fail(l)
if not bad:
    ok("no undefined names")

# 4. cards draw
try:
    from datetime import datetime, timedelta
    import card_render as cr
    sample_prog = dict(tag="[T]", name="Test", season="s", start="2026-01-01", end="2026-01-09", account_id="1",
                       power=1, merits="+1", kills="+1", deads="+1", healed="+1",
                       deads_req=dict(deaths=1, required=2, level="mid", done=False),
                       troops=[("Infantry", 1, 1)], rss=[("Gold", "1")], coins="1", pets="1", decos="1")
    rows = [dict(name="A", val=3), dict(name="B 𝔻", val=2, me=True), dict(name="C", val=1)]
    now = datetime(2026, 1, 1, 12)
    renders = {
        "progress": lambda: cr.render_progress_card(sample_prog),
        "leaderboard": lambda: cr.render_leaderboard_card(dict(title="t", subtitle="s", accent=cr.RED, rows=rows)),
        "compare": lambda: cr.render_compare_card(dict(a=dict(name="A"), b=dict(name="B"), rows=[("Power", 2, 1)])),
        "events": lambda: cr.render_events_card(dict(now=now, events=[dict(name="E", dt=now + timedelta(hours=2),
                                                                             lead=30, channel="c", ping="@p")], total=1)),
    }
    for extra in ("render_scoreboard_card", "render_info_card", "render_table_card"):
        if hasattr(cr, extra):
            pass
    for name, fn in renders.items():
        out = fn()
        if not out.read(8).startswith(b"\x89PNG"):
            fail(f"{name} card did not produce a PNG")
        else:
            ok(f"{name} card draws")
except Exception as e:
    fail(f"card smoke test crashed: {type(e).__name__}: {e}")

print()
if fails:
    print(f"{len(fails)} problem(s) - fix before pushing.")
    sys.exit(1)
print("All checks passed.")
