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
abyss_channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Storage =====
EVENTS_FILE = "events.json"

def preload_events():
    if not os.path.exists(EVENTS_FILE):
        data = {
            "kvk": [
                {"name": "Bear", "datetime": "2025-09-13T18:00:00", "reminder": 10},
                {"name": "Giant", "datetime": "2025-09-15T02:00:00", "reminder": 10},
                {"name": "Gate1", "datetime": "2025-09-16T18:00:00", "reminder": 10},
                {"name": "Statue", "datetime": "2025-09-18T18:00:00", "reminder": 10}
            ],
            "custom": []
        }
        with open(EVENTS_FILE, "w") as f:
            json.dump(data, f, indent=2)

def load_events():
    preload_events()
    with open(EVENTS_FILE, "r") as f:
        return json.load(f)

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

# ===== Weekly Events Rotation =====
weekly_rotation = ["Range Forge", "Melee Wheel", "Melee Forge", "Range Wheel"]
weekly_start = datetime(2025, 9, 9, 0, 0)

def get_weekly_events():
    now = datetime.utcnow()
    weeks_passed = (now - weekly_start).days // 7
    events = []
    for i in range(4):
        index = (weeks_passed + i) % len(weekly_rotation)
        event_date = weekly_start + timedelta(weeks=weeks_passed + i)
        events.append({"name": weekly_rotation[index], "datetime": event_date})
    return events

# ===== State Sessions =====
active_sessions = {}  # user_id: {mode, category, step, event_index, field}

# ===== Bot Events =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

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
        for event in evlist[:]:
            event_dt = datetime.fromisoformat(event["datetime"])
            reminder = event["reminder"]

            # Reminder check
            if event_dt - timedelta(minutes=reminder) <= now < event_dt - timedelta(minutes=reminder-1):
                channel = bot.get_channel(abyss_channel_id)
                if channel:
                    await channel.send(f"⏰ Reminder: **{event['name']}** starts in {reminder} minutes!")

            # Live now
            if event_dt <= now < event_dt + timedelta(hours=1):
                channel = bot.get_channel(abyss_channel_id)
                if channel:
                    await channel.send(f"🔥 **{event['name']}** is LIVE NOW!")

            # Expired cleanup
            if now > event_dt + timedelta(hours=1):
                evlist.remove(event)
                save_events(events)

# ===== Display Commands =====
def format_events(events, category):
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    upcoming = sorted(events, key=lambda e: e["datetime"])
    upcoming = [e for e in upcoming if datetime.fromisoformat(e["datetime"]) >= now]
    if not upcoming:
        return f"No upcoming {category.upper()} events."

    msg = f"📅 **Next {category.upper()} Events:**\n"
    for i, event in enumerate(upcoming[:4], start=1):
        dt = datetime.fromisoformat(event["datetime"])
        delta = dt - now
        days, seconds = delta.days, delta.seconds
        hours, minutes = divmod(seconds // 60, 60)
        msg += f"{i}. **{event['name']}** → <t:{int(dt.timestamp())}:F> (in {days}d {hours}h {minutes}m, reminder {event['reminder']}m)\n"
    return msg

@bot.tree.command(name="weeklyevent", description="Show the next 4 Weekly events")
async def weeklyevent(interaction: discord.Interaction):
    weekly = get_weekly_events()
    msg = "📅 **Next WEEKLY Events:**\n"
    now = datetime.utcnow()
    for i, event in enumerate(weekly, start=1):
        delta = event["datetime"] - now
        days, seconds = delta.days, delta.seconds
        hours, minutes = divmod(seconds // 60, 60)
        msg += f"{i}. **{event['name']}** → <t:{int(event['datetime'].timestamp())}:F> (in {days}d {hours}h {minutes}m)\n"
    await interaction.response.send_message(msg)

@bot.tree.command(name="kvkevent", description="Show the next 4 KVK events")
async def kvkevent(interaction: discord.Interaction):
    events = load_events()
    await interaction.response.send_message(format_events(events["kvk"], "kvk"))

@bot.tree.command(name="customevent", description="Show the next 4 Custom events")
async def customevent(interaction: discord.Interaction):
    events = load_events()
    await interaction.response.send_message(format_events(events["custom"], "custom"))

# ===== Interactive Edit / Remove =====
@bot.tree.command(name="editevent", description="Interactively edit an event (admin only)")
@app_commands.describe(category="Category: kvk or custom")
async def editevent(interaction: discord.Interaction, category: str = "custom"):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    events = load_events()
    evlist = events.get(category.lower(), [])
    if not evlist:
        await interaction.response.send_message(f"No events in {category.upper()}.", ephemeral=True)
        return

    msg = f"📋 Events in {category.upper()}:\n"
    for i, e in enumerate(evlist, start=1):
        dt = datetime.fromisoformat(e["datetime"])
        msg += f"{i}. **{e['name']}** → {dt.strftime('%d %b %Y, %H:%M UTC')} (reminder {e['reminder']}m)\n"

    await interaction.response.send_message(msg + "\nReply with the number of the event you want to edit. Type `exit` to cancel.")
    active_sessions[interaction.user.id] = {"mode": "edit", "category": category.lower(), "step": "choose_id"}

@bot.tree.command(name="removeevent", description="Interactively remove an event (admin only)")
@app_commands.describe(category="Category: kvk or custom")
async def removeevent(interaction: discord.Interaction, category: str = "custom"):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    events = load_events()
    evlist = events.get(category.lower(), [])
    if not evlist:
        await interaction.response.send_message(f"No events in {category.upper()}.", ephemeral=True)
        return

    msg = f"📋 Events in {category.upper()}:\n"
    for i, e in enumerate(evlist, start=1):
        dt = datetime.fromisoformat(e["datetime"])
        msg += f"{i}. **{e['name']}** → {dt.strftime('%d %b %Y, %H:%M UTC')}\n"

    await interaction.response.send_message(msg + "\nReply with the number of the event you want to delete. Type `exit` to cancel.")
    active_sessions[interaction.user.id] = {"mode": "remove", "category": category.lower(), "step": "choose_id"}

# ===== On Message for Interactive Flow =====
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    uid = message.author.id
    if uid in active_sessions:
        session = active_sessions[uid]

        if message.content.lower() == "exit":
            await message.channel.send("❌ Session cancelled.")
            del active_sessions[uid]
            return

        events = load_events()
        evlist = events.get(session["category"], [])

        # Step 1: Choose ID
        if session["step"] == "choose_id":
            if not message.content.isdigit() or not (1 <= int(message.content) <= len(evlist)):
                await message.channel.send("⚠️ Invalid choice. Please enter a valid number or type `exit`.")
                return
            index = int(message.content) - 1
            session["event_index"] = index

            if session["mode"] == "edit":
                await message.channel.send(f"What do you want to edit for **{evlist[index]['name']}**?\nOptions: `name`, `datetime`, `reminder`, `category` (or `exit`)")
                session["step"] = "choose_field"

            elif session["mode"] == "remove":
                event = evlist[index]
                dt = datetime.fromisoformat(event["datetime"])
                await message.channel.send(f"Are you sure you want to delete **{event['name']}** ({dt.strftime('%d %b %Y, %H:%M UTC')})? Type `yes` or `no`.")
                session["step"] = "confirm_remove"

        # Step 2: Edit field choice
        elif session["step"] == "choose_field":
            field = message.content.lower()
            if field not in ["name", "datetime", "reminder", "category"]:
                await message.channel.send("⚠️ Invalid option. Choose `name`, `datetime`, `reminder`, or `category`.")
                return
            session["field"] = field
            session["step"] = "provide_value"
            await message.channel.send(f"Enter new value for **{field}**:")

        # Step 3: Provide new value
        elif session["step"] == "provide_value":
            event = evlist[session["event_index"]]
            field = session["field"]

            if field == "name":
                event["name"] = message.content

            elif field == "datetime":
                if re.match(r"\d{2}-\d{2}-\d{4}", message.content):
                    event["datetime"] = datetime.strptime(message.content, "%d-%m-%Y %H:%M").isoformat()
                else:
                    delta = timedelta()
                    match = re.findall(r"(\d+)([dhm])", message.content)
                    for val, unit in match:
                        if unit == "d": delta += timedelta(days=int(val))
                        elif unit == "h": delta += timedelta(hours=int(val))
                        elif unit == "m": delta += timedelta(minutes=int(val))
                    event["datetime"] = (datetime.utcnow() + delta).isoformat()

            elif field == "reminder":
                if not message.content.isdigit():
                    await message.channel.send("⚠️ Reminder must be a number (minutes). Try again or type `exit`.")
                    return
                event["reminder"] = int(message.content)

            elif field == "category":
                if message.content.lower() not in ["kvk", "custom"]:
                    await message.channel.send("⚠️ Category must be `kvk` or `custom`. Try again or type `exit`.")
                    return
                events[message.content.lower()].append(event)
                evlist.remove(event)

            save_events(events)
            await message.channel.send("✅ Event updated successfully.")
            del active_sessions[uid]

        # Step 4: Confirm remove
        elif session["step"] == "confirm_remove":
            if message.content.lower() == "yes":
                event = evlist.pop(session["event_index"])
                save_events(events)
                await message.channel.send(f"✅ Event **{event['name']}** deleted.")
            else:
                await message.channel.send("❌ Deletion cancelled.")
            del active_sessions[uid]

    await bot.process_commands(message)

# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

bot.run(bot_token)
