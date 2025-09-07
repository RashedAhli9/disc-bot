import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import pytz
import os
from datetime import date, timedelta, datetime

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

@bot.tree.command(name="checkevent", description="Check this week's and next week's Abyss event")
async def checkevent(interaction: discord.Interaction):
    today = date.today()

    # Find the Sunday of the starting week (before 9/9)
    start_sunday = start_date - timedelta(days=start_date.weekday() + 1)

    # How many Sundays have passed since then
    weeks_passed = (today - start_sunday).days // 7

    # Current and next event indices
    current_index = weeks_passed % len(events)
    next_index = (current_index + 1) % len(events)

    # Current and next Tuesday dates (event days)
    this_week_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
    next_week_tuesday = start_sunday + timedelta(weeks=weeks_passed + 1, days=2)

    # Decide which event is next based on today's date
    now = datetime.utcnow()
    if now.date() < this_week_tuesday:
        # Countdown to this week's event
        target_event = events[current_index]
        target_date = this_week_tuesday
    else:
        # Countdown to next week's event
        target_event = events[next_index]
        target_date = next_week_tuesday

    # Countdown calculation
    next_event_datetime = datetime.combine(target_date, datetime.min.time())
    delta = next_event_datetime - now
    days_left = delta.days
    hours_left, remainder = divmod(delta.seconds, 3600)
    minutes_left, _ = divmod(remainder, 60)

    await interaction.response.send_message(
        f"📅 This week's event is **{events[current_index]}** on "
        f"**{this_week_tuesday.strftime('%A, %B %d, %Y')}**\n"
        f"📅 Next week's event is **{events[next_index]}** on "
        f"**{next_week_tuesday.strftime('%A, %B %d, %Y')}**\n\n"
        f"⏳ Time until next event: **{days_left}d {hours_left}h {minutes_left}m** "
        f"({target_event} on {target_date.strftime('%A, %B %d, %Y')})"
    )


# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

bot.run(bot_token)
