import discord
from discord.ext import commands, tasks
import datetime
import pytz

# Use UTC timezone
MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549  # <-- Replace with your channel ID

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    check_time.start()

@tasks.loop(minutes=1)
async def check_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.datetime.now(tz)

    # Tuesday = 1, Friday = 4  (Python weekday: Monday = 0)
    if now.weekday() in [1, 4]:
        if now.hour in [0, 8, 16] and now.minute == 0:
            channel = bot.get_channel(channel_id)
            await channel.send("abyss is starting in 15 minutes!")

bot.run("MTQxMjQ2OTYzNzk5NTY5NjE5OA.Ggwsr0.Wt7n5RRHCEIkg9aakRDug_vlBckxLc0M_4fj90")  # <-- Replace with your bot token

