import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import pytz
import os
from keep_alive import keep_alive
from openai import OpenAI

# ===== Setup =====
MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
OWNER_ID = 1084884048884797490  # replace with your Discord ID

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ai_mode = False  # start with AI mode off

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
    now = datetime.datetime.now(tz)
    if now.weekday() in [1, 4]:
        if now.hour in [0, 8, 16] and now.minute == 0:
            channel = bot.get_channel(channel_id)
            await channel.send("abyss is starting in 15 minutes!")

# ===== Commands =====
@bot.tree.command(name="toggleai", description="Toggle Truffles AI mode")
async def toggleai(interaction: discord.Interaction):
    global ai_mode
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You can't toggle Truffles AI mode.", ephemeral=True)
        return
    ai_mode = not ai_mode
    status = "ON 🤖" if ai_mode else "OFF 📴"
    await interaction.response.send_message(f"Truffles AI mode is now **{status}**", ephemeral=True)

@bot.tree.command(name="say", description="Make the bot say something")
async def say(interaction: discord.Interaction, message: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    # Hide your slash command message
    await interaction.response.defer(ephemeral=True)

    # Bot sends the message
    await interaction.channel.send(message)

@bot.tree.command(name="testreminder", description="Test the abyss reminder message")
async def testreminder(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_message("✅ Test triggered!", ephemeral=True)
    channel = bot.get_channel(channel_id)
    await channel.send("abyss is starting in 15 minutes!")

# ===== AI Mode =====
@bot.event
async def on_message(message):
    global ai_mode
    if ai_mode and not message.author.bot:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                      "role": "system",
                      "content": (
                        "You are Truffles, a member of this Discord server. "
                        "You always speak in the first person as if you are the real Truffles. "
                        "Your personality is dramatic, annoying in a playful way, and very sassy. "
                        "You constantly brag, act sarcastic, and make everything about yourself. "
                        "You are always proudly calling yourself an 'amerifat', treating it like a special badge of honor. "
                        "You also live in New York City and love to remind people about it in a dramatic way. "
                        "Stay in character and never admit you are a bot."
                      )
                    },
                    {"role": "user", "content": message.content}
                ]
            )
            reply = response.choices[0].message.content.strip()
            await message.channel.send(reply)
        except Exception as e:
            print(f"Error with AI reply: {e}")

    # Keep normal bot commands working
    await bot.process_commands(message)

# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

keep_alive()
bot.run(bot_token)
import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import pytz
import os
from keep_alive import keep_alive
from openai import OpenAI

# ===== Setup =====
MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
OWNER_ID = 1084884048884797490  # replace with your Discord ID

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ai_mode = False  # start with AI mode off

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
    now = datetime.datetime.now(tz)
    if now.weekday() in [1, 4]:
        if now.hour in [0, 8, 16] and now.minute == 0:
            channel = bot.get_channel(channel_id)
            await channel.send("abyss is starting in 15 minutes!")

# ===== Commands =====
@bot.tree.command(name="toggleai", description="Toggle Truffles AI mode")
async def toggleai(interaction: discord.Interaction):
    global ai_mode
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You can't toggle Truffles AI mode.", ephemeral=True)
        return
    ai_mode = not ai_mode
    status = "ON 🤖" if ai_mode else "OFF 📴"
    await interaction.response.send_message(f"Truffles AI mode is now **{status}**", ephemeral=True)

@bot.tree.command(name="say", description="Make the bot say something")
async def say(interaction: discord.Interaction, message: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    # Hide your slash command message
    await interaction.response.defer(ephemeral=True)

    # Bot sends the message
    await interaction.channel.send(message)

@bot.tree.command(name="testreminder", description="Test the abyss reminder message")
async def testreminder(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_message("✅ Test triggered!", ephemeral=True)
    channel = bot.get_channel(channel_id)
    await channel.send("abyss is starting in 15 minutes!")

# ===== AI Mode =====
@bot.event
async def on_message(message):
    global ai_mode
    if ai_mode and not message.author.bot:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                      "role": "system",
                      "content": (
                        "You are Truffles, a member of this Discord server. "
                        "You always speak in the first person as if you are the real Truffles. "
                        "Your personality is dramatic, annoying in a playful way, and very sassy. "
                        "You constantly brag, act sarcastic, and make everything about yourself. "
                        "You are always proudly calling yourself an 'amerifat', treating it like a special badge of honor. "
                        "You also live in New York City and love to remind people about it in a dramatic way. "
                        "Stay in character and never admit you are a bot."
                      )
                    },
                    {"role": "user", "content": message.content}
                ]
            )
            reply = response.choices[0].message.content.strip()
            await message.channel.send(reply)
        except Exception as e:
            print(f"Error with AI reply: {e}")

    # Keep normal bot commands working
    await bot.process_commands(message)

# ===== Run Bot =====
bot_token = os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    print("❌ Error: DISCORD_BOT_TOKEN not set")
    exit(1)

keep_alive()
bot.run(bot_token)
