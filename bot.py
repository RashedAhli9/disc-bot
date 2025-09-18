import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import os
import json
import re
from datetime import date, timedelta, datetime, time

# ===== Setup =====
MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Custom Events Storage =====
EVENTS_FILE = "events.json"

def load_events():
    if not os.path.exists(EVENTS_FILE):
        data = {"custom": []}
        with open(EVENTS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    with open(EVENTS_FILE, "r") as f:
        return json.load(f)

def save_events(events):
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=2)

# ===== Weekly Event (Abyss Cycle) =====
events = ["Range Forge", "Melee Wheel", "Melee Forge", "Range Wheel"]
start_date = date(2025, 9, 16)  # Start from Sept 16, 2025

event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯"
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

        dt = datetime.combine(event_date, time(0,0))
        ts = int(dt.replace(tzinfo=pytz.UTC).timestamp())

        if i == 0 and event_start <= now < event_end:
            delta = event_end - now
            days, seconds = delta.days, delta.seconds
            hours, minutes = divmod(seconds // 60, 60)
            status = f"🟢 LIVE NOW (ends in {days}d {hours}h {minutes}m)"
        else:
            delta = dt - now
            days, seconds = delta.days, delta.seconds
            hours, minutes = divmod(seconds // 60, 60)
            status = f"⏳ Starts in {days}d {hours}h {minutes}m"

        msg += f"{number_emojis[i]} {emoji} **{event_name}** — <t:{ts}:F>\n{status}\n\n"

    await interaction.response.send_message(msg)

# ===== KVK Events (Fixed List UTC) =====
kvk_events = [
    ("🐻 Bear", datetime(2025, 9, 13, 14, 0)),
    ("🗿 Giant", datetime(2025, 9, 15, 2, 0)),
    ("🚪 Gate1", datetime(2025, 9, 16, 14, 0)),
    ("🗿 Statue", datetime(2025, 9, 18, 14, 0)),
    ("⚔️ Fort12", datetime(2025, 9, 20, 2, 0)),
    ("🚪 Gate2", datetime(2025, 9, 21, 14, 0)),
    ("🐍 Hydra", datetime(2025, 9, 23, 14, 0)),
    ("⚔️ Fort13", datetime(2025, 9, 25, 2, 0)),
    ("🚪 Gate3", datetime(2025, 9, 26, 14, 0)),
    ("⚙️ Gear Sentry", datetime(2025, 9, 28, 14, 0)),
    ("🗿 Island Statue", datetime(2025, 9, 30, 14, 0)),
    ("💀 Necrogiant", datetime(2025, 10, 2, 14, 0)),
    ("🚪 Gate4", datetime(2025, 10, 4, 14, 0)),
    ("🎖️ 60k Merit", datetime(2025, 10, 6, 2, 0)),
    ("⚔️ Fort14", datetime(2025, 10, 9, 2, 0)),
    ("🚪 Gate5", datetime(2025, 10, 10, 14, 0)),
    ("🎖️ 60k Merit", datetime(2025, 10, 12, 2, 0)),
    ("🐉 Shadow Dragon", datetime(2025, 10, 13, 14, 0)),
    ("⚔️ Fort15", datetime(2025, 10, 16, 2, 0)),
    ("🔥 Magma", datetime(2025, 10, 17, 14, 0)),
]

@bot.tree.command(name="kvkevent", description="Check the next 4 KVK + Custom events")
async def kvkevent(interaction: discord.Interaction):
    now = datetime.utcnow()
    events_data = load_events()

    combined = []
    for name, dt in kvk_events:
        if dt <= now < dt + timedelta(hours=1):
            combined.append((name, dt, "live"))
        elif dt > now:
            combined.append((name, dt, "upcoming"))

    for e in events_data["custom"]:
        dt = datetime.fromisoformat(e["datetime"])
        if dt <= now < dt + timedelta(hours=1):
            combined.append((e["name"], dt, "live"))
        elif dt > now:
            combined.append((e["name"], dt, "upcoming"))

    # Auto cleanup old events
    events_data["custom"] = [e for e in events_data["custom"] if datetime.fromisoformat(e["datetime"]) > now - timedelta(hours=1)]
    save_events(events_data)

    combined = sorted(combined, key=lambda x: x[1])[:4]

    if not combined:
        await interaction.response.send_message("No upcoming events.")
        return

    msg = "📅 **KVK + Custom Events**\n\n"
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i, (name, dt, status_type) in enumerate(combined):
        ts = int(dt.replace(tzinfo=pytz.UTC).timestamp())
        if status_type == "live":
            status = "🟢 LIVE NOW"
        else:
            delta = dt - now
            days, seconds = delta.days, delta.seconds
            hours, minutes = divmod(seconds // 60, 60)
            status = f"⏳ Starts in {days}d {hours}h {minutes}m"

        msg += f"{number_emojis[i]} {name} — <t:{ts}:F>\n{status}\n\n"

    await interaction.response.send_message(msg)

# ===== Reminders for KVK + Custom =====
@tasks.loop(minutes=1)
async def event_reminders():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    channel = bot.get_channel(channel_id)
    events_data = load_events()

    # KVK reminders (fixed 10m before)
    for name, dt in kvk_events:
        if now == dt - timedelta(minutes=10):
            await channel.send(f"⏰ Reminder: {name} starts in 10 minutes! <t:{int(dt.replace(tzinfo=pytz.UTC).timestamp())}:F>")

    # Custom reminders
    for e in events_data["custom"]:
        dt = datetime.fromisoformat(e["datetime"])
        reminder = e.get("reminder", 10)
        if now == dt - timedelta(minutes=reminder):
            await channel.send(f"⏰ Reminder: {e['name']} starts in {reminder} minutes! <t:{int(dt.replace(tzinfo=pytz.UTC).timestamp())}:F>")

# ===== Admin Permission Check =====
def has_admin_permission(interaction: discord.Interaction):
    if interaction.user.id == OWNER_ID:
        return True
    if hasattr(interaction.user, "roles") and any(role.name.lower() == "admin" for role in interaction.user.roles):
        return True
    return False

# ===== Add Event =====
@bot.tree.command(name="addevent", description="Add a custom event (UTC input, reminder in minutes)")
@app_commands.describe(name="Event name", datetime_str="UTC time (DD-MM-YYYY HH:MM)", reminder="Minutes before start to remind")
async def addevent(interaction: discord.Interaction, name: str, datetime_str: str, reminder: int = 10):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You can't use this command.", ephemeral=True)
        return
    try:
        event_dt = datetime.strptime(datetime_str, "%d-%m-%Y %H:%M")  # UTC input
    except ValueError:
        await interaction.response.send_message("❌ Invalid format. Use `DD-MM-YYYY HH:MM` in UTC.", ephemeral=True)
        return

    events = load_events()
    events["custom"].append({"name": name, "datetime": event_dt.isoformat(), "reminder": reminder})
    save_events(events)
    await interaction.response.send_message(f"✅ Added custom event **{name}** at <t:{int(event_dt.replace(tzinfo=pytz.UTC).timestamp())}:F> (reminder {reminder}m)")

# ===== Edit Event (multi-step) =====
active_edits = {}

@bot.tree.command(name="editevent", description="Edit a custom event (admin only)")
async def editevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You can't use this command.", ephemeral=True)
        return

    events = load_events()["custom"]
    if not events:
        await interaction.response.send_message("No custom events available to edit.")
        return

    msg = "✏️ **Custom Events List**\n\n"
    for idx, e in enumerate(events, start=1):
        dt = datetime.fromisoformat(e["datetime"])
        msg += f"{idx}. {e['name']} — <t:{int(dt.replace(tzinfo=pytz.UTC).timestamp())}:F> (reminder {e['reminder']}m)\n"

    await interaction.response.send_message(msg + "\nReply with the event **number** to edit or type `exit`.")
    active_edits[interaction.user.id] = {"step": "choose_event"}

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.author.id in active_edits:
        ctx = active_edits[message.author.id]
        events = load_events()["custom"]

        if message.content.lower() == "exit":
            await message.channel.send("❌ Edit cancelled.")
            del active_edits[message.author.id]
            return

        if ctx["step"] == "choose_event":
            try:
                idx = int(message.content) - 1
                ctx["index"] = idx
                ctx["step"] = "choose_field"
                await message.channel.send("What do you want to edit? (name / datetime / reminder)")
            except:
                await message.channel.send("Invalid input, try again.")
            return

        if ctx["step"] == "choose_field":
            field = message.content.lower()
            if field not in ["name", "datetime", "reminder"]:
                await message.channel.send("Invalid field, type: name / datetime / reminder")
                return
            ctx["field"] = field
            ctx["step"] = "new_value"
            await message.channel.send(f"Enter new value for {field}:")
            return

        if ctx["step"] == "new_value":
            idx = ctx["index"]
            field = ctx["field"]
            if field == "name":
                events[idx]["name"] = message.content
            elif field == "reminder":
                events[idx]["reminder"] = int(message.content)
            elif field == "datetime":
                try:
                    dt = datetime.strptime(message.content, "%d-%m-%Y %H:%M")
                    events[idx]["datetime"] = dt.isoformat()
                except:
                    await message.channel.send("Invalid date format. Use DD-MM-YYYY HH:MM in UTC.")
                    return
            save_events({"custom": events})
            await message.channel.send(f"✅ Updated event {events[idx]['name']}. Edit another field? (yes/no)")
            ctx["step"] = "edit_again"
            return

        if ctx["step"] == "edit_again":
            if message.content.lower() == "yes":
                ctx["step"] = "choose_field"
                await message.channel.send("What field do you want to edit next? (name / datetime / reminder)")
            else:
                del active_edits[message.author.id]
                await message.channel.send("✅ Editing finished.")
            return

    await bot.process_commands(message)

# ===== Remove Event Interactive =====
active_removes = {}

@bot.tree.command(name="removeevent", description="Remove a custom event (admin only)")
async def removeevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You can't use this command.", ephemeral=True)
        return

    events = load_events()["custom"]
    if not events:
        await interaction.response.send_message("No custom events available to remove.")
        return

    msg = "🗑️ **Custom Events List**\n\n"
    for idx, e in enumerate(events, start=1):
        dt = datetime.fromisoformat(e["datetime"])
        msg += f"{idx}. {e['name']} — <t:{int(dt.replace(tzinfo=pytz.UTC).timestamp())}:F> (reminder {e['reminder']}m)\n"

    await interaction.response.send_message(msg + "\nReply with the event **number** to delete or type `exit`.")
    active_removes[interaction.user.id] = True

@bot.event
async def on_message(message):
    if message.author.bot: return

    if message.author.id in active_removes:
        events = load_events()["custom"]
        if message.content.lower() == "exit":
            await message.channel.send("❌ Delete cancelled.")
            del active_removes[message.author.id]
            return
        try:
            idx = int(message.content) - 1
            removed = events.pop(idx)
            save_events({"custom": events})
            await message.channel.send(f"🗑️ Deleted event {removed['name']}")
        except:
            await message.channel.send("Invalid number, try again or type `exit`.")
            return
        del active_removes[message.author.id]
        return

    await bot.process_commands(message)

# ===== Run Bot =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    update_channel = bot.get_channel(update_channel_id)
    if update_channel:
        await update_channel.send("🤖 Bot updated and online!")
    event_reminders.start()

bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

bot.run(bot_token)
