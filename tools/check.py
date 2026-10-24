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

print("RESULT:", "FAILED" if fail else "OK")
sys.exit(1 if fail else 0)
