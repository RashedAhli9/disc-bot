import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import pytz
import os
import json
import re
from datetime import timedelta, datetime

# ===== Setup =====
MY_TIMEZONE = "UTC"
abyss_channel_id = 1328658110897983549   # Abyss/KVK reminders
update_channel_id = 1332676174995918859  # Bot update messages
OWNER_ID = 1084884048884797490           # Replace with your Discord ID

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Storage =====
EVENTS_FILE = "events.json"

def load_events():
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "r") as f:
            return json.load(f)
    return {"weekly": [], "kvk": [], "custom": []}

def save_events(events):
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=2)

# ===== Permission Check =====
def has_admin_permission(interaction: discord.Interaction):
    if interaction.user.id == OWNER_ID:
        return True
    if hasattr(interaction.user, "roles") and any(role.name.lower() == "admin" for role in interaction.user.roles):
        return True
    return False

# ===== Bot Events =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

    # Update message on deploy
    channel = bot.get_channel(update_channel_id)
    if channel:
        await channel.send("🤖 Bot updated and online!")

    reminder_loop.start()

# ===== Reminder Loop =====
@tasks.loop(minutes=1)
async def reminder_loop():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    events = load_events()

    for category, evlist in events.items():
        for event in evlist[:]:  # copy to avoid modification errors
            event_dt = datetime.fromisoformat(event["datetime"])
            reminder = event["reminder"]

            # Reminder time
            reminder_time = event_dt - timedelta(minutes=reminder)
            if reminder_time.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0):
                channel = bot.get_channel(abyss_channel_id)
                if channel:
                    await channel.send(f"⏰ Reminder: **{event['name']}** starts in {reminder} minutes! ({category.upper()} event)")

            # Live now
            if event_dt <= now < event_dt + timedelta(hours=1):
                channel = bot.get_channel(abyss_channel_id)
                if channel:
                    await channel.send(f"🔥 **{event['name']}** is LIVE NOW! ({category.upper()} event)")

            # Auto-remove old events
            if now > event_dt + timedelta(hours=1):
                evlist.remove(event)
                save_events(events)

# ===== Add Event =====
@bot.tree.command(name="addevent", description="Add a new event")
@app_commands.describe(
    name="Event name",
    datetime_str="Date in DD-MM-YYYY HH:MM or relative (e.g. 1d - 12h - 10m)",
    reminder="Minutes before the event to remind",
    category="Which list: weekly, kvk, or custom"
)
async def addevent(interaction: discord.Interaction, name: str, datetime_str: str, reminder: int, category: str):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
        return

    category = category.lower()
    if category not in ["weekly", "kvk", "custom"]:
        await interaction.response.send_message("❌ Invalid category. Choose: weekly, kvk, or custom.", ephemeral=True)
        return

    now = datetime.utcnow()
    event_dt = None

    # Try absolute date
    try:
        event_dt = datetime.strptime(datetime_str, "%d-%m-%Y %H:%M")
    except ValueError:
        # Try relative format
        match = re.findall(r"(\d+)([dhm])", datetime_str)
        if match:
            delta = timedelta()
            for value, unit in match:
                value = int(value)
                if unit == "d":
                    delta += timedelta(days=value)
                elif unit == "h":
                    delta += timedelta(hours=value)
                elif unit == "m":
                    delta += timedelta(minutes=value)
            event_dt = now + delta

    if not event_dt:
        await interaction.response.send_message("❌ Invalid datetime format. Use `DD-MM-YYYY HH:MM` or `Xd - Yh - Zm`.", ephemeral=True)
        return

    # Save event
    events = load_events()
    new_event = {"name": name, "datetime": event_dt.isoformat(), "reminder": reminder}
    events[category].append(new_event)
    save_events(events)

    await interaction.response.send_message(
        f"✅ Event **{name}** added to **{category.upper()}** for <t:{int(event_dt.timestamp())}:F> "
        f"with reminder {reminder} minutes before."
    )

# ===== Remove Event =====
@bot.tree.command(name="removeevent", description="Remove an event by name")
async def removeevent(interaction: discord.Interaction, name: str, category: str):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
        return

    category = category.lower()
    events = load_events()

    if category not in events:
        await interaction.response.send_message("❌ Invalid category. Choose: weekly, kvk, or custom.", ephemeral=True)
        return

    before = len(events[category])
    events[category] = [e for e in events[category] if e["name"].lower() != name.lower()]
    after = len(events[category])
    save_events(events)

    if before == after:
        await interaction.response.send_message(f"⚠️ No event named **{name}** found in {category}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"🗑️ Removed **{name}** from {category.upper()} events.")

# ===== Edit Event =====
@bot.tree.command(name="editevent", description="Edit an event’s name, datetime, or reminder")
@app_commands.describe(
    old_name="The event name to edit",
    new_name="New name (leave blank to keep same)",
    datetime_str="New date/time (DD-MM-YYYY HH:MM or Xd - Yh - Zm)",
    reminder="New reminder in minutes (leave -1 to keep same)",
    category="Which list: weekly, kvk, or custom"
)
async def editevent(interaction: discord.Interaction, old_name: str, new_name: str = None, datetime_str: str = None, reminder: int = -1, category: str = "custom"):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
        return

    category = category.lower()
    events = load_events()

    if category not in events:
        await interaction.response.send_message("❌ Invalid category. Choose: weekly, kvk, or custom.", ephemeral=True)
        return

    for event in events[category]:
        if event["name"].lower() == old_name.lower():
            if new_name:
                event["name"] = new_name

            if datetime_str:
                try:
                    new_dt = datetime.strptime(datetime_str, "%d-%m-%Y %H:%M")
                except ValueError:
                    match = re.findall(r"(\d+)([dhm])", datetime_str)
                    if match:
                        delta = timedelta()
                        for value, unit in match:
                            value = int(value)
                            if unit == "d":
                                delta += timedelta(days=value)
                            elif unit == "h":
                                delta += timedelta(hours=value)
                            elif unit == "m":
                                delta += timedelta(minutes=value)
                        new_dt = datetime.utcnow() + delta
                    else:
                        await interaction.response.send_message("❌ Invalid datetime format.", ephemeral=True)
                        return
                event["datetime"] = new_dt.isoformat()

            if reminder >= 0:
                event["reminder"] = reminder

            save_events(events)
            await interaction.response.send_message(f"✏️ Event **{old_name}** updated successfully.")
            return

    await interaction.response.send_message(f"⚠️ Event **{old_name}** not found in {category}.", ephemeral=True)

# ===== Display Commands =====
def format_events(events, category):
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    upcoming = sorted(events, key=lambda e: e["datetime"])
    upcoming = [e for e in upcoming if datetime.fromisoformat(e["datetime"]) >= now]
    if not upcoming:
        return f"No upcoming {category.upper()} events."

    msg = f"📅 **Next {category.upper()} Events:**\n"
    for event in upcoming[:4]:
        dt = datetime.fromisoformat(event["datetime"])
        delta = dt - now
        days, seconds = delta.days, delta.seconds
        hours, minutes = divmod(seconds // 60, 60)
        msg += f"- **{event['name']}** → <t:{int(dt.timestamp())}:F> (in {days}d {hours}h {minutes}m)\n"
    return msg

@bot.tree.command(name="weeklyevent", description="Show the next 4 Weekly events")
async def weeklyevent(interaction: discord.Interaction):
    events = load_events()
    await interaction.response.send_message(format_events(events["weekly"], "weekly"))

@bot.tree.command(name="kvkevent", description="Show the next 4 KVK events")
async def kvkevent(interaction: discord.Interaction):
    events = load_events()
    await interaction.response.send_message(format_events(events["kvk"], "kvk"))

@bot.tree.command(name="customevent", description="Show the next 4 Custom events")
async def customevent(interaction: discord.Interaction):
    events = load_events()
    await interaction.response.send_message(format_events(events["custom"], "custom"))

# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

bot.run(bot_token)
