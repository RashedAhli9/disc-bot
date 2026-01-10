# ================================================
#   ABYSS REMINDER BOT — FULL REBUILD (CHUNK 1/10)
#   Using bot (2).py as the exact base
# ================================================

import discord
from discord import app_commands
from discord.ext import tasks, commands
import asyncio
import sqlite3
import os
import json
import pytz
from datetime import datetime, timedelta
import zipfile
import shutil
from flask import Flask
import threading

# -------------------------------
# BOT + INTENT SETUP
# -------------------------------

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

OWNER_ID = 1084884048884797490
PUBLIC_ROLE_ID = 1413532222396301322

# -------------------------------
# PERMISSION CHECKS
# -------------------------------

def is_owner(inter: discord.Interaction):
    return inter.user.id == OWNER_ID

def owner_only():
    async def predicate(inter: discord.Interaction):
        if inter.user.id != OWNER_ID:
            await inter.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# -------------------------------
# DATABASE — EXACT SAME AS bot (2).py
# -------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "events.db")

def db_connect():
    return sqlite3.connect(DB_PATH)

def db_init():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            datetime TEXT,
            reminder INTEGER
        )
    """)
    conn.commit()
    conn.close()

db_init()

# -------------------------------
# ABYSS CONFIG — EXACT STRUCTURE FROM bot (2).py
# -------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "abyss_config.json")

DEFAULT_CONFIG = {
    "round2_enabled": False,
    "events": []
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

# -------------------------------
# BACKUP SYSTEM — NEW FEATURE
# -------------------------------

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

def make_backup_zip():
    """Creates a ZIP containing events.db + abyss_config.json"""
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    zip_name = f"backup_{ts}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB_PATH):
            z.write(DB_PATH, "events.db")
        if os.path.exists(CONFIG_PATH):
            z.write(CONFIG_PATH, "abyss_config.json")

    return zip_path

# -------------------------------
# FLASK KEEPALIVE — EXACT FROM bot (2).py
# -------------------------------

app = Flask('')

@app.route('/')
def home():
    return "Bot alive!", 200

def run_web():
    app.run(host="0.0.0.0", port=8000)

def keep_alive():
    thread = threading.Thread(target=run_web)
    thread.start()

keep_alive()

# -------------------------------
# SAFE LOGIN MODE (REPLACES bot.run)
# -------------------------------

async def safe_login():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_BOT_TOKEN not found!")
        return

    while True:
        try:
            await bot.start(token)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("⚠️ Rate-limited — retrying in 30 seconds...")
                await asyncio.sleep(30)
            else:
                print(f"Unexpected login error: {e}")
                await asyncio.sleep(10)
# ============================================================
# =============== DATETIME PARSING ============================
# ============================================================

def parse_time_input(time_str):
    """Parses various formats like '14utc', '1d2h', and '2026-01-01 15:00'"""
    try:
        return datetime.strptime(time_str, "%d-%m-%Y %H:%M")
    except ValueError:
        pass
    
    # Support '1d 2h' format (relative time)
    if 'd' in time_str or 'h' in time_str or 'm' in time_str:
        days = hours = minutes = 0
        for part in time_str.split():
            if part.endswith("d"):
                days = int(part[:-1])
            if part.endswith("h"):
                hours = int(part[:-1])
            if part.endswith("m"):
                minutes = int(part[:-1])
        return datetime.utcnow() + timedelta(days=days, hours=hours, minutes=minutes)

    # Support '14utc' format (specific time today at 14:00 UTC)
    if time_str.lower().endswith("utc"):
        now = datetime.utcnow()
        return now.replace(hour=int(time_str[:-3]), minute=0, second=0, microsecond=0)

    return None

# ============================================================
# =============== EVENT MODAL UI (NEW /addevent) ================
# ============================================================

class AddEventModal(discord.ui.Modal, title="➕ Add Event"):
    event_name = discord.ui.TextInput(label="Event Name", placeholder="Enter event name")
    event_datetime = discord.ui.TextInput(label="Event Datetime (UTC)", placeholder="14-01-2026 15:30 or 1d2h30m or 14utc")
    reminder_minutes = discord.ui.TextInput(label="Reminder Minutes", placeholder="10 (or 'no' for no reminder)")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse the datetime input
            event_time = parse_time_input(self.event_datetime.value)
            if not event_time:
                await interaction.response.send_message(
                    "❌ Invalid datetime format. Please use the format: `14-01-2026 15:30`, `1d 2h`, or `14utc`",
                    ephemeral=True
                )
                return

            reminder = 0 if self.reminder_minutes.value.lower() == "no" else int(self.reminder_minutes.value)

            # Add event to database
            db_add_event(self.event_name.value, event_time.isoformat(), reminder)

            await interaction.response.send_message(
                f"✅ Event **{self.event_name.value}** added for **{event_time.isoformat()} UTC** (Reminder: {reminder} minutes).",
                ephemeral=True
            )

            # Trigger silent backup after event is added
            silent_backup()
        
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )

# ============================================================
# =============== /addevent COMMAND ============================
# ============================================================

@bot.tree.command(name="addevent", description="Add a new event to the schedule")
@owner_only()
async def addevent(interaction: discord.Interaction):
    # Show modal to input event details
    modal = AddEventModal()
    await interaction.response.send_modal(modal)
# ============================================================
# =============== EVENT EDITING AND REMOVAL ===================
# ============================================================

# ============================
# Edit Event Modal
# ============================

class EditEventModal(discord.ui.Modal, title="✏️ Edit Event"):
    event_name = discord.ui.TextInput(label="Event Name", placeholder="Enter event name")
    event_datetime = discord.ui.TextInput(label="Event Datetime (UTC)", placeholder="14-01-2026 15:30 or 1d2h30m or 14utc")
    reminder_minutes = discord.ui.TextInput(label="Reminder Minutes", placeholder="10 (or 'no' for no reminder)")

    event_id = None  # To hold the event ID for editing

    def __init__(self, event_id, event_name, event_datetime, reminder_minutes):
        super().__init__()
        self.event_id = event_id
        self.event_name.default = event_name
        self.event_datetime.default = event_datetime
        self.reminder_minutes.default = reminder_minutes

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse the datetime input
            event_time = parse_time_input(self.event_datetime.value)
            if not event_time:
                await interaction.response.send_message(
                    "❌ Invalid datetime format. Please use the format: `14-01-2026 15:30`, `1d 2h`, or `14utc`",
                    ephemeral=True
                )
                return

            reminder = 0 if self.reminder_minutes.value.lower() == "no" else int(self.reminder_minutes.value)

            # Update event in the database
            db_update_event(self.event_id, self.event_name.value, event_time.isoformat(), reminder)

            await interaction.response.send_message(
                f"✅ Event **{self.event_name.value}** updated for **{event_time.isoformat()} UTC** (Reminder: {reminder} minutes).",
                ephemeral=True
            )

            # Trigger silent backup after event is updated
            silent_backup()

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )


# ============================
# /editevent COMMAND
# ============================

@bot.tree.command(name="editevent", description="Edit an existing event")
@owner_only()
async def editevent(interaction: discord.Interaction):
    # Fetch all events
    events = db_get_events()
    if not events:
        return await interaction.response.send_message(
            "❌ No events found.",
            ephemeral=True
        )

    # Event selection menu
    options = [
        discord.SelectOption(
            label=f"{event[1]} (ID: {event[0]})",  # Event name + ID
            description=datetime.fromisoformat(event[2]).strftime("%d-%m-%Y %H:%M"),
            value=str(event[0])  # Use event ID for editing
        )
        for event in events
    ]

    select = discord.ui.Select(placeholder="Select an event to edit", options=options)
    
    async def select_callback(interaction: discord.Interaction):
        event_id = int(select.values[0])
        event = next(e for e in events if e[0] == event_id)

        modal = EditEventModal(event_id, event[1], event[2], str(event[3]))
        await interaction.response.send_modal(modal)

    select.callback = select_callback

    # Show select menu
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Choose an event to edit:",
        view=view,
        ephemeral=True
    )


# ============================
# /removeevent COMMAND
# ============================

@bot.tree.command(name="removeevent", description="Remove an existing event")
@owner_only()
async def removeevent(interaction: discord.Interaction):
    # Fetch all events
    events = db_get_events()
    if not events:
        return await interaction.response.send_message(
            "❌ No events to remove.",
            ephemeral=True
        )

    # Event selection menu
    options = [
        discord.SelectOption(
            label=f"{event[1]} (ID: {event[0]})",  # Event name + ID
            description=datetime.fromisoformat(event[2]).strftime("%d-%m-%Y %H:%M"),
            value=str(event[0])  # Use event ID for removal
        )
        for event in events
    ]

    select = discord.ui.Select(placeholder="Select an event to remove", options=options)
    
    async def select_callback(interaction: discord.Interaction):
        event_id = int(select.values[0])
        event = next(e for e in events if e[0] == event_id)

        # Confirm delete action
        confirmation_view = discord.ui.View()

        async def confirm_delete(interaction: discord.Interaction):
            db_delete_event(event_id)
            await interaction.response.send_message(f"✅ Event **{event[1]}** removed.", ephemeral=True)
            silent_backup()

        async def cancel_delete(interaction: discord.Interaction):
            await interaction.response.send_message(f"❌ Deletion of **{event[1]}** canceled.", ephemeral=True)

        # Confirm buttons
        confirm_button = discord.ui.Button(label="Confirm Delete", style=discord.ButtonStyle.danger)
        confirm_button.callback = confirm_delete
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel_button.callback = cancel_delete

        confirmation_view.add_item(confirm_button)
        confirmation_view.add_item(cancel_button)

        await interaction.response.send_message(
            f"Are you sure you want to delete event **{event[1]}**?",
            view=confirmation_view,
            ephemeral=True
        )

    select.callback = select_callback

    # Show select menu
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Choose an event to remove:",
        view=view,
        ephemeral=True
    )
# ============================================================
# =============== REMINDER LOOPS ============================
# ============================================================

@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    tz = pytz.timezone("UTC")
    now = datetime.now(tz)

    # Check if it's one of the selected days
    if now.weekday() not in abyss_config['events']:
        return

    # Get the channel for reminders
    channel = bot.get_channel(1444604637377204295)  # Replace with actual channel ID
    if not channel:
        return

    if now.hour in abyss_config["hours"] and now.minute == 0:
        await channel.send(f"<@&{PUBLIC_ROLE_ID}>, Abyss event starts in 15 minutes!")

    if abyss_config.get("round2_enabled", False) and now.hour in abyss_config["hours"] and now.minute == 30:
        await channel.send(f"<@&{PUBLIC_ROLE_ID}>, Round 2 event starts in 15 minutes!")


sent_custom = set()

@tasks.loop(minutes=1)
async def custom_event_loop():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    channel = bot.get_channel(1444604637377204295)  # Replace with actual channel ID
    if not channel:
        return

    rows = db_get_events()
    for event in rows:
        event_id, name, dt, reminder = event
        event_time = datetime.fromisoformat(dt)

        # DELETE event after it ends (1 hour after the start)
        if now >= event_time + timedelta(hours=1):
            db_delete_event(event_id)
            continue

        # Send reminder notifications if event has a reminder set
        if reminder > 0:
            reminder_time = event_time - timedelta(minutes=reminder)
            key = (event_id, reminder_time.isoformat())
            if reminder_time <= now < reminder_time + timedelta(minutes=1):
                if key not in sent_custom:
                    await channel.send(f"⏰ Reminder: **{name}** in {reminder} minutes! <t:{int(event_time.timestamp())}:F>")
                    sent_custom.add(key)

    if len(sent_custom) > 300:
        sent_custom.clear()
# ============================================================
# =============== BACKUP SYSTEM ==============================
# ============================================================

BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

BACKUP_LOG_CHANNEL = 1444604637377204295  # Your backup notification channel


# ------------------------------------------------------------
# Utility: Create ZIP backup containing events.db + abyss_config.json
# ------------------------------------------------------------
def create_backup_zip() -> str:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    zip_name = f"backup-{timestamp}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_name)

    with zipfile.ZipFile(zip_path, "w") as z:
        if os.path.exists(DB):
            z.write(DB, arcname="events.db")
        if os.path.exists(ABYSS_CONFIG_FILE):
            z.write(ABYSS_CONFIG_FILE, arcname="abyss_config.json")

    return zip_path


# ------------------------------------------------------------
# Silent Backup (no sending file)
# Triggered when: add/edit/delete event
# ------------------------------------------------------------
def silent_backup():
    try:
        create_backup_zip()
    except Exception as e:
        print(f"[Silent Backup Error] {e}")


# ------------------------------------------------------------
# /forcebackup — Creates a new backup ZIP manually
# OWNER ONLY
# ------------------------------------------------------------
@bot.tree.command(name="forcebackup", description="Create a new backup ZIP of all bot configurations and events.")
@owner_only()
async def forcebackup(interaction: discord.Interaction):

    zip_path = create_backup_zip()

    await interaction.response.send_message(
        f"✅ **New backup created!**\n`{os.path.basename(zip_path)}`",
        ephemeral=True
    )

    # Send backup file to log channel
    channel = bot.get_channel(BACKUP_LOG_CHANNEL)
    if channel:
        await channel.send(
            content=f"📦 **Forced backup created by <@{interaction.user.id}>**",
            file=discord.File(zip_path)
        )


# ------------------------------------------------------------
# /backup — List last 3 backups with download buttons
# OWNER ONLY
# ------------------------------------------------------------
@bot.tree.command(name="backup", description="List the latest 3 backups with download buttons.")
@owner_only()
async def backup(interaction: discord.Interaction):

    files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    latest = files[:3]

    if not latest:
        return await interaction.response.send_message("❌ No backups found.", ephemeral=True)

    embed = discord.Embed(
        title="📦 Latest Backups",
        description="Click a button to download.",
        color=0x2ecc71
    )

    view = discord.ui.View()

    for fname in latest:
        fpath = os.path.join(BACKUP_DIR, fname)

        async def make_callback(fp=fpath):
            async def callback(int2: discord.Interaction):
                await int2.response.send_message(
                    content=f"📦 **Backup File:** `{os.path.basename(fp)}`",
                    file=discord.File(fp),
                    ephemeral=True
                )
            return callback

        btn = discord.ui.Button(
            label=fname,
            style=discord.ButtonStyle.primary
        )
        btn.callback = await make_callback()

        view.add_item(btn)

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ------------------------------------------------------------
# /restorebackup — Restore events.db and abyss_config.json from a ZIP
# OWNER ONLY
# ------------------------------------------------------------
@bot.tree.command(name="restorebackup", description="Restore bot data from an uploaded backup .ZIP file.")
@owner_only()
async def restorebackup(interaction: discord.Interaction):

    await interaction.response.send_message(
        "📤 **Upload your backup ZIP file now.**\nMust contain: `events.db` and `abyss_config.json`.",
        ephemeral=True
    )

    def check(msg):
        return msg.author.id == interaction.user.id and msg.attachments

    try:
        msg = await bot.wait_for("message", timeout=60, check=check)
    except asyncio.TimeoutError:
        return await interaction.followup.send("❌ Restore timed out.", ephemeral=True)

    attachment = msg.attachments[0]

    if not attachment.filename.endswith(".zip"):
        return await interaction.followup.send("❌ File must be a `.zip`.", ephemeral=True)

    zip_path = f"/tmp/{attachment.filename}"
    await attachment.save(zip_path)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            if "events.db" in z.namelist():
                z.extract("events.db", ".")
            if "abyss_config.json" in z.namelist():
                z.extract("abyss_config.json", ".")

        # Reload Abyss settings
        global abyss_config
        abyss_config = load_json(ABYSS_CONFIG_FILE, DEFAULT_ABYSS)

        await interaction.followup.send("✅ **Backup restored successfully!**", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error restoring backup: {e}", ephemeral=True)
# ============================================================
# =============== PERMISSION SYSTEM + ROLE COMMANDS ==========
# ============================================================

OWNER_ID = 1084884048884797490
PUBLIC_ROLE_ID = 1413532222396301322


# ---------------- OWNER ONLY DECORATOR ----------------------
def owner_only():
    def predicate(interaction: discord.Interaction):
        return interaction.user.id == OWNER_ID
    return app_commands.check(predicate)


# ---------------- ADMIN OR OWNER DECORATOR ------------------
def admin_or_owner():
    def predicate(interaction: discord.Interaction):
        if interaction.user.id == OWNER_ID:
            return True
        return any(r.permissions.administrator for r in interaction.user.roles)
    return app_commands.check(predicate)



# ============================================================
# PUBLIC ROLE COMMANDS
# ============================================================

@bot.tree.command(name="addrole", description="Adds the Abyss notification role to yourself.")
async def addrole(interaction: discord.Interaction):
    role = interaction.guild.get_role(PUBLIC_ROLE_ID)

    if not role:
        return await interaction.response.send_message("❌ Role not found.", ephemeral=True)

    if role in interaction.user.roles:
        return await interaction.response.send_message("⚠️ You already have this role.", ephemeral=True)

    try:
        await interaction.user.add_roles(role)
        await interaction.response.send_message("✅ Role added!", ephemeral=True)
    except:
        await interaction.response.send_message("❌ I do not have permission to add that role.", ephemeral=True)



@bot.tree.command(name="removerole", description="Removes the Abyss notification role from yourself.")
async def removerole(interaction: discord.Interaction):
    role = interaction.guild.get_role(PUBLIC_ROLE_ID)

    if not role:
        return await interaction.response.send_message("❌ Role not found.", ephemeral=True)

    if role not in interaction.user.roles:
        return await interaction.response.send_message("⚠️ You don't have this role.", ephemeral=True)

    try:
        await interaction.user.remove_roles(role)
        await interaction.response.send_message("✅ Role removed!", ephemeral=True)
    except:
        await interaction.response.send_message("❌ I do not have permission to remove that role.", ephemeral=True)



# ============================================================
# RESTRICT OWNER/ADMIN COMMANDS
# ============================================================

# /addevent
addevent = bot.tree.get_command("addevent")
if addevent:
    addevent.add_check(admin_or_owner())

# /editevent
editevent_cmd = bot.tree.get_command("editevent")
if editevent_cmd:
    editevent_cmd.add_check(admin_or_owner())

# /removeevent
removeevent_cmd = bot.tree.get_command("removeevent")
if removeevent_cmd:
    removeevent_cmd.add_check(admin_or_owner())

# /abyssconfig
abyssconfig_cmd = bot.tree.get_command("abyssconfig")
if abyssconfig_cmd:
    abyssconfig_cmd.add_check(owner_only())

# /backup
backup_cmd = bot.tree.get_command("backup")
if backup_cmd:
    backup_cmd.add_check(owner_only())

# /forcebackup
forcebackup_cmd = bot.tree.get_command("forcebackup")
if forcebackup_cmd:
    forcebackup_cmd.add_check(owner_only())

# /restorebackup
restore_cmd = bot.tree.get_command("restorebackup")
if restore_cmd:
    restore_cmd.add_check(owner_only())
# ============================================================
# =============== KEEPALIVE FLASK SERVER =====================
# ============================================================

from flask import Flask
import threading

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot alive", 200


def run_web():
    # Use the PORT Koyeb requires
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    thread = threading.Thread(target=run_web)
    thread.start()


# Start flask immediately
keep_alive()


# ============================================================
# =============== SAFE LOGIN SYSTEM ==========================
# ============================================================

import asyncio

async def safe_login():
    """
    Prevent discord global 429 lockout during rapid redeploys.
    Tries to login repeatedly with increasing delay.
    """

    delay = 5  # Start with 5 seconds
    max_delay = 120  # Hard cap

    while True:
        try:
            print(f"[SafeLogin] Attempting login… delay={delay}s")
            await bot.start(TOKEN)
            break  # If login succeeds, exit loop
        except discord.HTTPException as e:
            if e.status == 429:
                print("[SafeLogin] BLOCKED by Discord Rate Limit (429). Retrying...")
            else:
                print(f"[SafeLogin] Unexpected HTTP error: {e}")

        except Exception as e:
            print(f"[SafeLogin] Login error: {e}")

        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)  # Exponential backoff


# ============================================================
# =============== START TASK LOOPS (AFTER LOGIN) =============
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print("Slash sync failed:", e)

    # Start loops (if not already running)
    if not abyss_reminder_loop.is_running():
        abyss_reminder_loop.start()

    if not custom_event_loop.is_running():
        custom_event_loop.start()

    # Log restart
    log_channel = bot.get_channel(BACKUP_LOG_CHANNEL)
    if log_channel:
        await log_channel.send("🔄 **Bot restarted and online.**")

# ============================================================
# =============== IMPROVED DATETIME PARSER ====================
# ============================================================

def parse_datetime(input_str: str):
    """
    Supports:
    - Absolute datetime: '14-01-2026 15:30'
    - Relative: '1d 2h 30m'
    - Quick UTC hour: '14utc' -> today at 14:00 UTC (or tomorrow if passed)
    """

    s = input_str.strip().lower()
    now = datetime.utcnow()

    # --------------------------------------------------------
    # 1. ABSOLUTE FORMAT (DD-MM-YYYY HH:MM)
    # --------------------------------------------------------
    try:
        return datetime.strptime(s, "%d-%m-%Y %H:%M")
    except:
        pass

    # --------------------------------------------------------
    # 2. "14utc" FORMAT
    # --------------------------------------------------------
    if s.endswith("utc"):
        try:
            hour = int(s.replace("utc", ""))

            # Create today @ HH:00
            dt = datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=hour,
                minute=0,
                second=0
            )

            # If passed → schedule tomorrow
            if dt <= now:
                dt += timedelta(days=1)

            return dt

        except:
            pass

    # --------------------------------------------------------
    # 3. RELATIVE FORMAT (Xd Yh Zm)
    # --------------------------------------------------------
    try:
        days = hours = minutes = 0

        for part in s.split():
            if part.endswith("d"):
                days = int(part[:-1])
            elif part.endswith("h"):
                hours = int(part[:-1])
            elif part.endswith("m"):
                minutes = int(part[:-1])

        # If we parsed at least something
        if days or hours or minutes:
            return now + timedelta(days=days, hours=hours, minutes=minutes)

    except:
        pass

    # --------------------------------------------------------
    # 4. FAILED TO PARSE
    # --------------------------------------------------------
    return None
# ============================================================
# =============== INTERNAL SAFETY & VALIDATION ===============
# ============================================================

import time


# ------------------------------------------------------------
# Safe DB wrapper (auto retries)
# ------------------------------------------------------------
def safe_db_action(action, *args, **kwargs):
    for attempt in range(3):
        try:
            return action(*args, **kwargs)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(0.2)
                continue
            print(f"[DB ERROR] {e}")
            break
        except Exception as e:
            print(f"[DB UNKNOWN ERROR] {e}")
            break
    return None


# PATCH DB FUNCTIONS TO USE SAFE WRAPPER
def db_add_event_safe(name, dt, reminder):
    return safe_db_action(db_add_event, name, dt, reminder)

def db_update_event_safe(eid, name=None, dt=None, reminder=None):
    return safe_db_action(db_update_event, eid, name, dt, reminder)

def db_delete_event_safe(eid):
    return safe_db_action(db_delete_event, eid)

def db_get_events_safe():
    result = safe_db_action(db_get_events)
    return result if result else []


# ------------------------------------------------------------
# Validation for event creation
# ------------------------------------------------------------
def validate_event_creation(name, dt):
    if not name or name.strip() == "":
        return False, "Event name cannot be empty."

    if not isinstance(dt, datetime):
        return False, "Invalid datetime."

    if dt <= datetime.utcnow():
        return False, "You cannot schedule an event in the past."

    return True, None


# ------------------------------------------------------------
# Patch AddEvent modal submit
# ------------------------------------------------------------
async def patched_addevent_submit(self, interaction):
    try:
        dt = parse_datetime(self.dt_input.value)
        if not dt:
            return await interaction.response.send_message(
                "❌ Invalid datetime format.",
                ephemeral=True
            )

        ok, err = validate_event_creation(self.name.value, dt)
        if not ok:
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)

        rem = 0 if self.reminder.value.lower() == "no" else int(self.reminder.value)

        db_add_event_safe(self.name.value, dt.isoformat(), rem)

        await interaction.response.send_message(
            f"✅ Added **{self.name.value}** at <t:{int(dt.timestamp())}:F>",
            ephemeral=True
        )

        # Silent backup + log
        silent_backup()
        channel = bot.get_channel(BACKUP_LOG_CHANNEL)
        if channel:
            await channel.send(f"➕ **Event Added:** {self.name.value} ({dt.isoformat()})")

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# Monkey patch the AddEventModal on_submit
AddEventModal.on_submit = patched_addevent_submit


# ------------------------------------------------------------
# Memory cleanup for sent_custom reminder registry
# ------------------------------------------------------------
def cleanup_sent_custom():
    global sent_custom
    if len(sent_custom) > 200:
        sent_custom = set()


# Patch custom_event_loop to include cleanup
_original_custom_event_loop = custom_event_loop

@tasks.loop(minutes=1)
async def custom_event_loop():
    await _original_custom_event_loop.callback()
    cleanup_sent_custom()
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot alive", 200

def run_web():
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    threading.Thread(target=run_web).start()

keep_alive()
async def safe_login():
    delay = 5
    max_delay = 120
    while True:
        try:
            await bot.start(TOKEN)
            break
        except discord.HTTPException as e:
            if e.status == 429:
                print("Rate limited by Discord")
        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)

# ============================================================
# RUN BOT WITH SAFE LOGIN
# ============================================================

# ============================================================
# === FINAL APPENDED PATCH (SAFE LOGIN + BACKUP + FLASK)
# === DO NOT ADD ANYTHING BELOW THIS
# ============================================================

# -------------------------------
# SILENT BACKUP WRAPPER (HOOK)
# -------------------------------

def _silent_backup_wrapper():
    try:
        make_backup_zip()
    except Exception as e:
        print(f"[Backup] {e}")

# Override DB mutators WITHOUT touching original code
_original_db_add_event = db_add_event
def db_add_event(name, dt, reminder):
    _original_db_add_event(name, dt, reminder)
    _silent_backup_wrapper()

_original_db_update_event = db_update_event
def db_update_event(eid, name, dt, reminder):
    _original_db_update_event(eid, name, dt, reminder)
    _silent_backup_wrapper()

_original_db_delete_event = db_delete_event
def db_delete_event(eid):
    _original_db_delete_event(eid)
    _silent_backup_wrapper()

# -------------------------------
# FINAL FLASK KEEPALIVE
# -------------------------------

_final_app = Flask("final_keepalive")

@_final_app.route("/")
def _final_home():
    return "Bot alive (final)", 200

def _final_run_web():
    port = int(os.getenv("PORT", 8000))
    _final_app.run(host="0.0.0.0", port=port)

threading.Thread(target=_final_run_web, daemon=True).start()

# -------------------------------
# FINAL SAFE LOGIN (OVERRIDES ALL)
# -------------------------------

async def safe_login():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ DISCORD_BOT_TOKEN not set")
        return

    delay = 5
    max_delay = 120

    while True:
        try:
            print(f"[SafeLogin] Attempting login (delay={delay}s)")
            await bot.start(token)
            break
        except discord.HTTPException as e:
            if e.status == 429:
                print("[SafeLogin] Discord rate limit hit (429)")
            else:
                print(f"[SafeLogin] HTTP error: {e}")
        except Exception as e:
            print(f"[SafeLogin] Unexpected error: {e}")

        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)

# -------------------------------
# FORCE SAFE LOGIN ENTRYPOINT
# -------------------------------

if __name__ == "__main__":
    asyncio.run(safe_login())
