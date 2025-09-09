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
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(e)
    check_time.start()

@tasks.loop(minutes=1)
async def check_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    # Tuesday = 1, Friday = 4 (Python weekday: Monday = 0)
    if now.weekday() in [1, 4]:
        # First set: 00:00, 08:00, 16:00
        if now.hour in [0, 8, 16] and now.minute == 0:
            channel = bot.get_channel(channel_id)
            await channel.send("<@&1413532222396301322>, Abyss will start in 15 minutes!")

        # Second set: 00:30, 08:30, 16:30
        if now.hour in [0, 8, 16] and now.minute == 30:
            channel = bot.get_channel(channel_id)
            await channel.send("<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes!")


# ===== Commands =====
@bot.tree.command(name="say", description="Make the bot say something")
async def say(interaction: discord.Interaction, message: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(message)


@bot.tree.command(name="testreminder", description="Test the abyss reminder message")
async def testreminder(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Test triggered!", ephemeral=True)
    channel = bot.get_channel(channel_id)
    await channel.send("<@&1413532222396301322>, Abyss will start in 15 minutes!")


# ===== Check Event Command =====
events = ["Range Forge", "Melee Wheel", "Melee Forge", "Range Wheel"]
start_date = date(2025, 9, 9)  # First event: Range Forge

# Event → Emoji mapping
event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯"
}

@bot.tree.command(name="checkevent", description="Check the next 4 weekly events")
async def checkevent(interaction: discord.Interaction):
    today = date.today()

    # Find the Sunday of the starting week (before 9/9)
    start_sunday = start_date - timedelta(days=start_date.weekday() + 1)

    # How many Sundays have passed since then
    weeks_passed = (today - start_sunday).days // 7

    # Skip past event if we're already past Friday 00:00 UTC
    this_week_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
    now = datetime.utcnow()
    event_start = datetime.combine(this_week_tuesday, time(0, 0))
    event_end = event_start + timedelta(days=3)  # Friday 00:00 UTC
    if now >= event_end:
        weeks_passed += 1

    # Event number emojis
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    msg = "📅 **Upcoming Events (UTC)**\n\n"

    for i in range(4):
        index = (weeks_passed + i) % len(events)
        event_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        event_name = events[index]
        emoji = event_emojis.get(event_name, "📌")

        status = ""
        if i == 0:
            event_start = datetime.combine(event_date, time(0, 0))
            event_end = event_start + timedelta(days=3)  # Friday 00:00 UTC

            if event_start <= now < event_end:
                delta = event_end - now
                days_left = delta.days
                hours_left, remainder = divmod(delta.seconds, 3600)
                minutes_left, _ = divmod(remainder, 60)
                status = f"🟢 LIVE NOW (ends in {days_left}d {hours_left}h {minutes_left}m)"
            elif now < event_start:
                delta = event_start - now
                days_left = delta.days
                hours_left, remainder = divmod(delta.seconds, 3600)
                minutes_left, _ = divmod(remainder, 60)
                status = f"⏳ Starts in {days_left}d {hours_left}h {minutes_left}m"
        else:
            delta = datetime.combine(event_date, time(0, 0)) - now
            days_left = delta.days
            hours_left, remainder = divmod(delta.seconds, 3600)
            minutes_left, _ = divmod(remainder, 60)
            status = f"⏳ Starts in {days_left}d {hours_left}h {minutes_left}m"

        msg += f"{number_emojis[i]} **{event_name}** — {event_date.strftime('%A, %B %d, %Y')}\n{status}\n\n"

    await interaction.response.send_message(msg)


# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

bot.run(bot_token)
