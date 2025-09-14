import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import os
from datetime import date, timedelta, datetime, time

# ===== Setup =====
MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549  # Replace with your channel ID
OWNER_ID = 1084884048884797490    # Replace with your Discord ID

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Events =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync failed: {e}")
    check_time.start()
    kvk_reminder.start()


@tasks.loop(minutes=1)
async def check_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    if now.weekday() in [1, 4]:  # Tuesday, Friday
        if now.hour in [0, 8, 16] and now.minute == 0:
            channel = bot.get_channel(channel_id)
            await channel.send("<@&1413532222396301322>, Abyss will start in 15 minutes!")

        if now.hour in [0, 8, 16] and now.minute == 30:
            channel = bot.get_channel(channel_id)
            await channel.send("<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes!")


# ===== Basic Commands =====
@bot.tree.command(name="say", description="Make the bot say something")
async def say(interaction: discord.Interaction, message: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You can't use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(message)


@bot.tree.command(name="testreminder", description="Test the Abyss reminder message")
async def testreminder(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You can't use this command.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Test triggered!", ephemeral=True)
    channel = bot.get_channel(channel_id)
    await channel.send("<@&1413532222396301322>, Abyss will start in 15 minutes!")


# ===== Weekly Event Command (Abyss) =====
events = ["Range Forge", "Melee Wheel", "Melee Forge", "Range Wheel"]
start_date = date(2025, 9, 9)  # First event: Range Forge

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

    if now >= event_end:  # skip expired
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
            days, seconds = delta.days, delta.seconds
            hours, minutes = divmod(seconds // 60, 60)
            status = f"🟢 LIVE NOW (ends in {days}d {hours}h {minutes}m)"
        else:
            delta = datetime.combine(event_date, time(0, 0)) - now
            days, seconds = delta.days, delta.seconds
            hours, minutes = divmod(seconds // 60, 60)
            status = f"⏳ Starts in {days}d {hours}h {minutes}m"

        msg += f"{number_emojis[i]} {emoji} **{event_name}** — <t:{int(datetime.combine(event_date, time(0,0)).timestamp())}:F>\n{status}\n\n"

    await interaction.response.send_message(msg)


# ===== KVK Event Command =====
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

@bot.tree.command(name="kvkevent", description="Check the next 4 KVK season events")
async def kvkevent(interaction: discord.Interaction):
    now = datetime.utcnow()
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    msg = "📅 **KVK Season Events**\n\n"

    upcoming = []
    for name, dt in kvk_events:
        if dt <= now < dt + timedelta(hours=1):  # LIVE NOW for 1h
            upcoming.append((name, dt, "live"))
        elif dt > now:
            upcoming.append((name, dt, "upcoming"))

    upcoming = upcoming[:4]

    for i, (name, dt, status_type) in enumerate(upcoming):
        if status_type == "live":
            status = "🟢 LIVE NOW (for 1h)"
        else:
            delta = dt - now
            days, seconds = delta.days, delta.seconds
            hours, minutes = divmod(seconds // 60, 60)
            status = f"⏳ Starts in {days}d {hours}h {minutes}m"

        msg += f"{number_emojis[i]} {name} — <t:{int(dt.timestamp())}:F>\n{status}\n\n"

    await interaction.response.send_message(msg)


# ===== KVK Reminder System =====
@tasks.loop(minutes=1)
async def kvk_reminder():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    channel = bot.get_channel(channel_id)

    for name, dt in kvk_events:
        if dt - timedelta(minutes=10) == now:  # exactly 10 minutes before
            await channel.send(f"⏰ Reminder: {name} starts in 10 minutes! <t:{int(dt.timestamp())}:F>")


# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

bot.run(bot_token)
