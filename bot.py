# ======================================
# ABYSS REMINDER BOT — FINAL VERSION
# PART 1 OF 3
# ======================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import json
import os
import io
import zipfile
from datetime import datetime, timedelta, date, time
from discord.ui import View, Button, Select, Modal, TextInput

# ================================
# CONFIG
# ================================
MY_TIMEZONE = "UTC"

channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490
GUILD_ID = 1328405638744641548

CUSTOM_FILE = "custom_events.json"
ABYSS_CONFIG_FILE = "abyss_config.json"

DEFAULT_ABYSS_DAYS = [1, 4, 6]  # Tue Fri Sun
DEFAULT_ABYSS_HOURS = [0, 4, 8, 12, 16, 20]
DEFAULT_REMINDER_HOURS = [8, 12, 16, 20]
DEFAULT_ROUND2 = True

# ================================
# DISCORD SETUP
# ================================
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================================
# STORAGE
# ================================
def load_custom_events():
    if not os.path.exists(CUSTOM_FILE):
        return []
    return json.load(open(CUSTOM_FILE, "r"))

def save_custom_events(events):
    json.dump(events, open(CUSTOM_FILE, "w"), indent=2)

def load_abyss_config():
    if not os.path.exists(ABYSS_CONFIG_FILE):
        return {
            "days": DEFAULT_ABYSS_DAYS,
            "hours": DEFAULT_ABYSS_HOURS,
            "reminder_hours": DEFAULT_REMINDER_HOURS,
            "round2": DEFAULT_ROUND2,
        }
    return json.load(open(ABYSS_CONFIG_FILE, "r"))

def save_abyss_config(cfg):
    json.dump(cfg, open(ABYSS_CONFIG_FILE, "w"), indent=2)

cfg = load_abyss_config()
ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
ROUND2_ENABLED = cfg["round2"]

# ================================
# HELPERS
# ================================
def parse_datetime(input_str):
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except:
        pass

    now = datetime.utcnow()
    d = h = m = 0
    for part in input_str.split():
        if part.endswith("d"):
            d = int(part[:-1])
        elif part.endswith("h"):
            h = int(part[:-1])
        elif part.endswith("m"):
            m = int(part[:-1])

    return now + timedelta(days=d, hours=h, minutes=m)


def has_admin(inter):
    if inter.user.id == OWNER_ID:
        return True
    return any(r.name.lower() == "admin" for r in inter.user.roles)


async def log(msg):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(msg)

# ================================
# /ABYSSCONFIG (UI)
# ================================
class DaySelect(Select):
    def __init__(self, selected_days):
        days_map = [
            ("Monday",0),("Tuesday",1),("Wednesday",2),
            ("Thursday",3),("Friday",4),("Saturday",5),("Sunday",6)
        ]
        options = [
            discord.SelectOption(
                label=name,
                value=str(num),
                default=(num in selected_days)
            ) for name, num in days_map
        ]
        super().__init__(
            placeholder="Select Abyss Days",
            min_values=1,
            max_values=7,
            options=options
        )

    async def callback(self, inter):
        cfg["days"] = [int(v) for v in self.values]
        save_abyss_config(cfg)
        await inter.response.edit_message(view=build_abyssconfig_view())


class HourSelect(Select):
    def __init__(self, selected_hours):
        options = [
            discord.SelectOption(
                label=f"{h:02d}:00",
                value=str(h),
                default=(h in selected_hours)
            ) for h in range(24)
        ]
        super().__init__(
            placeholder="Select Abyss Hours",
            min_values=1,
            max_values=24,
            options=options
        )

    async def callback(self, inter):
        cfg["hours"] = [int(v) for v in self.values]
        save_abyss_config(cfg)
        await inter.response.edit_message(view=build_abyssconfig_view())


class ReminderHourSelect(Select):
    def __init__(self, abyss_hours, selected):
        options = [
            discord.SelectOption(
                label=f"{h:02d}:00",
                value=str(h),
                default=(h in selected)
            ) for h in abyss_hours
        ]
        super().__init__(
            placeholder="Select Reminder Hours",
            min_values=0,
            max_values=len(abyss_hours),
            options=options
        )

    async def callback(self, inter):
        cfg["reminder_hours"] = [int(v) for v in self.values]
        save_abyss_config(cfg)
        await inter.response.edit_message(view=build_abyssconfig_view())


class Round2Select(Select):
    def __init__(self, state):
        options = [
            discord.SelectOption(label="Enabled", value="1", default=state),
            discord.SelectOption(label="Disabled", value="0", default=not state)
        ]
        super().__init__(placeholder="Round 2 Mode", min_values=1, max_values=1, options=options)

    async def callback(self, inter):
        cfg["round2"] = (self.values[0] == "1")
        save_abyss_config(cfg)
        await inter.response.edit_message(view=build_abyssconfig_view())


def build_abyssconfig_view():
    view = View()
    view.add_item(DaySelect(cfg["days"]))
    view.add_item(HourSelect(cfg["hours"]))
    view.add_item(ReminderHourSelect(cfg["hours"], cfg["reminder_hours"]))
    view.add_item(Round2Select(cfg["round2"]))
    return view


@bot.tree.command(name="abyssconfig", description="Configure Abyss schedule.")
async def abyssconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    embed = discord.Embed(
        title="⚙️ Abyss Configuration",
        color=discord.Color.gold()
    )
    embed.add_field(name="Days", value=str(cfg["days"]), inline=False)
    embed.add_field(name="Hours", value=str(cfg["hours"]), inline=False)
    embed.add_field(name="Reminder Hours", value=str(cfg["reminder_hours"]), inline=False)
    embed.add_field(name="Round 2", value=str(cfg["round2"]), inline=False)

    await inter.response.send_message(
        embed=embed,
        view=build_abyssconfig_view(),
        ephemeral=True
    )
# ======================================
# ABYSS REMINDER BOT — FINAL VERSION
# PART 2 OF 3
# ======================================

# ================================
# ABYSS REMINDER ENGINE
# ================================
@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    ch = bot.get_channel(channel_id)

    # ---- 1. MAIN ABYSS REMINDERS ----
    if now.weekday() in cfg["days"]:
        if now.hour in cfg["reminder_hours"] and now.minute == 0:
            if ch:
                await ch.send(
                    f"<@&1413532222396301322>, Abyss will start in 15 minutes!"
                )

        # ---- 2. ROUND 2 ----
        if cfg["round2"]:
            if now.hour in cfg["reminder_hours"] and now.minute == 30:
                if ch:
                    await ch.send(
                        f"<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes!"
                    )

# ================================
# CUSTOM EVENT REMINDERS
# ================================
@tasks.loop(minutes=1)
async def event_reminder_loop():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(channel_id)
    events = load_custom_events()

    for ev in events:
        dt = datetime.fromisoformat(ev["datetime"])
        rem = ev.get("reminder", 0)

        if rem <= 0:
            continue

        remind_time = dt - timedelta(minutes=rem)

        if remind_time <= now < remind_time + timedelta(minutes=1):
            await ch.send(
                f"⏰ Reminder: **{ev['name']}** starts in {rem} minutes! <t:{int(dt.timestamp())}:F>"
            )

# ================================
# SYNC + START LOOPS
# ================================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"🌍 Global: {len(synced)} commands")
    except Exception as e:
        print("Sync error:", e)

    abyss_reminder_loop.start()
    event_reminder_loop.start()

    log_ch = bot.get_channel(update_channel_id)
    if log_ch:
        await log_ch.send("🤖 Abyss Reminder Bot Updated & Online!")

# ================================
# WEEKLY EVENTS
# ================================
weekly_events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
start_date = date(2025, 9, 16)

event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯",
}

@bot.tree.command(name="weeklyevent", description="Show upcoming weekly Abyss events.")
async def weeklyevent(inter):
    today = date.today()
    start_sunday = start_date - timedelta(days=start_date.weekday() + 1)
    weeks_passed = (today - start_sunday).days // 7

    this_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
    now = datetime.utcnow()
    event_start = datetime.combine(this_tuesday, time(0, 0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks_passed += 1
        this_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
        event_start = datetime.combine(this_tuesday, time(0, 0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i in range(4):
        idx = (weeks_passed + i) % 4
        event_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        name = weekly_events[idx]
        emoji = event_emojis[name]

        dt = datetime.combine(event_date, time(0, 0))
        delta = dt - now
        status = f"⏳ {delta.days}d {delta.seconds//3600}h"

        msg += f"{nums[i]} {emoji} **{name}** — <t:{int(dt.timestamp())}:F>\n{status}\n\n"

    await inter.response.send_message(msg)

# ================================
# KVK EVENTS
# ================================
@bot.tree.command(name="kvkevent", description="Show next 4 custom events.")
async def kvkevent(inter):
    now = datetime.utcnow()
    events = load_custom_events()
    events_sorted = sorted(events, key=lambda e: datetime.fromisoformat(e["datetime"]))

    upcoming = []
    for ev in events_sorted:
        dt = datetime.fromisoformat(ev["datetime"])
        if dt > now:
            upcoming.append(ev)
        if len(upcoming) == 4:
            break

    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    msg = "📅 **Upcoming Events**\n\n"
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i, ev in enumerate(upcoming):
        dt = datetime.fromisoformat(ev["datetime"])
        delta = dt - now
        msg += (
            f"{nums[i]} **{ev['name']}** — <t:{int(dt.timestamp())}:F>\n"
            f"⏳ {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m\n\n"
        )

    await inter.response.send_message(msg)

# ================================
# ADD EVENT
# ================================
class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name")
    datetime_input = TextInput(label="Datetime (UTC)", placeholder="DD-MM-YYYY HH:MM or 1d 2h")
    reminder = TextInput(label="Reminder Minutes", placeholder="10")

    async def on_submit(self, inter):
        try:
            dt = parse_datetime(self.datetime_input.value)
            rem = 0 if self.reminder.value.lower() == "no" else int(self.reminder.value)

            new_ev = {
                "name": self.name.value,
                "datetime": dt.isoformat(),
                "reminder": rem,
            }

            events = load_custom_events()
            events.append(new_ev)
            save_custom_events(events)

            await inter.response.send_message(
                f"✅ Added **{new_ev['name']}** (<t:{int(dt.timestamp())}:F>)",
                ephemeral=True
            )

        except Exception as e:
            await inter.response.send_message(f"❌ {e}", ephemeral=True)

@bot.tree.command(name="addevent", description="Add a custom event.")
async def addevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)
    await inter.response.send_modal(AddEventModal())

# ================================
# EDIT EVENT
# ================================
active_flows = {}

@bot.tree.command(name="editevent", description="Edit a custom event.")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    events = load_custom_events()
    if not events:
        return await inter.response.send_message("No events found.", ephemeral=True)

    uid = inter.user.id

    class SelectEvent(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                ) for i, e in enumerate(events)
            ]
            super().__init__(placeholder="Choose event", options=opts)

        async def callback(self, i2):
            idx = int(self.values[0])
            active_flows[uid] = {"idx": idx, "field": ""}

            class EditMenu(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self, btn, i3):
                    active_flows[uid]["field"] = "name"
                    await i3.response.send_message("Enter new name:", ephemeral=True)

                @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.secondary)
                async def edit_dt(self, btn, i3):
                    active_flows[uid]["field"] = "datetime"
                    await i3.response.send_message("Enter new datetime:", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_rm(self, btn, i3):
                    active_flows[uid]["field"] = "reminder"
                    await i3.response.send_message("Enter new reminder minutes:", ephemeral=True)

            await i2.response.send_message("Choose field:", view=EditMenu(), ephemeral=True)

    view = View()
    view.add_item(SelectEvent())
    await inter.response.send_message("Choose an event to edit:", view=view, ephemeral=True)

# ================================
# ON_MESSAGE: Apply event edits
# ================================
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    if msg.author.id not in active_flows:
        return

    flow = active_flows[msg.author.id]
    idx = flow["idx"]
    field = flow["field"]

    events = load_custom_events()
    if not (0 <= idx < len(events)):
        del active_flows[msg.author.id]
        return

    if field == "datetime":
        events[idx]["datetime"] = parse_datetime(msg.content).isoformat()
    elif field == "reminder":
        events[idx]["reminder"] = int(msg.content)
    else:
        events[idx]["name"] = msg.content

    save_custom_events(events)
    del active_flows[msg.author.id]
    await msg.channel.send("✅ Event updated.")
# ======================================
# ABYSS REMINDER BOT — FINAL VERSION
# PART 3 OF 3
# ======================================

# ================================
# EXPORT CONFIG
# ================================
@bot.tree.command(name="exportconfig", description="Export all Abyss & Event settings.")
async def exportconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(CUSTOM_FILE):
            z.write(CUSTOM_FILE)
        if os.path.exists(ABYSS_CONFIG_FILE):
            z.write(ABYSS_CONFIG_FILE)

    mem.seek(0)
    await inter.response.send_message(
        "📦 **Configuration Exported**",
        file=discord.File(mem, filename="config.zip"),
        ephemeral=True
    )

# ================================
# VALIDATION HELPERS
# ================================
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
    return (
        "days" in d and
        "hours" in d and
        "reminder_hours" in d and
        "round2" in d
    )

def soft_validate_abyss(d):
    out = {}
    if "days" in d:
        out["days"] = [int(x) for x in d["days"]]
    if "hours" in d:
        out["hours"] = [int(x) for x in d["hours"]]
    if "reminder_hours" in d:
        out["reminder_hours"] = [int(x) for x in d["reminder_hours"]]
    if "round2" in d:
        out["round2"] = bool(d["round2"])
    return out

# ================================
# IMPORT CONFIG
# ================================
@bot.tree.command(name="importconfig", description="Import settings from config.zip")
async def importconfig(inter, file: discord.Attachment):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    if not file.filename.endswith(".zip"):
        return await inter.response.send_message("❌ Upload a .zip file.", ephemeral=True)

    raw = await file.read()
    mem_zip = io.BytesIO(raw)

    try:
        z = zipfile.ZipFile(mem_zip)
    except:
        return await inter.response.send_message("❌ Invalid ZIP.", ephemeral=True)

    events_data = None
    abyss_data = None

    for name in z.namelist():
        if name == CUSTOM_FILE:
            try:
                events_data = json.loads(z.read(name))
            except:
                pass
        if name == ABYSS_CONFIG_FILE:
            try:
                abyss_data = json.loads(z.read(name))
            except:
                pass

    # STRICT IMPORT
    if events_data and abyss_data:
        if strict_validate_events(events_data) and strict_validate_abyss(abyss_data):
            save_custom_events(events_data)
            save_abyss_config(abyss_data)

            global cfg, ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED
            cfg = abyss_data
            ABYSS_DAYS = cfg["days"]
            ABYSS_HOURS = cfg["hours"]
            REMINDER_HOURS = cfg["reminder_hours"]
            ROUND2_ENABLED = cfg["round2"]

            return await inter.response.send_message("✅ Strict import complete.", ephemeral=True)

    # SOFT IMPORT
    imported = []
    if events_data:
        save_custom_events(events_data)
        imported.append("• custom_events.json (soft)")

    if abyss_data:
        soft = soft_validate_abyss(abyss_data)
        cfg.update(soft)
        save_abyss_config(cfg)

        ABYSS_DAYS = cfg["days"]
        ABYSS_HOURS = cfg["hours"]
        REMINDER_HOURS = cfg["reminder_hours"]
        ROUND2_ENABLED = cfg["round2"]

        imported.append("• abyss_config.json (soft)")

    if not imported:
        return await inter.response.send_message("❌ Nothing importable.", ephemeral=True)

    await inter.response.send_message(
        "⚠️ Soft import completed:\n" + "\n".join(imported),
        ephemeral=True
    )

# ================================
# REMOVE EVENT
# ================================
@bot.tree.command(name="removeevent", description="Delete a custom event.")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    events = load_custom_events()
    if not events:
        return await inter.response.send_message("No events found.", ephemeral=True)

    class SelectRemove(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                )
                for i, e in enumerate(events)
            ]

            super().__init__(placeholder="Select event to delete", options=opts)

        async def callback(self, i2):
            idx = int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(self_btn, i3):
                    evs = load_custom_events()
                    if 0 <= idx < len(evs):
                        ev = evs.pop(idx)
                        save_custom_events(evs)
                        await i3.response.send_message(f"🗑 Deleted **{ev['name']}**")
                    else:
                        await i3.response.send_message("❌ Index error.")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(self_btn, i3):
                    await i3.response.send_message("❌ Cancelled.", ephemeral=True)

            await i2.response.send_message(
                "Confirm deletion:",
                view=Confirm(),
                ephemeral=True
            )

    view = View()
    view.add_item(SelectRemove())
    await inter.response.send_message(
        "Choose an event to delete:",
        view=view,
        ephemeral=True
    )

# ================================
# RUN BOT
# ================================
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    print("❌ ERROR: DISCORD_BOT_TOKEN not set")
else:
    bot.run(TOKEN)
