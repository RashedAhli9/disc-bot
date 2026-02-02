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
    print("[HEALTH CHECK] ping received")
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
import aiohttp
import shutil
import os

# ============================================================
# GLOBAL CONFIG
# ============================================================

MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490
ROLE_ID = 1413532222396301322
BACKUP_CHANNEL_ID = 1444604637377204295
ABYSS_ROLE_ID = 1413532222396301322
ABYSS_CONFIG_FILE = "abyss_config.json"
DB = "/data/events.db"


    
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
    input_str = input_str.strip()
    now = datetime.utcnow()

    # Case 1: full date + HH:MM
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except:
        pass

    # Case 2: full date + HHutc
    if "-" in input_str and "utc" in input_str:
        date_part, time_part = input_str.split()
        base_date = datetime.strptime(date_part, "%d-%m-%Y")
        hour = int(time_part.replace("utc", ""))
        return base_date.replace(
            hour=hour, minute=0, second=0, microsecond=0
        )

    # Relative parsing
    d = h = m = 0
    for part in input_str.lower().split():
        if part.endswith("d"):
            d = int(part[:-1])
        elif part.endswith("h"):
            h = int(part[:-1])
        elif part.endswith("m"):
            m = int(part[:-1])
        elif part.endswith("utc"):
            hour = int(part.replace("utc", ""))
            return now.replace(
                hour=hour, minute=0, second=0, microsecond=0
            )

    return now + timedelta(days=d, hours=h, minutes=m)


def day_name(i):
    return ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i]

def pretty_days(days):
    return ", ".join(day_name(d) for d in sorted(days))

def pretty_hours(hours):
    return ", ".join(f"{h:02}:00" for h in sorted(hours))


async def dm_abyss_role(bot: discord.Client, embed: discord.Embed):
    guild = bot.get_guild(GUILD_ID)
    print("[DM DEBUG] guild:", guild)

    if not guild:
        print("[DM DEBUG] ❌ Guild not found")
        return

    role = guild.get_role(ABYSS_ROLE_ID)
    print("[DM DEBUG] role:", role)

    if not role:
        print("[DM DEBUG] ❌ Role not found")
        return

    sent = 0
    async for member in guild.fetch_members(limit=None):
        if role in member.roles:
            print("[DM DEBUG] trying DM ->", member.name)
            try:
                dm = await member.create_dm()
                await dm.send(embed=embed)
                sent += 1
            except discord.Forbidden:
                print("[DM DEBUG] ❌ DMs blocked for", member.name)
            except Exception as e:
                print("[DM DEBUG] ❌ DM error", member.name, e)

    print(f"[DM DEBUG] sent to {sent} members")


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
    print("[DB ADD EVENT] writing to:", DB)
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
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

    await inter.response.defer(ephemeral=True)  # ✅ CRITICAL

    select = Select(
        placeholder="Select a backup to restore",
        options=[discord.SelectOption(label=f, value=f) for f in files]
    )

    async def cb(i):
        await i.response.defer(ephemeral=True)

        path = os.path.join(BACKUP_DIR, select.values[0])

        with zipfile.ZipFile(path, "r") as z:
            z.extractall(".")

        await i.followup.send(
            f"♻️ Restored `{select.values[0]}`. Restarting bot...",
            ephemeral=True
        )

        await asyncio.sleep(2)
       # auto-restart on Koyeb

    select.callback = cb
    view = View(timeout=60)
    view.add_item(select)

    await inter.followup.send("Choose a backup to restore:", view=view, ephemeral=True)

# ============================================================
# ON READY
# ============================================================


@tasks.loop(minutes=5)
async def self_ping():
    try:
        url = os.getenv("KOYEB_PUBLIC_URL")
        if not url:
            return

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                pass
    except Exception as e:
        print("[Self Ping Error]", e)

@bot.event
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Sync commands once
    try:
        synced = await bot.tree.sync()
        print("Synced", len(synced))
    except Exception as e:
        print("Sync failed:", e)

    # ✅ START SELF-PING (CRITICAL)
    if not self_ping.is_running():
        self_ping.start()

    # ✅ SAFE LOOP STARTS
    if not abyss_reminder_loop.is_running():
        abyss_reminder_loop.start()

    if not custom_event_loop.is_running():
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
@bot.tree.command(name="checkdb", description="check DB")
async def dbdump(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message(
            "Owner only.", ephemeral=True
        )

    rows = db_get_events()
    if not rows:
        return await interaction.response.send_message(
            "DB is empty.", ephemeral=True
        )

    msg = "\n".join(str(r) for r in rows)
    await interaction.response.send_message(
        f"```{msg}```", ephemeral=True
    )


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
    name = TextInput(
        label="Event Name",
        placeholder="e.g. Pass 1 Opens"
    )
    dt_input = TextInput(
        label="Datetime (UTC)",
        placeholder="DD-MM-YYYY HH:MM | 1d 2h | 14utc"
    )
    reminder = TextInput(
        label="Reminder (minutes or 'no')",
        placeholder="15"
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            dt = parse_datetime(self.dt_input.value)

            # Round event time to minute precision
            dt = dt.replace(second=0, microsecond=0)

            rem = (
                0
                if self.reminder.value.lower() == "no"
                else int(self.reminder.value)
            )

            db_add_event(
                self.name.value.strip(),
                dt.isoformat(),
                rem
            )

            await interaction.followup.send(
                f"✅ **Event Added**\n"
                f"**{self.name.value}**\n"
                f"<t:{int(dt.timestamp())}:F>",
                ephemeral=True
            )

        except Exception as e:
            print("[AddEvent Error]", e)
            await interaction.followup.send(
                "❌ Failed to add event.",
                ephemeral=True
            )

@bot.tree.command(name="addevent", description="Add a custom event")
async def addevent(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    await inter.response.send_modal(AddEventModal())


# ============================================================
# ADD / EDIT / REMOVE EVENT COMMANDS
# ============================================================

@bot.tree.command(name="testdm", description="Owner-only: test Abyss role DMs")
async def testdm(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message(
            "❌ Owner only.", ephemeral=True
        )

    embed = discord.Embed(
        title="🧪 Abyss DM Test",
        description=(
            "This is a **test DM** for Abyss reminders.\n\n"
            "If you received this message, DM delivery is working ✅"
        ),
        color=0x2ECC71
    )

    await interaction.response.send_message(
        "📨 Sending test DMs to all Abyss role members…",
        ephemeral=True
    )

    await dm_abyss_role(bot, embed)


@bot.tree.command(name="editevent", description="Edit an existing event")
async def editevent(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    events = db_get_events()
    if not events:
        return await inter.response.send_message("❌ No events available.", ephemeral=True)

    options = [
        discord.SelectOption(
            label=f"{name} ({dt})",
            value=str(event_id)
        )
        for event_id, name, dt, rem in events
    ]

    select = Select(
        placeholder="Select an event to edit",
        options=options
    )

    async def select_callback(i: discord.Interaction):
        event_id = int(select.values[0])
        event = next(e for e in events if e[0] == event_id)

        _, old_name, old_dt, old_rem = event

        class EditEventModal(Modal, title="Edit Event"):
            name = TextInput(label="Event Name", default=old_name)
            datetime = TextInput(
                label="Date & Time (YYYY-MM-DD HH:MM)",
                default=old_dt.replace("T", " ")[:16]
            )
            reminder = TextInput(
                label="Reminder (hours before)",
                default=str(old_rem)
            )

            async def on_submit(self, modal_inter: discord.Interaction):
                try:
                    dt_str = self.datetime.value.strip()

                    # Parse and round to minute precision
                    dt_obj = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                    dt_obj = dt_obj.replace(second=0, microsecond=0)
                    dt_str = dt_obj.isoformat(timespec="minutes")

                    rem = int(self.reminder.value.strip())

                    db_update_event(
                        event_id,
                        name=self.name.value.strip(),
                        dt=dt_str,
                        reminder=rem
                    )

                    await modal_inter.response.send_message(
                        "✅ Event updated successfully.",
                        ephemeral=True
                    )

                except ValueError:
                    await modal_inter.response.send_message(
                        "❌ Invalid date or reminder format.\nUse `YYYY-MM-DD HH:MM`.",
                        ephemeral=True
                    )

                except Exception as e:
                    print("[EditEvent Error]", e)
                    await modal_inter.response.send_message(
                        "❌ Failed to update event.",
                        ephemeral=True
                    )


        await i.response.send_modal(EditEventModal())

    select.callback = select_callback
    view = View()
    view.add_item(select)

    await inter.response.send_message(
        "Select an event to edit:",
        view=view,
        ephemeral=True
    )


@bot.tree.command(name="addrole", description="Get the Abyss role")
async def addrole(interaction: discord.Interaction):
    role = interaction.guild.get_role(ABYSS_ROLE_ID)
    if not role:
        return await interaction.response.send_message(
            "❌ Abyss role not found.", ephemeral=True
        )

    if role in interaction.user.roles:
        return await interaction.response.send_message(
            "⚠️ You already have the Abyss role.", ephemeral=True
        )

    await interaction.user.add_roles(role)
    await interaction.response.send_message(
        "✅ Abyss role added! You will now receive Abyss reminders.",
        ephemeral=True
    )
@bot.tree.command(name="removerole", description="Remove the Abyss role")
async def removerole(interaction: discord.Interaction):
    role = interaction.guild.get_role(ABYSS_ROLE_ID)
    if not role:
        return await interaction.response.send_message(
            "❌ Abyss role not found.", ephemeral=True
        )

    if role not in interaction.user.roles:
        return await interaction.response.send_message(
            "⚠️ You don’t have the Abyss role.", ephemeral=True
        )

    await interaction.user.remove_roles(role)
    await interaction.response.send_message(
        "✅ Abyss role removed. You will no longer receive Abyss reminders.",
        ephemeral=True
    )

@bot.tree.command(name="removeevent", description="Remove an existing event")
async def removeevent(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    events = db_get_events()
    if not events:
        return await inter.response.send_message("❌ No events available.", ephemeral=True)

    options = [
        discord.SelectOption(
            label=f"{name} ({dt})",
            value=str(event_id)
        )
        for event_id, name, dt, rem in events
    ]

    select = Select(
        placeholder="Select an event to remove",
        options=options
    )

    async def select_callback(i: discord.Interaction):
        event_id = int(select.values[0])
        db_delete_event(event_id)
        await i.response.send_message(
            "🗑️ Event removed successfully.",
            ephemeral=True
        )

    select.callback = select_callback
    view = View()
    view.add_item(select)

    await inter.response.send_message(
        "Select an event to remove:",
        view=view,
        ephemeral=True
    )


# ============================================================
# ABYSS CONFIG COMMAND
# ============================================================
class AbyssConfigView(View):
    def __init__(self, days, hours, rem, round2):
        super().__init__(timeout=300)
        self.days = days
        self.hours = hours
        self.rem = rem
        self.round2 = round2

        self.day_sel = Select(
            placeholder="Select Abyss Days",
            min_values=1,
            max_values=7,
            options=[
                discord.SelectOption(
                    label=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i],
                    value=str(i),
                    default=(i in days)
                )
                for i in range(7)
            ]
        )
        self.day_sel.callback = self.cb_days
        self.add_item(self.day_sel)

        self.hour_sel = Select(
            placeholder="Select Abyss Hours",
            min_values=1,
            max_values=6,
            options=[
                discord.SelectOption(
                    label=f"{h:02}:00 UTC",
                    value=str(h),
                    default=(h in hours)
                )
                for h in [0,4,8,12,16,20]
            ]
        )
        self.hour_sel.callback = self.cb_hours
        self.add_item(self.hour_sel)

        self.rem_sel = Select(
            placeholder="Reminder Hours",
            min_values=0,
            max_values=len(hours),
            options=[
                discord.SelectOption(
                    label=f"{h:02}:00 UTC",
                    value=str(h),
                    default=(h in rem)
                )
                for h in hours
            ]
        )
        self.rem_sel.callback = self.cb_rem
        self.add_item(self.rem_sel)

        self.round_btn = Button(
            label=f"Round 2: {'ON' if round2 else 'OFF'}",
            style=discord.ButtonStyle.success if round2 else discord.ButtonStyle.danger
        )
        self.round_btn.callback = self.toggle_round2
        self.add_item(self.round_btn)

    async def cb_days(self, interaction):
        global ABYSS_DAYS
        self.days = [int(v) for v in self.day_sel.values]
        ABYSS_DAYS = self.days
        cfg["days"] = self.days
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message("Days updated ✔", ephemeral=True)

    async def cb_hours(self, interaction):
        global ABYSS_HOURS
        self.hours = [int(v) for v in self.hour_sel.values]
        ABYSS_HOURS = self.hours
        cfg["hours"] = self.hours
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message("Hours updated ✔", ephemeral=True)

    async def cb_rem(self, interaction):
        global REMINDER_HOURS
        self.rem = [int(v) for v in self.rem_sel.values]
        REMINDER_HOURS = self.rem
        cfg["reminder_hours"] = self.rem
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message("Reminder hours updated ✔", ephemeral=True)

    async def toggle_round2(self, interaction):
        global ROUND2_ENABLED
        self.round2 = not self.round2
        ROUND2_ENABLED = self.round2
        cfg["round2"] = self.round2
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message(
            f"Round 2 {'enabled' if self.round2 else 'disabled'} ✔",
            ephemeral=True
        )



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

    # Abyss start reminder
    if now.hour in REMINDER_HOURS and now.minute == 0:
        embed = discord.Embed(
            title="🕒 Abyss Reminder",
            description="Abyss starts in **15 minutes**!",
            color=0xE74C3C
        )
        await dm_abyss_role(bot, embed)

    # Round 2 reminder
    if ROUND2_ENABLED and now.hour in REMINDER_HOURS and now.minute == 30:
        embed = discord.Embed(
            title="🕒 Abyss Reminder",
            description="Round 2 starts in **15 minutes**!",
            color=0xF1C40F
        )
        await dm_abyss_role(bot, embed)

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

        # Delete events 1 hour after they pass
        if now >= dt_obj + timedelta(hours=1):
            db_delete_event(event_id)
            continue

        # Reminder logic (robust, restart-safe)
        if rem > 0:
            rtime = (dt_obj - timedelta(minutes=rem)).replace(
                second=0,
                microsecond=0
            )

            if now >= rtime and event_id not in sent_custom:
                await ch.send(
                    f"⏰ Reminder: **{name}** in {rem} minutes! "
                    f"<t:{int(dt_obj.timestamp())}:F>"
                )
                sent_custom.add(event_id)

    # Prevent memory growth
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

    while True:
        try:
            await bot.start(token)
            break

        except discord.HTTPException as e:
            if e.status == 429:
                # HARD COOLDOWN on rate limit
                print("⛔ Discord rate-limited login. Cooling down for 15 minutes.")
                await asyncio.sleep(900)  # 15 minutes
            else:
                print(f"[Login Error] {e}")
                await asyncio.sleep(60)

        except Exception as e:
            print(f"[Fatal Login Error] {e}")
            await asyncio.sleep(120)

if __name__ == "__main__":
    asyncio.run(safe_login())

    # KEEP PROCESS ALIVE (REQUIRED FOR KOYEB)
    import time
    while True:
        time.sleep(3600)






























