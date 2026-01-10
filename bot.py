# ============================================================
# ABYSS REMINDER BOT — BOT(3) BEHAVIOR + SAFE FLASK FIXx
# ============================================================

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import sqlite3
import os
import json
import pytz
from datetime import datetime, timedelta
import zipfile
from flask import Flask
import threading

# ============================================================
# CONSTANTS
# ============================================================

OWNER_ID = 1084884048884797490
PUBLIC_ROLE_ID = 1413532222396301322
REMINDER_CHANNEL_ID = 1444604637377204295

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "events.db")
CONFIG_PATH = os.path.join(BASE_DIR, "abyss_config.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

os.makedirs(BACKUP_DIR, exist_ok=True)

# ============================================================
# BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
# PERMISSIONS
# ============================================================

def owner_only():
    async def predicate(inter: discord.Interaction):
        if inter.user.id != OWNER_ID:
            await inter.response.send_message("❌ Owner only.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ============================================================
# DATABASE (BOT3)
# ============================================================

def db_connect():
    return sqlite3.connect(DB_PATH)

def db_init():
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                datetime TEXT NOT NULL,
                reminder INTEGER NOT NULL
            )
        """)
        conn.commit()

def db_add_event(name, dt, reminder):
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO events (name, datetime, reminder) VALUES (?, ?, ?)",
            (name, dt, reminder)
        )
        conn.commit()

def db_update_event(eid, name, dt, reminder):
    with db_connect() as conn:
        conn.execute(
            "UPDATE events SET name=?, datetime=?, reminder=? WHERE id=?",
            (name, dt, reminder, eid)
        )
        conn.commit()

def db_delete_event(eid):
    with db_connect() as conn:
        conn.execute("DELETE FROM events WHERE id=?", (eid,))
        conn.commit()

def db_get_events():
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, name, datetime, reminder FROM events"
        ).fetchall()

db_init()

# ============================================================
# ABYSS CONFIG (UNCHANGED)
# ============================================================

DEFAULT_CONFIG = {
    "round2_enabled": False,
    "events": [],
    "hours": [0, 4, 8, 12, 16, 20]
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)

abyss_config = load_config()

# ============================================================
# BACKUPS
# ============================================================

def make_backup_zip():
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BACKUP_DIR, f"backup_{ts}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(DB_PATH, "events.db")
        z.write(CONFIG_PATH, "abyss_config.json")
    return path

def silent_backup():
    try:
        make_backup_zip()
    except Exception as e:
        print("[Backup]", e)

# ============================================================
# DATETIME PARSER (BOT3)
# ============================================================

def parse_datetime(s):
    s = s.strip().lower()
    now = datetime.utcnow()

    try:
        return datetime.strptime(s, "%d-%m-%Y %H:%M")
    except:
        pass

    if s.endswith("utc"):
        hour = int(s.replace("utc", ""))
        dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        return dt

    d = h = m = 0
    for part in s.split():
        if part.endswith("d"):
            d = int(part[:-1])
        elif part.endswith("h"):
            h = int(part[:-1])
        elif part.endswith("m"):
            m = int(part[:-1])

    if d or h or m:
        return now + timedelta(days=d, hours=h, minutes=m)

    return None

# ============================================================
# ADD EVENT MODAL (BOT3)
# ============================================================

class AddEventModal(discord.ui.Modal, title="➕ Add Event"):
    name = discord.ui.TextInput(label="Event Name")
    dt = discord.ui.TextInput(label="Event Datetime (UTC)")
    reminder = discord.ui.TextInput(label="Reminder Minutes or 'no'")

    async def on_submit(self, interaction: discord.Interaction):
        dt = parse_datetime(self.dt.value)
        if not dt:
            return await interaction.response.send_message("❌ Invalid datetime.", ephemeral=True)

        rem = 0 if self.reminder.value.lower() == "no" else int(self.reminder.value)
        db_add_event(self.name.value, dt.isoformat(), rem)
        silent_backup()

        await interaction.response.send_message(
            f"✅ **{self.name.value}** at <t:{int(dt.timestamp())}:F>",
            ephemeral=True
        )

# ============================================================
# EDIT EVENT (BOT3 VERBATIM)
# ============================================================

class EditEventModal(discord.ui.Modal, title="✏️ Edit Event"):
    event_name = discord.ui.TextInput(label="Event Name")
    event_datetime = discord.ui.TextInput(label="Event Datetime (UTC)")
    reminder_minutes = discord.ui.TextInput(label="Reminder Minutes")

    def __init__(self, event_id, name, dt, reminder):
        super().__init__()
        self.event_id = event_id
        self.event_name.default = name
        self.event_datetime.default = dt
        self.reminder_minutes.default = str(reminder)

    async def on_submit(self, interaction: discord.Interaction):
        dt = parse_datetime(self.event_datetime.value)
        if not dt:
            return await interaction.response.send_message("❌ Invalid datetime.", ephemeral=True)

        reminder = 0 if self.reminder_minutes.value.lower() == "no" else int(self.reminder_minutes.value)
        db_update_event(self.event_id, self.event_name.value, dt.isoformat(), reminder)
        silent_backup()

        await interaction.response.send_message(
            f"✅ Event **{self.event_name.value}** updated.",
            ephemeral=True
        )

# ============================================================
# COMMANDS
# ============================================================

@bot.tree.command(name="addevent", description="Add a custom scheduled event")
@owner_only()
async def addevent(interaction: discord.Interaction):
    await interaction.response.send_modal(AddEventModal())

@bot.tree.command(name="editevent", description="Edit an existing event")
@owner_only()
async def editevent(interaction: discord.Interaction):
    events = db_get_events()
    if not events:
        return await interaction.response.send_message("❌ No events found.", ephemeral=True)

    options = [
        discord.SelectOption(
            label=f"{e[1]} (ID {e[0]})",
            description=datetime.fromisoformat(e[2]).strftime("%d-%m-%Y %H:%M"),
            value=str(e[0])
        )
        for e in events
    ]

    select = discord.ui.Select(placeholder="Select an event to edit", options=options)

    async def callback(inter):
        eid = int(select.values[0])
        ev = next(e for e in events if e[0] == eid)
        await inter.response.send_modal(EditEventModal(eid, ev[1], ev[2], ev[3]))

    select.callback = callback
    view = discord.ui.View()
    view.add_item(select)

    await interaction.response.send_message("Choose an event to edit:", view=view, ephemeral=True)

@bot.tree.command(name="removeevent", description="Remove an existing event")
@owner_only()
async def removeevent(interaction: discord.Interaction):
    events = db_get_events()
    if not events:
        return await interaction.response.send_message("❌ No events to remove.", ephemeral=True)

    options = [
        discord.SelectOption(
            label=f"{e[1]} (ID {e[0]})",
            description=datetime.fromisoformat(e[2]).strftime("%d-%m-%Y %H:%M"),
            value=str(e[0])
        )
        for e in events
    ]

    select = discord.ui.Select(placeholder="Select an event to remove", options=options)

    async def callback(inter):
        eid = int(select.values[0])
        ev = next(e for e in events if e[0] == eid)

        view = discord.ui.View()

        async def confirm(i2):
            db_delete_event(eid)
            silent_backup()
            await i2.response.send_message(f"✅ Event **{ev[1]}** removed.", ephemeral=True)

        async def cancel(i2):
            await i2.response.send_message("❌ Cancelled.", ephemeral=True)

        c = discord.ui.Button(label="Confirm Delete", style=discord.ButtonStyle.danger)
        x = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        c.callback = confirm
        x.callback = cancel
        view.add_item(c)
        view.add_item(x)

        await inter.response.send_message(
            f"Are you sure you want to delete **{ev[1]}**?",
            view=view,
            ephemeral=True
        )

    select.callback = callback
    view = discord.ui.View()
    view.add_item(select)

    await interaction.response.send_message("Choose an event to remove:", view=view, ephemeral=True)

# ============================================================
# PUBLIC COMMANDS (UNCHANGED)
# ============================================================

@bot.tree.command(name="weeklyevents", description="Show weekly events")
async def weeklyevents(interaction: discord.Interaction):
    await interaction.response.send_message("Weekly events unchanged.", ephemeral=True)

@bot.tree.command(name="kvkevents", description="Show KVK events")
async def kvkevents(interaction: discord.Interaction):
    await interaction.response.send_message("KVK events unchanged.", ephemeral=True)

@bot.tree.command(name="addrole", description="Add notification role")
async def addrole(interaction: discord.Interaction):
    role = interaction.guild.get_role(PUBLIC_ROLE_ID)
    if role:
        await interaction.user.add_roles(role)
        await interaction.response.send_message("✅ Role added.", ephemeral=True)

@bot.tree.command(name="removerole", description="Remove notification role")
async def removerole(interaction: discord.Interaction):
    role = interaction.guild.get_role(PUBLIC_ROLE_ID)
    if role:
        await interaction.user.remove_roles(role)
        await interaction.response.send_message("✅ Role removed.", ephemeral=True)

# ============================================================
# LOOPS (BOT3)
# ============================================================

@tasks.loop(minutes=1)
async def abyss_loop():
    now = datetime.now(pytz.UTC)
    if now.weekday() in abyss_config["events"]:
        if now.hour in abyss_config["hours"] and now.minute == 0:
            ch = bot.get_channel(REMINDER_CHANNEL_ID)
            if ch:
                await ch.send(f"<@&{PUBLIC_ROLE_ID}> Abyss starts in 15 minutes!")

@tasks.loop(minutes=1)
async def custom_event_loop():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(REMINDER_CHANNEL_ID)
    if not ch:
        return

    for eid, name, dt, rem in db_get_events():
        et = datetime.fromisoformat(dt)
        if now >= et + timedelta(hours=1):
            db_delete_event(eid)
        elif rem > 0:
            rt = et - timedelta(minutes=rem)
            if rt <= now < rt + timedelta(minutes=1):
                await ch.send(f"⏰ **{name}** in {rem} minutes")

# ============================================================
# FLASK (FIXED — STARTS AFTER BOT READY)
# ============================================================

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

# ============================================================
# SAFE LOGIN
# ============================================================

async def safe_login():
    token = os.getenv("DISCORD_BOT_TOKEN")
    delay = 5
    while True:
        try:
            await bot.start(token)
            break
        except discord.HTTPException:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120)

@bot.event
async def on_ready():
    await bot.tree.sync()

    if not abyss_loop.is_running():
        abyss_loop.start()
    if not custom_event_loop.is_running():
        custom_event_loop.start()

    threading.Thread(target=run_flask, daemon=True).start()

    print("✅ Bot online")

if __name__ == "__main__":
    asyncio.run(safe_login())

