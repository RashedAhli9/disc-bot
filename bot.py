import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import os
import json
from datetime import date, timedelta, datetime, time

# ===== Setup =====
MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549      # Abyss reminders channel
update_channel_id = 1332676174995918859  # Bot update notifications channel
OWNER_ID = 1084884048884797490

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CUSTOM_FILE = "custom_events.json"


# ===== JSON Storage =====
def load_custom_events():
    if not os.path.exists(CUSTOM_FILE):
        return []
    with open(CUSTOM_FILE, "r") as f:
        return json.load(f)

def save_custom_events(events):
    with open(CUSTOM_FILE, "w") as f:
        json.dump(events, f, indent=2, default=str)


# ===== Helper Functions =====
def parse_datetime(input_str: str):
    """Parse either DD-MM-YYYY HH:MM (UTC) or relative like 1d 2h 30m"""
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


def has_admin_permission(interaction):
    return (
        interaction.user.id == OWNER_ID
        or any(r.name.lower() == "admin" for r in interaction.user.roles)
    )


# ===== Events =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

    update_channel = bot.get_channel(update_channel_id)
    if update_channel:
        await update_channel.send("🤖 Bot updated and online!")

    check_time.start()
    event_reminder.start()


@tasks.loop(minutes=1)
async def check_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    if now.weekday() in [1, 4]:
        if now.hour in [0, 8, 16] and now.minute == 0:
            channel = bot.get_channel(channel_id)
            await channel.send("<@&1413532222396301322>, Abyss will start in 15 minutes!")
        if now.hour in [0, 8, 16] and now.minute == 30:
            channel = bot.get_channel(channel_id)
            await channel.send("<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes!")


# ===== Weekly Event Command =====
events = ["Range Forge", "Melee Wheel", "Melee Forge", "Range Wheel"]
start_date = date(2025, 9, 16)  # First event: Range Forge
event_emojis = {"Range Forge": "🏹", "Melee Wheel": "⚔️", "Melee Forge": "🔨", "Range Wheel": "🎯"}

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
            status = f"🟢 LIVE NOW (ends in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m)"
        else:
            delta = datetime.combine(event_date, time(0, 0)) - now
            status = f"⏳ Starts in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"

        msg += f"{number_emojis[i]} {emoji} **{event_name}** — <t:{int(datetime.combine(event_date, time(0,0)).timestamp())}:F>\n{status}\n\n"

    await interaction.response.send_message(msg)


# ===== KVK + Custom Events =====
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
    events_all = [(name, dt, "kvk", 10) for name, dt in kvk_events]

    custom = load_custom_events()
    for ev in custom:
        ev_time = datetime.fromisoformat(ev["datetime"])
        events_all.append((ev["name"], ev_time, "custom", ev.get("reminder", 0)))

    events_all = sorted(events_all, key=lambda x: x[1])
    upcoming = []
    for name, dt, source, rem in events_all:
        if dt <= now < dt + timedelta(hours=1):
            upcoming.append((name, dt, "live"))
        elif dt > now:
            upcoming.append((name, dt, "upcoming"))
        if len(upcoming) == 4:
            break

    msg = "📅 **KVK + Custom Events**\n\n"
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i, (name, dt, status_type) in enumerate(upcoming):
        if status_type == "live":
            status = "🟢 LIVE NOW (for 1h)"
        else:
            delta = dt - now
            status = f"⏳ Starts in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"
        msg += f"{number_emojis[i]} {name} — <t:{int(dt.timestamp())}:F>\n{status}\n\n"

    await interaction.response.send_message(msg)


# ===== Add/Edit/Remove Custom Events =====
active_flows = {}

@bot.tree.command(name="addevent", description="Add a custom event (admin only)")
async def addevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.send_message("✍️ Enter event name (or type 'exit' to cancel):", ephemeral=True)
    active_flows[interaction.user.id] = {"step": "name", "data": {}}


@bot.tree.command(name="editevent", description="Edit a custom event (admin only)")
async def editevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    custom = load_custom_events()
    if not custom:
        await interaction.response.send_message("No custom events found.", ephemeral=True)
        return
    msg = "📋 Choose ID to edit:\n"
    for i, ev in enumerate(custom, 1):
        msg += f"{i}. {ev['name']} — <t:{int(datetime.fromisoformat(ev['datetime']).timestamp())}:F>\n"
    await interaction.response.send_message(msg, ephemeral=True)
    active_flows[interaction.user.id] = {"step": "edit_select"}


@bot.tree.command(name="removeevent", description="Remove a custom event (admin only)")
async def removeevent(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    custom = load_custom_events()
    if not custom:
        await interaction.response.send_message("No custom events found.", ephemeral=True)
        return
    msg = "🗑️ Choose ID to remove:\n"
    for i, ev in enumerate(custom, 1):
        msg += f"{i}. {ev['name']} — <t:{int(datetime.fromisoformat(ev['datetime']).timestamp())}:F>\n"
    await interaction.response.send_message(msg, ephemeral=True)
    active_flows[interaction.user.id] = {"step": "remove_select"}


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.author.id not in active_flows:
        return
    flow = active_flows[message.author.id]

    if message.content.lower() == "exit":
        await message.channel.send("❌ Cancelled.")
        del active_flows[message.author.id]
        return

    if flow["step"] == "name":
        flow["data"]["name"] = message.content
        flow["step"] = "datetime"
        await message.channel.send("📅 Enter date/time (UTC) as `DD-MM-YYYY HH:MM` or relative like `1d 2h 30m`:")
    elif flow["step"] == "datetime":
        try:
            dt = parse_datetime(message.content)
            flow["data"]["datetime"] = dt.isoformat()
            flow["step"] = "reminder"
            await message.channel.send("⏰ Enter reminder minutes before event (or 'no'):")
        except Exception:
            await message.channel.send("❌ Invalid date/time. Try again.")
    elif flow["step"] == "reminder":
        if message.content.lower() == "no":
            flow["data"]["reminder"] = 0
        else:
            flow["data"]["reminder"] = int(message.content)
        events = load_custom_events()
        events.append(flow["data"])
        save_custom_events(events)
        await message.channel.send(f"✅ Event added: **{flow['data']['name']}** at <t:{int(datetime.fromisoformat(flow['data']['datetime']).timestamp())}:F>")
        del active_flows[message.author.id]

    elif flow["step"] == "edit_select":
        idx = int(message.content) - 1
        flow["data"]["idx"] = idx
        flow["step"] = "edit_field"
        await message.channel.send("✍️ What do you want to edit? (name / datetime / reminder)")
    elif flow["step"] == "edit_field":
        flow["data"]["field"] = message.content.lower()
        flow["step"] = "edit_value"
        await message.channel.send(f"Enter new value for {flow['data']['field']}:")
    elif flow["step"] == "edit_value":
        custom = load_custom_events()
        idx = flow["data"]["idx"]
        field = flow["data"]["field"]
        if field == "datetime":
            custom[idx]["datetime"] = parse_datetime(message.content).isoformat()
        elif field == "reminder":
            custom[idx]["reminder"] = 0 if message.content.lower() == "no" else int(message.content)
        elif field == "name":
            custom[idx]["name"] = message.content
        save_custom_events(custom)
        await message.channel.send("✅ Event updated.")
        del active_flows[message.author.id]

    elif flow["step"] == "remove_select":
        idx = int(message.content) - 1
        custom = load_custom_events()
        if 0 <= idx < len(custom):
            removed = custom.pop(idx)
            save_custom_events(custom)
            await message.channel.send(f"🗑️ Removed event: {removed['name']}")
        else:
            await message.channel.send("❌ Invalid ID.")
        del active_flows[message.author.id]


# ===== Reminder + Cleanup Loop =====
@tasks.loop(minutes=1)
async def event_reminder():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    channel = bot.get_channel(channel_id)

    # Cleanup expired custom events (silent)
    custom = load_custom_events()
    updated_custom = []
    for ev in custom:
        ev_time = datetime.fromisoformat(ev["datetime"])
        if now > ev_time + timedelta(hours=1):
            continue
        updated_custom.append(ev)
    if len(updated_custom) != len(custom):
        save_custom_events(updated_custom)

    # Build event list
    events = [(name, dt, 10) for name, dt in kvk_events]  # kvk default reminder 10m
    for ev in updated_custom:
        events.append((ev["name"], datetime.fromisoformat(ev["datetime"]), ev.get("reminder", 0)))

    # Check reminders
    for name, dt, reminder in events:
        if reminder > 0 and dt - timedelta(minutes=reminder) == now:
            await channel.send(f"⏰ Reminder: {name} starts in {reminder} minutes! <t:{int(dt.timestamp())}:F>")


# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)
bot.run(bot_token)
