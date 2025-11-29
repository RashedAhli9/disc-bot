import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import os
import json
from datetime import date, timedelta, datetime, time
from discord.ui import View, Button, Select, Modal, TextInput

# ===== Setup =====
MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549      # Abyss reminders channel
update_channel_id = 1332676174995918859  # Bot update notifications + logs
OWNER_ID = 1084884048884797490
GUILD_ID = 1328658110897983549

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CUSTOM_FILE = os.getenv("CUSTOM_FILE", "custom_events.json")
ABYSS_CONFIG_FILE = os.getenv("ABYSS_CONFIG_FILE", "abyss_config.json")

active_flows = {}
sent_reminders = set()

# Defaults: Tue, Fri, Sun at 0/4/8/12/16/20 UTC
ABYSS_DAYS = [1, 4, 6]                 # 0=Mon,1=Tue,...,6=Sun
ABYSS_HOURS = [0, 4, 8, 12, 16, 20]    # UTC hours


# ===== JSON Storage =====
def load_custom_events():
    if not os.path.exists(CUSTOM_FILE):
        return []
    with open(CUSTOM_FILE, "r") as f:
        return json.load(f)

def save_custom_events(events):
    with open(CUSTOM_FILE, "w") as f:
        json.dump(events, f, indent=2, default=str)


# ===== Abyss Config Storage =====
def load_abyss_config():
    """Load Abyss days/hours from file or fall back to defaults."""
    global ABYSS_DAYS, ABYSS_HOURS
    if not os.path.exists(ABYSS_CONFIG_FILE):
        return {"days": ABYSS_DAYS, "hours": ABYSS_HOURS}
    with open(ABYSS_CONFIG_FILE, "r") as f:
        data = json.load(f)
    days = data.get("days", ABYSS_DAYS)
    hours = data.get("hours", ABYSS_HOURS)
    return {"days": days, "hours": hours}

def save_abyss_config(days, hours):
    with open(ABYSS_CONFIG_FILE, "w") as f:
        json.dump({"days": days, "hours": hours}, f, indent=2)


# Load Abyss config at startup (module import)
_config = load_abyss_config()
ABYSS_DAYS = _config["days"]
ABYSS_HOURS = _config["hours"]


# ===== Helpers =====
def parse_datetime(input_str: str):
    """Parse DD-MM-YYYY HH:MM (UTC) or relative like '1d 2h 30m'."""
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


def has_admin_permission(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.id == OWNER_ID
        or any(r.name.lower() == "admin" for r in interaction.user.roles)
    )


async def log_action(message: str):
    channel = bot.get_channel(update_channel_id)
    if channel:
        await channel.send(message)


# ===== ON READY =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"🔄 Synced {len(synced)} commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

    log_channel = bot.get_channel(update_channel_id)
    if log_channel:
        await log_channel.send("🤖 Bot updated and online!")

    check_time.start()
    event_reminder.start()


# ===== Abyss Reminder Loop =====
@tasks.loop(minutes=1)
async def check_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    # Only run on configured Abyss days
    if now.weekday() in ABYSS_DAYS:
        # 15 minutes before Abyss start
        if now.hour in ABYSS_HOURS and now.minute == 0:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(
                    "<@&1413532222396301322>, Abyss will start in 15 minutes!"
                )

        # 15 minutes before Round 2
        if now.hour in ABYSS_HOURS and now.minute == 30:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(
                    "<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes!"
                )


# ===== Weekly Abyss Rotation (unchanged logic) =====
events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
start_date = date(2025, 9, 16)  # First event: Melee Wheel
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

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    msg = "📅 **Weekly Abyss Events**\n\n"

    for i in range(4):
        index = (weeks_passed + i) % len(events)
        event_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        event_name = events[index]
        emoji = event_emojis.get(event_name, "📌")

        if i == 0 and event_start <= now < event_end:
            delta = event_end - now
            status = (
                f"🟢 LIVE NOW (ends in "
                f"{delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m)"
            )
        else:
            delta = datetime.combine(event_date, time(0, 0)) - now
            status = (
                f"⏳ Starts in "
                f"{delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"
            )

        msg += (
            f"{number_emojis[i]} {emoji} **{event_name}** — "
            f"<t:{int(datetime.combine(event_date, time(0,0)).timestamp())}:F>\n"
            f"{status}\n\n"
        )

    await interaction.response.send_message(msg)


# ===== /abyssconfig (owner-only) =====
@bot.tree.command(
    name="abyssconfig",
    description="View or update Abyss days/hours (owner only)",
)
@app_commands.describe(
    days="Comma-separated weekdays (0=Mon..6=Sun), e.g. 1,4,6",
    hours="Comma-separated hours in UTC (0-23), e.g. 0,4,8,12,16,20",
)
async def abyssconfig(
    interaction: discord.Interaction,
    days: str = None,
    hours: str = None,
):
    global ABYSS_DAYS, ABYSS_HOURS

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ Only the bot owner can use this command.", ephemeral=True
        )
        return

    # Just show current config
    if days is None and hours is None:
        days_str = ", ".join(str(d) for d in ABYSS_DAYS)
        hours_str = ", ".join(str(h) for h in ABYSS_HOURS)
        await interaction.response.send_message(
            "⚙️ **Current Abyss Config**\n"
            f"Days (0=Mon..6=Sun): `{days_str}`\n"
            f"Hours (UTC): `{hours_str}`",
            ephemeral=True,
        )
        return

    # Parse and update days/hours
    new_days = ABYSS_DAYS
    new_hours = ABYSS_HOURS

    if days is not None:
        try:
            parsed_days = [
                int(x) for x in days.replace(" ", "").split(",") if x != ""
            ]
            if not parsed_days:
                raise ValueError
            for d in parsed_days:
                if d < 0 or d > 6:
                    raise ValueError
            new_days = parsed_days
        except Exception:
            await interaction.response.send_message(
                "❌ Invalid `days`. Use numbers 0–6, comma-separated, "
                "e.g. `1,4,6` (Tue,Fri,Sun).",
                ephemeral=True,
            )
            return

    if hours is not None:
        try:
            parsed_hours = [
                int(x) for x in hours.replace(" ", "").split(",") if x != ""
            ]
            if not parsed_hours:
                raise ValueError
            for h in parsed_hours:
                if h < 0 or h > 23:
                    raise ValueError
            new_hours = parsed_hours
        except Exception:
            await interaction.response.send_message(
                "❌ Invalid `hours`. Use numbers 0–23, comma-separated, "
                "e.g. `0,4,8,12,16,20`.",
                ephemeral=True,
            )
            return

    ABYSS_DAYS = new_days
    ABYSS_HOURS = new_hours
    save_abyss_config(ABYSS_DAYS, ABYSS_HOURS)

    await interaction.response.send_message(
        "✅ **Abyss config updated.**\n"
        f"Days: `{', '.join(str(d) for d in ABYSS_DAYS)}`\n"
        f"Hours (UTC): `{', '.join(str(h) for h in ABYSS_HOURS)}`",
        ephemeral=True,
    )
    await log_action(
        f"⚙️ [Abyss Config Updated] Days={ABYSS_DAYS}, "
        f"Hours={ABYSS_HOURS} by {interaction.user.mention}"
    )


# ===== CUSTOM EVENTS ONLY (kvkevent) =====
@bot.tree.command(
    name="kvkevent",
    description="Show next 4 upcoming custom events",
)
async def kvkevent(interaction: discord.Interaction):
    now = datetime.utcnow()
    custom = load_custom_events()
    # custom['datetime'] is ISO format; string sort works, but be explicit with datetime
    custom_sorted = sorted(
        custom, key=lambda ev: ev["datetime"]
    )

    upcoming = []
    for ev in custom_sorted:
        ev_time = datetime.fromisoformat(ev["datetime"])
        if ev_time <= now < ev_time + timedelta(hours=1):
            upcoming.append((ev["name"], ev_time, "live"))
        elif ev_time > now:
            upcoming.append((ev["name"], ev_time, "upcoming"))
        if len(upcoming) == 4:
            break

    if not upcoming:
        await interaction.response.send_message("📭 No upcoming events.", ephemeral=True)
        return

    msg = "📅 **Upcoming Events**\n\n"
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i, (name, dt, status) in enumerate(upcoming):
        if status == "live":
            remaining = (dt + timedelta(hours=1)) - now
            mins_left = max(1, remaining.seconds // 60)
            state = f"🟢 LIVE (ends in ~{mins_left}m)"
        else:
            delta = dt - now
            state = (
                f"⏳ Starts in {delta.days}d "
                f"{delta.seconds//3600}h {(delta.seconds//60)%60}m"
            )

        msg += (
            f"{emojis[i]} **{name}** — <t:{int(dt.timestamp())}:F>\n"
            f"{state}\n\n"
        )

    await interaction.response.send_message(msg)


# ===== ADD EVENT =====
class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name")
    datetime_input = TextInput(
        label="Datetime (UTC)",
        placeholder="DD-MM-YYYY HH:MM or 1d 2h",
    )
    reminder = TextInput(
        label="Reminder (minutes or 'no')",
        placeholder="10",
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            dt = parse_datetime(self.datetime_input.value)
            reminder_value = (
                0 if self.reminder.value.lower() == "no" else int(self.reminder.value)
            )
            new = {
                "name": self.name.value,
                "datetime": dt.isoformat(),
                "reminder": reminder_value,
            }
            data = load_custom_events()
            data.append(new)
            save_custom_events(data)

            await interaction.response.send_message(
                f"✅ Event added: **{new['name']}** at <t:{int(dt.timestamp())}:F>",
                ephemeral=True,
            )
            await log_action(
                f"📝 [Event Added] **{new['name']}** at <t:{int(dt.timestamp())}:F> "
                f"by {interaction.user.mention}"
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to add event: {e}", ephemeral=True
            )


@bot.tree.command(name="addevent", description="Add a custom event (admin only)")
async def addevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message(
            "❌ No permission to add events.", ephemeral=True
        )
        return
    await interaction.response.send_modal(AddEventModal())


# ===== EDIT EVENT =====
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
            opts = [
                discord.SelectOption(label=e["name"], value=str(i))
                for i, e in enumerate(custom)
            ]
            super().__init__(placeholder="Choose event to edit", options=opts)

        async def callback(self, inter: discord.Interaction):
            idx = int(self.values[0])
            flow = {"idx": idx}
            active_flows[interaction.user.id] = flow

            class Buttons(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self, button: Button, i: discord.Interaction):
                    flow["field"] = "name"
                    flow["step"] = "edit"
                    await i.response.send_message(
                        "Enter new name:", ephemeral=True
                    )

                @discord.ui.button(
                    label="Edit Datetime",
                    style=discord.ButtonStyle.secondary,
                )
                async def edit_datetime(self, button: Button, i: discord.Interaction):
                    flow["field"] = "datetime"
                    flow["step"] = "edit"
                    await i.response.send_message(
                        "Enter new datetime (UTC `DD-MM-YYYY HH:MM` or relative):",
                        ephemeral=True,
                    )

                @discord.ui.button(
                    label="Edit Reminder",
                    style=discord.ButtonStyle.success,
                )
                async def edit_reminder(self, button: Button, i: discord.Interaction):
                    flow["field"] = "reminder"
                    flow["step"] = "edit"
                    await i.response.send_message(
                        "Enter new reminder minutes (or `no`):", ephemeral=True
                    )

            await inter.response.send_message(
                "Choose what to edit:", view=Buttons(), ephemeral=True
            )

    view = View()
    view.add_item(SelectEvent())
    await interaction.response.send_message(
        "Select event:", view=view, ephemeral=True
    )


# ===== REMOVE EVENT =====
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
            opts = [
                discord.SelectOption(label=e["name"], value=str(i))
                for i, e in enumerate(custom)
            ]
            super().__init__(placeholder="Select event to delete", options=opts)

        async def callback(self, i: discord.Interaction):
            idx = int(self.values[0])

            class Confirm(View):
                @discord.ui.button(
                    label="YES", style=discord.ButtonStyle.danger
                )
                async def yes(self, button: Button, i2: discord.Interaction):
                    ev_list = load_custom_events()
                    if 0 <= idx < len(ev_list):
                        ev = ev_list.pop(idx)
                        save_custom_events(ev_list)
                        await i2.response.send_message(
                            f"🗑️ Removed **{ev['name']}**"
                        )
                        await log_action(
                            f"🗑️ [Event Removed] **{ev['name']}** by {i.user.mention}"
                        )
                    else:
                        await i2.response.send_message("❌ Invalid event.")
                @discord.ui.button(
                    label="NO", style=discord.ButtonStyle.secondary
                )
                async def no(self, button: Button, i2: discord.Interaction):
                    await i2.response.send_message(
                        "❌ Deletion cancelled.", ephemeral=True
                    )

            await i.response.send_message(
                "Confirm deletion:", view=Confirm(), ephemeral=True
            )

    view = View()
    view.add_item(SelectRemove())
    await interaction.response.send_message(
        "Choose event:", view=view, ephemeral=True
    )


# ===== EDIT FLOW TEXT HANDLER =====
@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return
    if msg.author.id not in active_flows:
        return

    flow = active_flows[msg.author.id]
    custom = load_custom_events()
    idx = flow["idx"]
    field = flow.get("field")

    if not (0 <= idx < len(custom)) or field not in ("name", "datetime", "reminder"):
        del active_flows[msg.author.id]
        return

    if field == "datetime":
        custom[idx]["datetime"] = parse_datetime(msg.content).isoformat()
    elif field == "reminder":
        custom[idx]["reminder"] = (
            0 if msg.content.lower() == "no" else int(msg.content)
        )
    else:  # name
        custom[idx]["name"] = msg.content

    save_custom_events(custom)
    await msg.channel.send("✅ Event updated.")
    await log_action(
        f"✏️ [Event Edited] **{custom[idx]['name']}** field **{field}** by {msg.author.mention}"
    )
    del active_flows[msg.author.id]


# ===== REMINDER LOOP (custom events) =====
@tasks.loop(minutes=1)
async def event_reminder():
    global sent_reminders
    now = datetime.utcnow().replace(second=0, microsecond=0)
    channel = bot.get_channel(channel_id)

    custom = load_custom_events()

    if channel:
        for ev in custom:
            dt = datetime.fromisoformat(ev["datetime"])
            rem = ev.get("reminder", 0)
            if rem <= 0:
                continue

            remind_time = dt - timedelta(minutes=rem)
            key = (ev["name"], remind_time.isoformat())

            if remind_time <= now < remind_time + timedelta(minutes=1):
                if key not in sent_reminders:
                    await channel.send(
                        f"⏰ Reminder: {ev['name']} starts in {rem} minutes! "
                        f"<t:{int(dt.timestamp())}:F>"
                    )
                    sent_reminders.add(key)

    # Limit memory usage
    if len(sent_reminders) > 300:
        sent_reminders = set(list(sent_reminders)[-100:])


# ===== RUN BOT =====
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ DISCORD_BOT_TOKEN not set")
    exit(1)

bot.run(TOKEN)
