# ======================================
# ABYSS REMINDER BOT — FINAL VERSION (PATCHED)
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
# BASIC CONFIG
# ================================
MY_TIMEZONE = "UTC"

channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490
GUILD_ID = 1328405638744641548

CUSTOM_FILE = "custom_events.json"
ABYSS_CONFIG_FILE = "abyss_config.json"

DEFAULT_ABYSS_DAYS = [1, 4, 6]  # Tue, Fri, Sun
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
# STORAGE HELPERS
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

# ================================
# SAFE CONFIG LOAD (PATCHED)
# ================================
cfg = load_abyss_config()

# auto-inject missing fields
if "reminder_hours" not in cfg:
    cfg["reminder_hours"] = DEFAULT_REMINDER_HOURS
if "round2" not in cfg:
    cfg["round2"] = DEFAULT_ROUND2

# write back corrected config
save_abyss_config(cfg)

ABYSS_DAYS = cfg.get("days", DEFAULT_ABYSS_DAYS)
ABYSS_HOURS = cfg.get("hours", DEFAULT_ABYSS_HOURS)
REMINDER_HOURS = cfg.get("reminder_hours", DEFAULT_REMINDER_HOURS)
ROUND2_ENABLED = cfg.get("round2", DEFAULT_ROUND2)

# ================================
# PARSE DATETIME HELPER
# ================================
def parse_datetime(text):
    try:
        return datetime.strptime(text, "%d-%m-%Y %H:%M")
    except:
        pass

    now = datetime.utcnow()
    d = h = m = 0

    for part in text.split():
        if part.endswith("d"):
            d = int(part[:-1])
        elif part.endswith("h"):
            h = int(part[:-1])
        elif part.endswith("m"):
            m = int(part[:-1])

    return now + timedelta(days=d, hours=h, minutes=m)

# ================================
# PERMISSION HELPER
# ================================
def has_admin(inter):
    if inter.user.id == OWNER_ID:
        return True
    return any(r.name.lower() == "admin" for r in inter.user.roles)

# ================================
# LOG HELPER
# ================================
async def log(msg):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(msg)

# ================================
# ======================================
# /abyssconfig (UI WITH SAVE BUTTON)
# ======================================
@bot.tree.command(name="abyssconfig", description="Configure Abyss reminder settings")
async def abyssconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    # Build UI
    view = View()

    # ----- DAY SELECT -----
    day_select = Select(
        placeholder="Select Abyss Days",
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

    # Preselect
    day_select.default_values = [str(d) for d in ABYSS_DAYS]

    async def day_callback(inter2):
        day_select.default_values = day_select.values
        await inter2.response.defer()

    day_select.callback = day_callback
    view.add_item(day_select)

    # ----- HOUR SELECT -----
    hour_select = Select(
        placeholder="Select Abyss Hours",
        min_values=1,
        max_values=24,
        options=[discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in range(24)]
    )

    hour_select.default_values = [str(h) for h in ABYSS_HOURS]

    async def hour_callback(inter2):
        hour_select.default_values = hour_select.values
        await inter2.response.defer()

    hour_select.callback = hour_callback
    view.add_item(hour_select)

    # ----- REMINDER HOURS (only hours selected above) -----
    reminder_select = Select(
        placeholder="Choose which hours will send the reminder",
        min_values=0,
        max_values=len(ABYSS_HOURS),
        options=[discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in ABYSS_HOURS]
    )

    reminder_select.default_values = [str(r) for r in REMINDER_HOURS]

    async def reminder_callback(inter2):
        reminder_select.default_values = reminder_select.values
        await inter2.response.defer()

    reminder_select.callback = reminder_callback
    view.add_item(reminder_select)

    # ----- ROUND 2 TOGGLE -----
    round2_select = Select(
        placeholder="Enable Round 2?",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Enabled", value="true"),
            discord.SelectOption(label="Disabled", value="false"),
        ]
    )

    round2_select.default_values = ["true" if ROUND2_ENABLED else "false"]

    async def round2_callback(inter2):
        round2_select.default_values = round2_select.values
        await inter2.response.defer()

    round2_select.callback = round2_callback
    view.add_item(round2_select)

    # ----- SAVE BUTTON (THE MISSING ONE!) -----
    @discord.ui.button(label="Save", style=discord.ButtonStyle.green)
    async def save_button(btn, inter2):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED

        ABYSS_DAYS = [int(v) for v in day_select.default_values]
        ABYSS_HOURS = [int(v) for v in hour_select.default_values]
        REMINDER_HOURS = [int(v) for v in reminder_select.default_values]
        ROUND2_ENABLED = (round2_select.default_values[0] == "true")

        cfg = {
            "days": ABYSS_DAYS,
            "hours": ABYSS_HOURS,
            "reminder_hours": REMINDER_HOURS,
            "round2": ROUND2_ENABLED
        }
        save_abyss_config(cfg)

        await inter2.response.send_message("✅ **Abyss Config Saved!**", ephemeral=True)

    view.add_item(save_button)

    # ----- SUMMARY EMBED -----
    embed = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
    embed.add_field(name="Days", value=str(ABYSS_DAYS), inline=False)
    embed.add_field(name="Hours", value=str(ABYSS_HOURS), inline=False)
    embed.add_field(name="Reminder Hours", value=str(REMINDER_HOURS), inline=False)
    embed.add_field(name="Round 2", value=str(ROUND2_ENABLED), inline=False)

    await inter.response.send_message(embed=embed, view=view, ephemeral=True)

# ======================================
# ABYSS REMINDER BOT — FINAL VERSION (PATCHED)
# PART 2 OF 3
# ======================================

# ================================
# ABYSS REMINDER ENGINE (MAIN + ROUND 2)
# ================================
@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    ch = bot.get_channel(channel_id)

    # Main Abyss reminder
    if now.weekday() in cfg["days"]:
        if now.hour in cfg["reminder_hours"] and now.minute == 0:
            if ch:
                await ch.send(
                    f"<@&1413532222396301322>, Abyss will start in 15 minutes!"
                )

        # Round 2
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
            if ch:
                await ch.send(
                    f"⏰ Reminder: **{ev['name']}** starts in {rem} minutes! <t:{int(dt.timestamp())}:F>"
                )

# ================================
# BOT READY → SYNC + START LOOPS
# ================================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"🌍 Synced {len(synced)} commands.")
    except Exception as e:
        print("Sync error:", e)

    abyss_reminder_loop.start()
    event_reminder_loop.start()

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Abyss Reminder Bot Updated & Online!")

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

    msg = "📅 **Weekly Abyss Events**\n\n"
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i in range(4):
        idx = (weeks_passed + i) % 4
        event_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        name = weekly_events[idx]
        emoji = event_emojis[name]

        dt = datetime.combine(event_date, time(0, 0))
        delta = dt - now
        msg += (
            f"{nums[i]} {emoji} **{name}** — <t:{int(dt.timestamp())}:F>\n"
            f"⏳ {delta.days}d {delta.seconds//3600}h\n\n"
        )

    await inter.response.send_message(msg)

# ================================
# KVK EVENTS
# ================================
@bot.tree.command(name="kvkevent", description="Show next 4 upcoming custom events.")
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

            evs = load_custom_events()
            evs.append(new_ev)
            save_custom_events(evs)

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
# EDIT EVENT (SAFE PATCHED)
# ================================
active_flows = {}

@bot.tree.command(name="editevent", description="Edit a custom event.")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    evs = load_custom_events()
    if not evs:
        return await inter.response.send_message("No events found.", ephemeral=True)

    uid = inter.user.id

    class SelectEvent(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                )
                for i, e in enumerate(evs)
            ]
            super().__init__(placeholder="Choose event", options=opts)

        async def callback(self, i2):
            idx = int(self.values[0])
            active_flows[uid] = {"idx": idx, "field": ""}

            class EditMenu(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self_btn, i3):
                    active_flows[uid]["field"] = "name"
                    await i3.response.send_message("Enter new name:", ephemeral=True)

                @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.secondary)
                async def edit_dt(self_btn, i3):
                    active_flows[uid]["field"] = "datetime"
                    await i3.response.send_message("Enter new datetime:", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_rm(self_btn, i3):
                    active_flows[uid]["field"] = "reminder"
                    await i3.response.send_message("Enter new reminder minutes or 'no':", ephemeral=True)

            await i2.response.send_message("Choose field:", view=EditMenu(), ephemeral=True)

    view = View()
    view.add_item(SelectEvent())
    await inter.response.send_message("Choose an event to edit:", view=view, ephemeral=True)

# ================================
# SAFE on_message HANDLER (PATCHED)
# ================================
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

    if not (0 <= idx < len(evs)):
        del active_flows[uid]
        return

    # ---- Edit Name ----
    if field == "name":
        evs[idx]["name"] = msg.content
        save_custom_events(evs)
        await msg.channel.send("✅ Name updated.")
        del active_flows[uid]
        return

    # ---- Edit Datetime ----
    if field == "datetime":
        try:
            evs[idx]["datetime"] = parse_datetime(msg.content).isoformat()
        except:
            await msg.channel.send("❌ Invalid datetime. Edit cancelled.")
            del active_flows[uid]
            return

        save_custom_events(evs)
        await msg.channel.send("❌ Invalid datetime. Edit cancelled.")
        await msg.channel.send("✅ Datetime updated.")
        del active_flows[uid]
        return

    # ---- Edit Reminder ----
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

# ======================================
# REMOVE EVENT
# ======================================
@bot.tree.command(name="removeevent", description="Delete a custom event.")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    evs = load_custom_events()
    if not evs:
        return await inter.response.send_message("No events found.", ephemeral=True)

    class SelectRemove(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=ev["name"],
                    description=datetime.fromisoformat(ev["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                )
                for i, ev in enumerate(evs)
            ]
            super().__init__(placeholder="Select event to delete", options=opts)

        async def callback(self, i2):
            idx = int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(btn, i3):
                    ev_list = load_custom_events()
                    if 0 <= idx < len(ev_list):
                        removed = ev_list.pop(idx)
                        save_custom_events(ev_list)
                        await i3.response.send_message(f"🗑 Deleted **{removed['name']}**")
                    else:
                        await i3.response.send_message("❌ Error: Index invalid.")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(btn, i3):
                    await i3.response.send_message("❌ Cancelled.", ephemeral=True)

            await i2.response.send_message("Confirm deletion:", view=Confirm(), ephemeral=True)

    v = View()
    v.add_item(SelectRemove())
    await inter.response.send_message("Choose an event to delete:", view=v, ephemeral=True)

# ======================================
# EXPORT CONFIG
# ======================================
@bot.tree.command(name="exportconfig", description="Export Abyss + Event settings.")
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

# ======================================
# IMPORT CONFIG (STRICT + SOFT)
# ======================================
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
    if "days" in d: out["days"] = [int(x) for x in d["days"]]
    if "hours" in d: out["hours"] = [int(x) for x in d["hours"]]
    if "reminder_hours" in d: out["reminder_hours"] = [int(x) for x in d["reminder_hours"]]
    if "round2" in d: out["round2"] = bool(d["round2"])
    return out

@bot.tree.command(name="importconfig", description="Import from config.zip")
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
            try: events_data = json.loads(z.read(name))
            except: pass
        if name == ABYSS_CONFIG_FILE:
            try: abyss_data = json.loads(z.read(name))
            except: pass

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
        imported.append("• Events (soft)")

    if abyss_data:
        soft = soft_validate_abyss(abyss_data)
        cfg.update(soft)
        save_abyss_config(cfg)

        ABYSS_DAYS = cfg["days"]
        ABYSS_HOURS = cfg["hours"]
        REMINDER_HOURS = cfg["reminder_hours"]
        ROUND2_ENABLED = cfg["round2"]

        imported.append("• Abyss Config (soft)")

    if not imported:
        return await inter.response.send_message("❌ Nothing imported.", ephemeral=True)

    await inter.response.send_message(
        "⚠️ Soft import completed:\n" + "\n".join(imported),
        ephemeral=True
    )

# ======================================
# RUN BOT
# ======================================
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ ERROR: DISCORD_BOT_TOKEN missing!")
else:
    bot.run(TOKEN)


