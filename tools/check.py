"""Pre-push safety check. Run: python3 tools/check.py
Catches the things that crash-loop the bot on Railway:
  1. syntax errors            2. undefined names (typos, missing imports)
  3. duplicate slash/prefix command names (what killed the bot with /addevent)
  4. the module failing to import (it registers every command at import time)
Exit code 0 = safe to push."""
import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["bot.py", "card_render.py"]
fail = False


def bad(msg):
    global fail
    fail = True
    print("FAIL:", msg)


# 1. syntax
for f in FILES:
    try:
        ast.parse(open(os.path.join(ROOT, f), encoding="utf-8").read(), f)
    except SyntaxError as e:
        bad(f"{f}:{e.lineno}: {e.msg}")

# 2. undefined names
r = subprocess.run([sys.executable, "-m", "pyflakes"] + [os.path.join(ROOT, f) for f in FILES],
                   capture_output=True, text=True)
for line in (r.stdout + r.stderr).splitlines():
    if "undefined name" in line:
        bad(line)

# 3. duplicate command names
src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
for kind, pat in (("slash", r'@bot\.tree\.command\(name="([^"]+)"'),
                  ("prefix", r'@bot\.command\(name="([^"]+)"'),
                  ("context menu", r'@bot\.tree\.context_menu\(name="([^"]+)"')):
    seen = {}
    for m in re.finditer(pat, src):
        seen[m.group(1)] = seen.get(m.group(1), 0) + 1
    for name, n in seen.items():
        if n > 1:
            bad(f"duplicate {kind} command '{name}' x{n}")

# 4. real import (registers all commands). Never logs in: login only runs under __main__.
env = dict(os.environ, PORT="0", DISCORD_BOT_TOKEN="", ANTHROPIC_API_KEY="", PYTHONDONTWRITEBYTECODE="1")
code = ("import sys; sys.path.insert(0, %r); import bot; "
        "print('commands: slash=%%d prefix=%%d' %% (len(bot.bot.tree.get_commands()), len(bot.bot.commands)))") % ROOT
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120, cwd=ROOT)
if r.returncode != 0:
    bad("importing bot.py failed:\n" + (r.stderr or r.stdout)[-1500:])
else:
    print(r.stdout.strip().splitlines()[-1])

# 4b. every image card renderer draws a PNG from sample data
try:
    sys.path.insert(0, ROOT)
    from datetime import datetime, timedelta
    import card_render as cr
    _now = datetime(2026, 1, 1, 12)
    _rows = [dict(name="A", val=3), dict(name="B", val=2, me=True)]
    _smoke = {
        "progress": lambda: cr.render_progress_card(dict(tag="[T]", name="Test", season="s", start="2026-01-01",
                      end="2026-01-09", account_id="1", power=1, merits="+1", kills="+1", deads="+1", healed="+1")),
        "leaderboard": lambda: cr.render_leaderboard_card(dict(title="t", subtitle="s", accent=cr.RED, rows=_rows)),
        "compare": lambda: cr.render_compare_card(dict(a=dict(name="A"), b=dict(name="B"), rows=[("Power", 2, 1)])),
        "events": lambda: cr.render_events_card(dict(now=_now, events=[dict(name="E", dt=_now + timedelta(hours=2),
                      lead=30, channel="c", ping="@p")], total=1)),
    }
    for _name, _fn in _smoke.items():
        if not _fn().read(8).startswith(b"\x89PNG"):
            bad(f"{_name} card did not produce a PNG")
    print("cards: OK")
except Exception as e:
    bad(f"card smoke test crashed: {type(e).__name__}: {e}")

# 5. parser tests
r = subprocess.run([sys.executable, "tests/test_parsers.py"], capture_output=True, text=True, env=env, timeout=180, cwd=ROOT)
if r.returncode != 0:
    bad("tests failed:\n" + (r.stderr or r.stdout)[-1500:])
else:
    print("tests: OK")

print("RESULT:", "FAILED" if fail else "OK")
sys.exit(1 if fail else 0)
