import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import pytz
from datetime import datetime, timedelta, date, time
from discord.ui import View, Select, Button, Modal, TextInput
import io
import zipfile

# ============================================================
# CONFIG
# ============================================================

MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490

CUSTOM_FILE = "custom_events.json"
ABYSS_CONFIG_FILE = "abyss_config.json"

# ============================================================
# SAFE CONFIG LOADER (CRASH-PROOF)
# ============================================================

DEFAULT_ABYSS = {
    "days": [1, 4, 6],                # Tue, Fri, Sun
    "hours": [0, 4, 8, 12, 16, 20],   # Default Abyss hours
    "reminder_hours": [0, 4, 8, 12, 16, 20],
    "round2": True
}

def load_or_reset_abyss_config():
    """Loads abyss_config.json or regenerates it if corrupted."""
    try:
        with open(ABYSS_CONFIG_FILE, "r") as f:
            data = json.load(f)

        # If ANY field is missing → reset the entire file
        for key in DEFAULT_ABYSS:
            if key not in data:
                raise KeyError

        return data

    except:
        # Write a clean new config file
        with open(ABYSS_CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_ABYSS, f, indent=2)
        return DEFAULT_ABYSS.copy()

# Load into globals
cfg = load_or_reset_abyss_config()

ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
ROUND2_ENABLED = cfg["round2"]

# ============================================================
# HELPERS — FILE HANDLING
# ============================================================

def ensure_file_exists(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=2)

def load_json(path, default):
    ensure_file_exists(path, default)
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ============================================================
# CUSTOM EVENTS LOADER
# ============================================================

ensure_file_exists(CUSTOM_FILE, [])

def load_custom_events():
    return load_json(CUSTOM_FILE, [])

def save_custom_events(data):
    save_json(CUSTOM_FILE, data)

# ============================================================
# DISCORD SETUP
# ============================================================

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_flows = {}      # For editing custom events
sent_custom_reminders = set()   # For preventing duplicate reminders

def parse_datetime(input_str: str) -> datetime:
    """Parse either 'DD-MM-YYYY HH:MM' or relative '1d 2h 30m'."""
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except ValueError:
        pass
    now = datetime.utcnow()
    d = h = m = 0
    for part in input_str.split():
        if part.endswith("d"): d = int(part[:-1])
        elif part.endswith("h"): h = int(part[:-1])
        elif part.endswith("m"): m = int(part[:-1])
    return now + timedelta(days=d, hours=h, minutes=m)

def has_admin(inter):
    return (
        inter.user.id == OWNER_ID or
        any(r.permissions.administrator for r in inter.user.roles)
    )

async def log_action(msg: str):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(msg)

# ============================================================
# READY EVENT
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands globally")
    except Exception as e:
        print("Sync Failed:", e)

    # Start loops
    abyss_reminder_loop.start()
    custom_event_loop.start()

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Bot updated and online!")

# ============================================================
# WEEKLY EVENT COMMAND
# ============================================================

weekly_events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯",
}

start_date = date(2025, 9, 16)

@bot.tree.command(name="weeklyevent", description="Check the next 4 weekly Abyss events")
async def weeklyevent(inter):
    today = date.today()
    start_sunday = start_date - timedelta(days=start_date.weekday() + 1)
    weeks_passed = (today - start_sunday).days // 7

    this_week_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
    now = datetime.utcnow()

    event_start = datetime.combine(this_week_tuesday, time(0, 0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks_passed += 1
        this_week_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
        event_start = datetime.combine(this_week_tuesday, time(0, 0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i in range(4):
        idx = (weeks_passed + i) % len(weekly_events)
        name = weekly_events[idx]
        emoji = event_emojis.get(name, "📌")

        ev_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        base_dt = datetime.combine(ev_date, time(0, 0))

        if i == 0 and event_start <= now < event_end:
            left = event_end - now
            status = f"🟢 LIVE NOW (ends in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m)"
        else:
            left = base_dt - now
            status = f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"

        msg += f"{numbers[i]} {emoji} **{name}** — <t:{int(base_dt.timestamp())}:F>\n{status}\n\n"

    await inter.response.send_message(msg)

# ============================================================
# /abyssconfig UI
# ============================================================

@bot.tree.command(name="abyssconfig", description="Configure Abyss hours & days")
async def abyssconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    # Build UI view
    view = View()

    # ---------------- DAY SELECT ----------------
    day_select = Select(
        placeholder="Select Abyss Days (0=Mon..6=Sun)",
        min_values=1,
        max_values=7,
        options=[
            discord.SelectOption(label="Monday", value="0"),
            discord.SelectOption(label="Tuesday", value="1"),
            discord.SelectOption(label="Wednesday", value="2"),
            discord.SelectOption(label="Thursday", value="3"),
            discord.SelectOption(label="Friday", value="4"),
            discord.SelectOption(label="Saturday", value="5"),
            discord.SelectOption(label="Sunday", value="6"),
        ]
    )
    day_select.default_values = [str(d) for d in ABYSS_DAYS]

    async def day_cb(i):
        day_select.default_values = day_select.values
        await i.response.defer()

    day_select.callback = day_cb
    view.add_item(day_select)

    # ---------------- HOUR SELECT ----------------
    hour_select = Select(
        placeholder="Select Abyss Hours (UTC)",
        min_values=1,
        max_values=24,
        options=[discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in range(24)]
    )
    hour_select.default_values = [str(h) for h in ABYSS_HOURS]

    async def hour_cb(i):
        hour_select.default_values = hour_select.values
        await i.response.defer()

    hour_select.callback = hour_cb
    view.add_item(hour_select)

    # ---------------- REMINDER HOUR SELECT ----------------
    reminder_select = Select(
        placeholder="Select Reminder Hours",
        min_values=0,
        max_values=24,
        options=[discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in ABYSS_HOURS]
    )
    reminder_select.default_values = [str(h) for h in REMINDER_HOURS]

    async def rem_cb(i):
        reminder_select.default_values = reminder_select.values
        await i.response.defer()

    reminder_select.callback = rem_cb
    view.add_item(reminder_select)

    # ---------------- ROUND 2 SELECT ----------------
    round2_select = Select(
        placeholder="Enable Round 2?",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Enabled", value="true"),
            discord.SelectOption(label="Disabled", value="false")
        ]
    )
    round2_select.default_values = ["true" if ROUND2_ENABLED else "false"]

    async def r2_cb(i):
        round2_select.default_values = round2_select.values
        await i.response.defer()

    round2_select.callback = r2_cb
    view.add_item(round2_select)

    # ---------------- SAVE BUTTON ----------------
    @discord.ui.button(label="Save", style=discord.ButtonStyle.green)
    async def save_btn(btn, i):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg

        ABYSS_DAYS = [int(v) for v in day_select.default_values]
        ABYSS_HOURS = [int(v) for v in hour_select.default_values]
        REMINDER_HOURS = [int(v) for v in reminder_select.default_values]
        ROUND2_ENABLED = (round2_select.default_values[0] == "true")

        cfg = {
            "days": ABYSS_DAYS,
            "hours": ABYSS_HOURS,
            "reminder_hours": REMINDER_HOURS,
            "round2": ROUND2_ENABLED,
        }

        save_json(ABYSS_CONFIG_FILE, cfg)

        await i.response.send_message("✅ **Abyss Config Saved!**", ephemeral=True)

    view.add_item(save_btn)

    # Embed Summary
    embed = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
    embed.add_field(name="Days", value=str(ABYSS_DAYS), inline=False)
    embed.add_field(name="Hours", value=str(ABYSS_HOURS), inline=False)
    embed.add_field(name="Reminder Hours", value=str(REMINDER_HOURS), inline=False)
    embed.add_field(name="Round 2 Enabled", value=str(ROUND2_ENABLED), inline=False)

    await inter.response.send_message(embed=embed, view=view, ephemeral=True)

# END OF PART 1
# ============================================================
# CUSTOM EVENT COMMANDS (KVK SYSTEM)
# ============================================================

@bot.tree.command(name="kvkevent", description="Show next 4 upcoming custom events")
async def kvkevent(inter):
    now = datetime.utcnow()
    events = load_custom_events()

    # sort by datetime
    def to_dt(ev):
        return datetime.fromisoformat(ev["datetime"])

    events_sorted = sorted(events, key=to_dt)
    upcoming = []

    for ev in events_sorted:
        dt = datetime.fromisoformat(ev["datetime"])
        if dt <= now < dt + timedelta(hours=1):
            upcoming.append((ev["name"], dt, "live"))
        elif dt > now:
            upcoming.append((ev["name"], dt, "upcoming"))

        if len(upcoming) == 4:
            break

    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    msg = "📅 **Upcoming Events**\n\n"
    icons = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i, (name, dt, status) in enumerate(upcoming):
        if status == "live":
            left = (dt + timedelta(hours=1)) - now
            mins = max(1, left.seconds // 60)
            state = f"🟢 LIVE (ends in ~{mins}m)"
        else:
            left = dt - now
            state = f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"

        msg += f"{icons[i]} **{name}** — <t:{int(dt.timestamp())}:F>\n{state}\n\n"

    await inter.response.send_message(msg)

# ============================================================
# ADD EVENT (MODAL)
# ============================================================

class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name")
    dt_input = TextInput(label="Datetime (UTC)", placeholder="DD-MM-YYYY HH:MM or 1d 2h")
    reminder = TextInput(label="Reminder (minutes or 'no')", placeholder="10")

    async def on_submit(self, inter):
        try:
            dt = parse_datetime(self.dt_input.value)

            if self.reminder.value.lower() == "no":
                rem = 0
            else:
                rem = int(self.reminder.value)

            event = {
                "name": self.name.value,
                "datetime": dt.isoformat(),
                "reminder": rem
            }

            evs = load_custom_events()
            evs.append(event)
            save_custom_events(evs)

            await inter.response.send_message(
                f"✅ Added **{event['name']}** at <t:{int(dt.timestamp())}:F>",
                ephemeral=True
            )

            await log_action(f"📝 Event Added: {event}")
        except Exception as e:
            await inter.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="addevent", description="Add custom event")
async def addevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)
    await inter.response.send_modal(AddEventModal())

# ============================================================
# EDIT EVENT
# ============================================================

@bot.tree.command(name="editevent", description="Edit a custom event")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    evs = load_custom_events()
    if not evs:
        return await inter.response.send_message("No events to edit.", ephemeral=True)

    class SelectEvent(Select):
        def __init__(self):
            options = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                )
                for i, e in enumerate(evs)
            ]
            super().__init__(placeholder="Choose event to edit", options=options)

        async def callback(self, i2):
            idx = int(self.values[0])
            active_flows[inter.user.id] = {"idx": idx}

            class EditMenu(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(btn, i3):
                    flow = active_flows[inter.user.id]
                    flow["field"] = "name"
                    await i3.response.send_message("Enter new name:", ephemeral=True)

                @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.secondary)
                async def edit_time(btn, i3):
                    flow = active_flows[inter.user.id]
                    flow["field"] = "datetime"
                    await i3.response.send_message("Enter new datetime (UTC):", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_reminder(btn, i3):
                    flow = active_flows[inter.user.id]
                    flow["field"] = "reminder"
                    await i3.response.send_message("Enter reminder minutes or 'no':", ephemeral=True)

            await i2.response.send_message("Choose field:", view=EditMenu(), ephemeral=True)

    view = View()
    view.add_item(SelectEvent())
    await inter.response.send_message("Select event:", view=view, ephemeral=True)

# ============================================================
# REMOVE EVENT
# ============================================================

@bot.tree.command(name="removeevent", description="Delete a custom event")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    evs = load_custom_events()
    if not evs:
        return await inter.response.send_message("No events to delete.", ephemeral=True)

    class SelectRemove(Select):
        def __init__(self):
            options = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                )
                for i, e in enumerate(evs)
            ]
            super().__init__(placeholder="Select event to delete", options=options)

        async def callback(self, i2):
            idx = int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(btn, i3):
                    ev_list = load_custom_events()
                    if 0 <= idx < len(ev_list):
                        removed = ev_list.pop(idx)
                        save_custom_events(ev_list)
                        await i3.response.send_message(f"🗑 Removed **{removed['name']}**")
                        await log_action(f"🗑 Event Removed: {removed}")
                    else:
                        await i3.response.send_message("❌ Invalid index.")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(btn, i3):
                    await i3.response.send_message("❌ Cancelled.", ephemeral=True)

            await i2.response.send_message("Confirm deletion:", view=Confirm(), ephemeral=True)

    view = View()
    view.add_item(SelectRemove())
    await inter.response.send_message("Choose event to delete:", view=view, ephemeral=True)

# ============================================================
# ON_MESSAGE HANDLER (FIXED & SAFE)
# ============================================================

@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    uid = msg.author.id
    if uid not in active_flows:
        return

    flow = active_flows[uid]
    idx = flow["idx"]
    field = flow["field"]

    evs = load_custom_events()

    # Out-of-range safety
    if not (0 <= idx < len(evs)):
        del active_flows[uid]
        return

    # ---------------- Edit Name ----------------
    if field == "name":
        evs[idx]["name"] = msg.content
        save_custom_events(evs)
        await msg.channel.send("✅ Name updated.")
        del active_flows[uid]
        return

    # ---------------- Edit Datetime ----------------
    if field == "datetime":
        try:
            evs[idx]["datetime"] = parse_datetime(msg.content).isoformat()
        except:
            await msg.channel.send("❌ Invalid datetime. Edit cancelled.")
            del active_flows[uid]
            return

        save_custom_events(evs)
        await msg.channel.send("✅ Datetime updated.")
        del active_flows[uid]
        return

    # ---------------- Edit Reminder ----------------
    if field == "reminder":
        try:
            if msg.content.lower() == "no":
                evs[idx]["reminder"] = 0
            else:
                value = int(msg.content)
                if value < 0:
                    raise ValueError
                evs[idx]["reminder"] = value
        except:
            await msg.channel.send("❌ Reminder must be a number (or 'no'). Edit cancelled.")
            del active_flows[uid]
            return

        save_custom_events(evs)
        await msg.channel.send("✅ Reminder updated.")
        del active_flows[uid]
        return

# ============================================================
# EXPORT / IMPORT CONFIG
# ============================================================

@bot.tree.command(name="exportconfig", description="Export Abyss + Events config")
async def exportconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ABYSS_CONFIG_FILE)
        z.write(CUSTOM_FILE)

    mem.seek(0)
    await inter.response.send_message(
        "📦 Exported configuration.",
        file=discord.File(mem, filename="config.zip"),
        ephemeral=True
    )


# END OF PART 2
# ============================================================
# IMPORT CONFIG
# ============================================================

def strict_validate_events(d):
    if not isinstance(d, list):
        return False
    for ev in d:
        if not isinstance(ev, dict):
            return False
        if "name" not in ev or "datetime" not in ev or "reminder" not in ev:
            return False
    return True

def strict_validate_abyss(d):
    return all(k in d for k in ["days", "hours", "reminder_hours", "round2"])

def soft_validate_abyss(d):
    out = {}
    if "days" in d: out["days"] = [int(x) for x in d["days"]]
    if "hours" in d: out["hours"] = [int(x) for x in d["hours"]]
    if "reminder_hours" in d: out["reminder_hours"] = [int(x) for x in d["reminder_hours"]]
    if "round2" in d: out["round2"] = bool(d["round2"])
    return out

@bot.tree.command(name="importconfig", description="Import zipper config")
async def importconfig(inter, file: discord.Attachment):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    if not file.filename.endswith(".zip"):
        return await inter.response.send_message("❌ Upload a ZIP file.", ephemeral=True)

    raw = await file.read()
    mem_zip = io.BytesIO(raw)

    try:
        z = zipfile.ZipFile(mem_zip)
    except:
        return await inter.response.send_message("❌ Invalid ZIP file.", ephemeral=True)

    events_data = None
    abyss_data = None

    for name in z.namelist():
        if name == CUSTOM_FILE:
            try: events_data = json.loads(z.read(name))
            except: pass
        if name == ABYSS_CONFIG_FILE:
            try: abyss_data = json.loads(z.read(name))
            except: pass

    # Strict Import
    if events_data and abyss_data:
        if strict_validate_events(events_data) and strict_validate_abyss(abyss_data):
            save_custom_events(events_data)
            save_json(ABYSS_CONFIG_FILE, abyss_data)

            global cfg, ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED
            cfg = abyss_data
            ABYSS_DAYS = cfg["days"]
            ABYSS_HOURS = cfg["hours"]
            REMINDER_HOURS = cfg["reminder_hours"]
            ROUND2_ENABLED = cfg["round2"]

            return await inter.response.send_message("✅ Strict import complete.", ephemeral=True)

    # Soft Import
    imported = []

    if events_data:
        save_custom_events(events_data)
        imported.append("• Events")

    if abyss_data:
        soft = soft_validate_abyss(abyss_data)
        cfg.update(soft)
        save_json(ABYSS_CONFIG_FILE, cfg)

        ABYSS_DAYS = cfg["days"]
        ABYSS_HOURS = cfg["hours"]
        REMINDER_HOURS = cfg["reminder_hours"]
        ROUND2_ENABLED = cfg["round2"]

        imported.append("• Abyss Config")

    if not imported:
        return await inter.response.send_message("⚠ No valid data found.", ephemeral=True)

    await inter.response.send_message(
        "⚠ Soft import completed:\n" + "\n".join(imported),
        ephemeral=True
    )

# ============================================================
# ABYSS REMINDER SYSTEM
# ============================================================

@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    # Only on selected days
    if now.weekday() not in ABYSS_DAYS:
        return

    ch = bot.get_channel(channel_id)
    if not ch:
        return

    # Round 1 — reminder at exact selected hours
    if now.hour in REMINDER_HOURS and now.minute == 0:
        await ch.send(f"<@&1413532222396301322>, Abyss will start in 15 minutes! (at {now.hour:02}:00 UTC)")

    # Round 2 — 30 minutes later
    if ROUND2_ENABLED:
        if now.hour in REMINDER_HOURS and now.minute == 30:
            await ch.send(f"<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes! (at {now.hour:02}:30 UTC)")

# ============================================================
# CUSTOM EVENT REMINDER LOOP
# ============================================================

@tasks.loop(minutes=1)
async def custom_event_loop():
    global sent_custom_reminders

    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(channel_id)
    if not ch:
        return

    events = load_custom_events()

    for ev in events:
        dt = datetime.fromisoformat(ev["datetime"])
        rem = ev["reminder"]

        if rem <= 0:
            continue

        remind_time = dt - timedelta(minutes=rem)
        key = (ev["name"], remind_time.isoformat())

        if remind_time <= now < remind_time + timedelta(minutes=1):
            if key not in sent_custom_reminders:
                await ch.send(f"⏰ Reminder: **{ev['name']}** starts in {rem} minutes! <t:{int(dt.timestamp())}:F>")
                sent_custom_reminders.add(key)

    if len(sent_custom_reminders) > 300:
        sent_custom_reminders = set(list(sent_custom_reminders)[-100:])

# ============================================================
# BOT RUNNER
# ============================================================

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ DISCORD_BOT_TOKEN is missing!")
else:
    bot.run(TOKEN)


