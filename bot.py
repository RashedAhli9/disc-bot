import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import os
import json
from datetime import date, timedelta, datetime, time
from discord.ui import View, Button, Select, Modal, TextInput

# ==============================
# CONFIGURATION
# ==============================
MY_TIMEZONE = "UTC"

channel_id = 1328658110897983549          # Abyss reminders channel
update_channel_id = 1332676174995918859   # Bot update notifications & logs
OWNER_ID = 1084884048884797490
GUILD_ID = 1328405638744641548            # Main server

CUSTOM_FILE = os.getenv("CUSTOM_FILE", "custom_events.json")
ABYSS_CONFIG_FILE = os.getenv("ABYSS_CONFIG_FILE", "abyss_config.json")

DEFAULT_ABYSS_DAYS = [1, 4, 6]                  # Tue, Fri, Sun
DEFAULT_ABYSS_HOURS = [0, 4, 8, 12, 16, 20]     # UTC hours

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

active_flows: dict[int, dict] = {}
sent_reminders: set[tuple[str, str]] = set()
ABYSS_DAYS = DEFAULT_ABYSS_DAYS.copy()
ABYSS_HOURS = DEFAULT_ABYSS_HOURS.copy()

# ==============================
# STORAGE HELPERS
# ==============================
def load_custom_events():
    if not os.path.exists(CUSTOM_FILE):
        return []
    with open(CUSTOM_FILE, "r") as f:
        return json.load(f)

def save_custom_events(events):
    with open(CUSTOM_FILE, "w") as f:
        json.dump(events, f, indent=2, default=str)

def load_abyss_config():
    if not os.path.exists(ABYSS_CONFIG_FILE):
        return {"days": DEFAULT_ABYSS_DAYS, "hours": DEFAULT_ABYSS_HOURS}
    with open(ABYSS_CONFIG_FILE, "r") as f:
        data = json.load(f)
    return {
        "days": data.get("days", DEFAULT_ABYSS_DAYS),
        "hours": data.get("hours", DEFAULT_ABYSS_HOURS),
    }

def save_abyss_config(days, hours):
    with open(ABYSS_CONFIG_FILE, "w") as f:
        json.dump({"days": days, "hours": hours}, f, indent=2)

_conf = load_abyss_config()
ABYSS_DAYS = _conf["days"]
ABYSS_HOURS = _conf["hours"]

# ==============================
# GENERIC HELPERS
# ==============================
def parse_datetime(input_str: str) -> datetime:
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except ValueError:
        pass

    now = datetime.utcnow()
    days = hours = minutes = 0
    for part in input_str.split():
        if "d" in part:
            days = int(part.replace("d", ""))
        elif "h" in part:
            hours = int(part.replace("h", ""))
        elif "m" in part:
            minutes = int(part.replace("m", ""))
    return now + timedelta(days=days, hours=hours, minutes=minutes)

async def log_action(msg: str):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(msg)

def has_admin_permission(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.id == OWNER_ID or
        any(r.name.lower() == "admin" for r in interaction.user.roles)
    )

# ==============================
# READY + SYNC
# ==============================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"🌍 Synced {len(synced)} global commands")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

    log = bot.get_channel(update_channel_id)
    if log:
        await log.send("🤖 Bot updated & synced (global commands).")

    check_time.start()
    event_reminder.start()

# ==============================
# ABYSS SCHEDULE REMINDERS
# ==============================
@tasks.loop(minutes=1)
async def check_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    if now.weekday() in ABYSS_DAYS:
        if now.hour in ABYSS_HOURS and now.minute == 0:
            ch = bot.get_channel(channel_id)
            if ch:
                await ch.send("<@&1413532222396301322>, Abyss starts in 15 minutes!")

        if now.hour in ABYSS_HOURS and now.minute == 30:
            ch = bot.get_channel(channel_id)
            if ch:
                await ch.send("<@&1413532222396301322>, Abyss Round 2 starts in 15 minutes!")

# ==============================
# WEEKLY EVENT ROTATION
# ==============================
weekly_events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
start_date = date(2025, 9, 16)

event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯",
}

@bot.tree.command(name="weeklyevent", description="Check the next 4 weekly Abyss events")
async def weeklyevent(interaction: discord.Interaction):
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
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i in range(4):
        idx = (weeks_passed + i) % len(weekly_events)
        event_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        name = weekly_events[idx]
        emoji = event_emojis.get(name, "📌")

        base_dt = datetime.combine(event_date, time(0, 0))

        if i == 0 and event_start <= now < event_end:
            delta = event_end - now
            status = f"🟢 LIVE NOW (ends in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m)"
        else:
            delta = base_dt - now
            status = f"⏳ Starts in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"

        msg += (
            f"{number_emojis[i]} {emoji} **{name}** — <t:{int(base_dt.timestamp())}:F>\n"
            f"{status}\n\n"
        )

    await interaction.response.send_message(msg)

# ==============================
# ABYSS CONFIG (OWNER ONLY)
# ==============================
@bot.tree.command(name="abyssconfig", description="View or update Abyss days/hours (owner only)")
@app_commands.describe(
    days="Comma-separated weekdays 0=Mon..6=Sun",
    hours="Comma-separated UTC hours 0-23",
)
async def abyssconfig(interaction: discord.Interaction, days: str | None = None, hours: str | None = None):
    global ABYSS_DAYS, ABYSS_HOURS

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)
        return

    if days is None and hours is None:
        await interaction.response.send_message(
            f"⚙️ **Current Abyss Config**\n"
            f"Days: `{', '.join(str(d) for d in ABYSS_DAYS)}`\n"
            f"Hours UTC: `{', '.join(str(h) for h in ABYSS_HOURS)}`",
            ephemeral=True,
        )
        return

    # Update days
    if days:
        try:
            parsed = [int(x) for x in days.split(",") if x.strip()]
            if not all(0 <= d <= 6 for d in parsed):
                raise ValueError
            ABYSS_DAYS = parsed
        except:
            await interaction.response.send_message("❌ Invalid days. Use 0–6.", ephemeral=True)
            return

    # Update hours
    if hours:
        try:
            parsed = [int(x) for x in hours.split(",") if x.strip()]
            if not all(0 <= h <= 23 for h in parsed):
                raise ValueError
            ABYSS_HOURS = parsed
        except:
            await interaction.response.send_message("❌ Invalid hours. Use 0–23.", ephemeral=True)
            return

    save_abyss_config(ABYSS_DAYS, ABYSS_HOURS)

    await interaction.response.send_message(
        f"✅ Updated Abyss Config\n"
        f"Days: `{ABYSS_DAYS}`\n"
        f"Hours: `{ABYSS_HOURS}`",
        ephemeral=True,
    )

    await log_action(f"⚙️ Abyss Config Updated by {interaction.user.mention}")

# ==============================
# KVK CUSTOM EVENTS
# ==============================
@bot.tree.command(name="kvkevent", description="Show next 4 upcoming custom events")
async def kvkevent(interaction: discord.Interaction):
    now = datetime.utcnow()
    events = load_custom_events()

    sorted_events = sorted(events, key=lambda e: datetime.fromisoformat(e["datetime"]))

    upcoming = []
    for ev in sorted_events:
        dt = datetime.fromisoformat(ev["datetime"])
        if dt <= now < dt + timedelta(hours=1):
            upcoming.append((ev["name"], dt, "live"))
        elif dt > now:
            upcoming.append((ev["name"], dt, "upcoming"))
        if len(upcoming) == 4:
            break

    if not upcoming:
        await interaction.response.send_message("📭 No upcoming events.", ephemeral=True)
        return

    msg = "📅 **Upcoming Events**\n\n"
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i, (name, dt, state) in enumerate(upcoming):
        if state == "live":
            remaining = (dt + timedelta(hours=1)) - now
            mins = max(1, remaining.seconds // 60)
            status = f"🟢 LIVE (ends in ~{mins}m)"
        else:
            delta = dt - now
            status = f"⏳ Starts in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"

        msg += f"{emojis[i]} **{name}** — <t:{int(dt.timestamp())}:F>\n{status}\n\n"

    await interaction.response.send_message(msg)

# ==============================
# ADD CUSTOM EVENT
# ==============================
class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name")
    datetime_input = TextInput(label="Datetime (UTC)", placeholder="DD-MM-YYYY HH:MM or 1d 2h")
    reminder = TextInput(label="Reminder (minutes or 'no')", placeholder="10")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            dt = parse_datetime(self.datetime_input.value)
            reminder_value = 0 if self.reminder.value.lower() == "no" else int(self.reminder.value)

            new_ev = {
                "name": self.name.value,
                "datetime": dt.isoformat(),
                "reminder": reminder_value,
            }

            events = load_custom_events()
            events.append(new_ev)
            save_custom_events(events)

            await interaction.response.send_message(
                f"✅ Event added: **{new_ev['name']}** at <t:{int(dt.timestamp())}:F>",
                ephemeral=True,
            )
            await log_action(f"📝 Event Added by {interaction.user.mention}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to add event: {e}", ephemeral=True)

@bot.tree.command(name="addevent", description="Add a custom event (admin only)")
async def addevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.send_modal(AddEventModal())

# ==============================
# EDIT EVENT
# ==============================
@bot.tree.command(name="editevent", description="Edit a custom event (admin only)")
async def editevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    custom = load_custom_events()
    if not custom:
        await interaction.response.send_message("No events found.", ephemeral=True)
        return

    class SelectEvent(Select):
        def __init__(self):
            options = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i),
                )
                for i, e in enumerate(custom)
            ]
            super().__init__(placeholder="Choose event to edit", options=options)

        async def callback(self, inter):
            idx = int(self.values[0])
            active_flows[interaction.user.id] = {"idx": idx}

            class EditButtons(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self, button, i):
                    active_flows[interaction.user.id]["field"] = "name"
                    await i.response.send_message("Enter new name:", ephemeral=True)

                @discord.ui.button(label="Edit Datetime", style=discord.ButtonStyle.secondary)
                async def edit_datetime(self, button, i):
                    active_flows[interaction.user.id]["field"] = "datetime"
                    await i.response.send_message("Enter new datetime:", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_reminder(self, button, i):
                    active_flows[interaction.user.id]["field"] = "reminder"
                    await i.response.send_message("Enter new reminder minutes:", ephemeral=True)

            await inter.response.send_message("Choose what to edit:", view=EditButtons(), ephemeral=True)

    view = View()
    view.add_item(SelectEvent())
    await interaction.response.send_message("Select an event:", view=view, ephemeral=True)

# ==============================
# REMOVE EVENT
# ==============================
@bot.tree.command(name="removeevent", description="Remove a custom event (admin only)")
async def removeevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    custom = load_custom_events()
    if not custom:
        await interaction.response.send_message("No events found.", ephemeral=True)
        return

    class SelectRemove(Select):
        def __init__(self):
            options = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i),
                )
                for i, e in enumerate(custom)
            ]
            super().__init__(placeholder="Select event to delete", options=options)

        async def callback(self, inter):
            idx = int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(self, button, i2):
                    ev_list = load_custom_events()
                    if 0 <= idx < len(ev_list):
                        ev = ev_list.pop(idx)
                        save_custom_events(ev_list)
                        await i2.response.send_message(f"🗑️ Removed **{ev['name']}**")
                        await log_action(f"🗑️ Event Removed by {interaction.user.mention}")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(self, button, i2):
                    await i2.response.send_message("Cancelled.", ephemeral=True)

            await inter.response.send_message("Confirm deletion:", view=Confirm(), ephemeral=True)

    view = View()
    view.add_item(SelectRemove())
    await interaction.response.send_message("Choose event to remove:", view=view, ephemeral=True)

# ==============================
# TEXT INPUT HANDLER FOR EDIT FLOW
# ==============================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.author.id not in active_flows:
        return

    flow = active_flows[message.author.id]
    idx = flow.get("idx")
    field = flow.get("field")

    custom = load_custom_events()

    if idx is None or field not in ("name", "datetime", "reminder"):
        del active_flows[message.author.id]
        return

    if not (0 <= idx < len(custom)):
        del active_flows[message.author.id]
        return

    if field == "datetime":
        custom[idx]["datetime"] = parse_datetime(message.content).isoformat()
    elif field == "reminder":
        custom[idx]["reminder"] = 0 if message.content.lower() == "no" else int(message.content)
    else:
        custom[idx]["name"] = message.content

    save_custom_events(custom)
    await message.channel.send("✅ Event updated.")
    await log_action(f"✏️ Event Edited by {message.author.mention}")
    del active_flows[message.author.id]

# ==============================
# EVENT REMINDER LOOP
# ==============================
@tasks.loop(minutes=1)
async def event_reminder():
    global sent_reminders
    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(channel_id)

    events = load_custom_events()
    if ch:
        for ev in events:
            dt = datetime.fromisoformat(ev["datetime"])
            rem = ev.get("reminder", 0)
            if rem <= 0:
                continue

            remind_time = dt - timedelta(minutes=rem)
            key = (ev["name"], remind_time.isoformat())

            if remind_time <= now < remind_time + timedelta(minutes=1):
                if key not in sent_reminders:
                    await ch.send(
                        f"⏰ Reminder: {ev['name']} starts in {rem} minutes! "
                        f"<t:{int(dt.timestamp())}:F>"
                    )
                    sent_reminders.add(key)

    if len(sent_reminders) > 300:
        sent_reminders = set(list(sent_reminders)[-100:])

# ==============================
# RUN BOT
# ==============================
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ DISCORD_BOT_TOKEN not set")
    raise SystemExit(1)

bot.run(TOKEN)
