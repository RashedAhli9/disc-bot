# ============================================================
# FLASK KEEPALIVE (STARTS IMMEDIATELY – KOYEB SAFE)
# ============================================================

from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "OK", 200

@app.route("/health")
def health():
    return "healthy", 200

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# ============================================================
# DISCORD + SYSTEM IMPORTS
# ============================================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import sqlite3
import pytz
from datetime import datetime, timedelta, date, time
from discord.ui import View, Select, Button, Modal, TextInput
import io
import zipfile
import asyncio

# ============================================================
# GLOBAL CONFIG
# ============================================================

MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490
ROLE_ID = 1413532222396301322
BACKUP_CHANNEL_ID = 1444604637377204295

ABYSS_CONFIG_FILE = "abyss_config.json"
DB = "events.db"

BACKUP_DIR = "backups"
MAX_BACKUPS = 10
os.makedirs(BACKUP_DIR, exist_ok=True)

# ============================================================
# REQUIRED HELPERS (FIXES ALL CRASHES)
# ============================================================

def has_admin(inter):
    if inter.user.id == OWNER_ID:
        return True
    return any(r.permissions.administrator for r in inter.user.roles)

def parse_datetime(input_str):
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except:
        pass

    now = datetime.utcnow()
    d = h = m = 0

    for part in input_str.lower().split():
        if part.endswith("d"):
            d = int(part[:-1])
        elif part.endswith("h"):
            h = int(part[:-1])
        elif part.endswith("m"):
            m = int(part[:-1])
        elif part.endswith("utc"):
            hh = int(part.replace("utc", ""))
            return now.replace(hour=hh, minute=0, second=0, microsecond=0)

    return now + timedelta(days=d, hours=h, minutes=m)

def day_name(i):
    return ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i]

def pretty_days(days):
    return ", ".join(day_name(d) for d in sorted(days))

def pretty_hours(hours):
    return ", ".join(f"{h:02}:00" for h in sorted(hours))

# ============================================================
# BACKUP SYSTEM
# ============================================================

def cleanup_old_backups():
    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
        reverse=True
    )
    for f in files[MAX_BACKUPS:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
        except:
            pass

async def upload_backup(path):
    ch = bot.get_channel(BACKUP_CHANNEL_ID)
    if ch:
        await ch.send("📦 **Backup created**", file=discord.File(path))

def make_backup():
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BACKUP_DIR, f"backup_{ts}.zip")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB):
            z.write(DB)
        if os.path.exists(ABYSS_CONFIG_FILE):
            z.write(ABYSS_CONFIG_FILE)

    cleanup_old_backups()

    if bot.loop.is_running():
        bot.loop.create_task(upload_backup(path))

def silent_backup():
    try:
        make_backup()
    except:
        pass
# ============================================================
# SQLITE DATABASE
# ============================================================

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            datetime TEXT NOT NULL,
            reminder INTEGER NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def db_add_event(name, dt, reminder):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO events (name, datetime, reminder) VALUES (?, ?, ?)",
        (name, dt, reminder)
    )
    conn.commit()
    conn.close()
    silent_backup()

def db_get_events():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "SELECT id, name, datetime, reminder FROM events ORDER BY datetime ASC"
    )
    rows = c.fetchall()
    conn.close()
    return rows

def db_update_event(event_id, name=None, dt=None, reminder=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    if name is not None:
        c.execute("UPDATE events SET name=? WHERE id=?", (name, event_id))
    if dt is not None:
        c.execute("UPDATE events SET datetime=? WHERE id=?", (dt, event_id))
    if reminder is not None:
        c.execute("UPDATE events SET reminder=? WHERE id=?", (reminder, event_id))

    conn.commit()
    conn.close()
    silent_backup()

def db_delete_event(event_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()
    silent_backup()

init_db()

# ============================================================
# DEFAULT ABYSS CONFIG
# ============================================================

DEFAULT_ABYSS = {
    "days": [1, 4, 6],
    "hours": [0, 4, 8, 12, 16, 20],
    "reminder_hours": [0, 4, 8, 12, 16, 20],
    "round2": True
}

def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=2)

def load_json(path, default):
    ensure_file(path, default)
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

cfg = load_json(ABYSS_CONFIG_FILE, DEFAULT_ABYSS)
for k in DEFAULT_ABYSS:
    if k not in cfg:
        cfg[k] = DEFAULT_ABYSS[k]
save_json(ABYSS_CONFIG_FILE, cfg)

ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
ROUND2_ENABLED = cfg["round2"]

# ============================================================
# DISCORD BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.active_edit = None

# ============================================================
# BACKUP SLASH COMMANDS (OWNER ONLY)
# ============================================================

@bot.tree.command(name="backup", description="List recent backups")
async def backup(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
        reverse=True
    )

    if not files:
        return await inter.response.send_message("📦 No backups found.", ephemeral=True)

    msg = "**📦 Recent Backups:**\n" + "\n".join(
        f"- `{f}`" for f in files[:MAX_BACKUPS]
    )
    await inter.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="forcebackup", description="Create a backup now")
async def forcebackup(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    make_backup()
    await inter.response.send_message("✅ Backup created.", ephemeral=True)

@bot.tree.command(name="restorebackup", description="Restore a backup")
async def restorebackup(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
        reverse=True
    )

    if not files:
        return await inter.response.send_message("❌ No backups found.", ephemeral=True)

    select = Select(
        placeholder="Select backup to restore",
        options=[discord.SelectOption(label=f, value=f) for f in files[:MAX_BACKUPS]]
    )

    async def cb(i):
        path = os.path.join(BACKUP_DIR, select.values[0])
        with zipfile.ZipFile(path, "r") as z:
            z.extractall(".")
        await i.response.send_message(
            f"♻️ Restored `{select.values[0]}`. Restart the bot.",
            ephemeral=True
        )

    select.callback = cb
    view = View()
    view.add_item(select)

    await inter.response.send_message(
        "Choose a backup:",
        view=view,
        ephemeral=True
    )
# ============================================================
# ON READY
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print("Synced", len(synced))
    except Exception as e:
        print("Sync failed:", e)

    abyss_reminder_loop.start()
    custom_event_loop.start()

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Bot restarted successfully.")

# ============================================================
# WEEKLY EVENTS
# ============================================================

weekly_events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯"
}

start_date = date(2025, 9, 16)

@bot.tree.command(name="weeklyevent", description="Show current and upcoming weekly Abyss events")
async def weeklyevent(inter):
    today = date.today()
    sunday = start_date - timedelta(days=start_date.weekday() + 1)
    weeks = (today - sunday).days // 7

    this_tue = sunday + timedelta(weeks=weeks, days=2)
    now = datetime.utcnow()

    event_start = datetime.combine(this_tue, time(0, 0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks += 1
        this_tue = sunday + timedelta(weeks=weeks, days=2)
        event_start = datetime.combine(this_tue, time(0, 0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i in range(4):
        idx = (weeks + i) % 4
        nm = weekly_events[idx]
        emoji = event_emojis.get(nm, "📌")
        ev_date = sunday + timedelta(weeks=weeks + i, days=2)
        base_dt = datetime.combine(ev_date, time(0, 0))

        if i == 0 and event_start <= now < event_end:
            left = event_end - now
            st = f"🟢 LIVE NOW ({left.seconds // 3600}h {(left.seconds // 60) % 60}m left)"
        else:
            left = base_dt - now
            st = f"⏳ {left.days}d {left.seconds // 3600}h {(left.seconds // 60) % 60}m"

        msg += f"{nums[i]} {emoji} **{nm}** — <t:{int(base_dt.timestamp())}:F>\n{st}\n\n"

    await inter.response.send_message(msg)

# ============================================================
# KVK / CUSTOM EVENTS DISPLAY
# ============================================================

@bot.tree.command(name="kvkevent", description="Show upcoming custom scheduled events")
async def kvkevent(inter):
    now = datetime.utcnow()
    rows = db_get_events()

    upcoming = [r for r in rows if datetime.fromisoformat(r[2]) > now]
    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    upcoming = upcoming[:4]
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    msg = "📅 **Upcoming Events**\n\n"

    for i, row in enumerate(upcoming):
        event_id, name, dt, rem = row
        dt_obj = datetime.fromisoformat(dt)
        left = dt_obj - now
        msg += (
            f"{nums[i]} **{name}** — <t:{int(dt_obj.timestamp())}:F>\n"
            f"Starts in {left.days}d {left.seconds // 3600}h {(left.seconds // 60) % 60}m\n\n"
        )

    await inter.response.send_message(msg, ephemeral=True)

# ============================================================
# ADD EVENT MODAL
# ============================================================

class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name", placeholder="e.g. Pass 1 Opens")
    dt_input = TextInput(
        label="Datetime (UTC)",
        placeholder="DD-MM-YYYY HH:MM | 1d 2h | 14utc"
    )
    reminder = TextInput(
        label="Reminder (minutes or 'no')",
        placeholder="15"
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            dt = parse_datetime(self.dt_input.value)
            rem = 0 if self.reminder.value.lower() == "no" else int(self.reminder.value)

            db_add_event(self.name.value, dt.isoformat(), rem)

            await interaction.response.send_message(
                f"✅ **Event Added**\n**{self.name.value}**\n<t:{int(dt.timestamp())}:F>",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# ============================================================
# ADD / EDIT / REMOVE EVENT COMMANDS
# ============================================================

@bot.tree.command(name="addevent", description="Add a new custom event")
async def addevent(interaction: discord.Interaction):
    if not has_admin(interaction):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    await interaction.response.send_modal(AddEventModal())

@bot.tree.command(name="editevent", description="Edit an existing custom event")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    rows = db_get_events()
    if not rows:
        return await inter.response.send_message("📭 No events available.", ephemeral=True)

    class PickEvent(Select):
        def __init__(self):
            super().__init__(
                placeholder="Select event to edit",
                options=[
                    discord.SelectOption(
                        label=f"{eid}: {name}",
                        description=datetime.fromisoformat(dt).strftime("%d-%m %H:%M"),
                        value=str(eid)
                    )
                    for eid, name, dt, rem in rows
                ]
            )

        async def callback(self, inter2):
            eid = int(self.values[0])

            class EditView(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self, btn, ix):
                    bot.active_edit = (ix.user.id, eid, "name")
                    await ix.response.send_message("Send new name in chat.", ephemeral=True)

                @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.secondary)
                async def edit_time(self, btn, ix):
                    bot.active_edit = (ix.user.id, eid, "time")
                    await ix.response.send_message("Send new datetime in chat.", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_rem(self, btn, ix):
                    bot.active_edit = (ix.user.id, eid, "rem")
                    await ix.response.send_message("Send new reminder (minutes or 'no').", ephemeral=True)

            await inter2.response.send_message("Choose what to edit:", view=EditView(), ephemeral=True)

    await inter.response.send_message("Pick an event:", view=View(PickEvent()), ephemeral=True)

@bot.tree.command(name="removeevent", description="Remove a custom event")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    rows = db_get_events()
    if not rows:
        return await inter.response.send_message("📭 No events available.", ephemeral=True)

    class PickRemove(Select):
        def __init__(self):
            super().__init__(
                placeholder="Select event to remove",
                options=[
                    discord.SelectOption(
                        label=f"{eid}: {name}",
                        description=datetime.fromisoformat(dt).strftime("%d-%m %H:%M"),
                        value=str(eid)
                    )
                    for eid, name, dt, rem in rows
                ]
            )

        async def callback(self, inter2):
            db_delete_event(int(self.values[0]))
            await inter2.response.send_message("🗑 Event removed.", ephemeral=True)

    await inter.response.send_message("Pick an event to remove:", view=View(PickRemove()), ephemeral=True)

# ============================================================
# ABYSS CONFIG COMMAND
# ============================================================

@bot.tree.command(name="abyssconfig", description="Configure Abyss days, hours, and reminders")
async def abyssconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    emb = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
    emb.add_field(name="Days", value=pretty_days(ABYSS_DAYS), inline=False)
    emb.add_field(name="Hours", value=pretty_hours(ABYSS_HOURS), inline=False)
    emb.add_field(name="Reminder Hours", value=pretty_hours(REMINDER_HOURS), inline=False)
    emb.add_field(
        name="Round 2",
        value="Enabled" if ROUND2_ENABLED else "Disabled",
        inline=False
    )

    view = AbyssConfigView(
        ABYSS_DAYS,
        ABYSS_HOURS,
        REMINDER_HOURS,
        ROUND2_ENABLED
    )

    await inter.response.send_message(
        embed=emb,
        view=view,
        ephemeral=True
    )


# ============================================================
# REMINDER LOOPS
# ============================================================

@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    if now.weekday() not in ABYSS_DAYS:
        return

    ch = bot.get_channel(channel_id)
    if not ch:
        return

    if now.hour in REMINDER_HOURS and now.minute == 0:
        await ch.send(f"<@&{ROLE_ID}>, Abyss starts in 15 minutes!")

    if ROUND2_ENABLED and now.hour in REMINDER_HOURS and now.minute == 30:
        await ch.send(f"<@&{ROLE_ID}>, Round 2 in 15 minutes!")

sent_custom = set()

@tasks.loop(minutes=1)
async def custom_event_loop():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(channel_id)
    if not ch:
        return

    rows = db_get_events()
    for ev in rows:
        event_id, name, dt, rem = ev
        dt_obj = datetime.fromisoformat(dt)

        if now >= dt_obj + timedelta(hours=1):
            db_delete_event(event_id)
            continue

        if rem > 0:
            rtime = dt_obj - timedelta(minutes=rem)
            key = (event_id, rtime.isoformat())
            if rtime <= now < rtime + timedelta(minutes=1):
                if key not in sent_custom:
                    await ch.send(
                        f"⏰ Reminder: **{name}** in {rem} minutes! <t:{int(dt_obj.timestamp())}:F>"
                    )
                    sent_custom.add(key)

    if len(sent_custom) > 300:
        sent_custom.clear()

# ============================================================
# SAFE LOGIN (NO bot.run)
# ============================================================

async def safe_login():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ Missing DISCORD_BOT_TOKEN")
        return

    delay = 10
    while True:
        try:
            await bot.start(token)
            break
        except discord.HTTPException as e:
            print(f"[Login Retry] {e}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120)

if __name__ == "__main__":
    asyncio.run(safe_login())

