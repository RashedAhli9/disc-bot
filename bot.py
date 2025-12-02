# ============================================================
# Abyss Reminder Bot (Final Stable Version)
# Fully dynamic abyssconfig UI (live-updating dropdowns)
# Pretty embed, Round2 toggle, perfect reminders
# ============================================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import pytz
from datetime import datetime, timedelta, date, time
from discord.ui import View, Select, Button, Modal, TextInput
import io
import zipfile

# ============================================================
# GLOBAL CONFIG
# ============================================================

MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490

CUSTOM_FILE = "custom_events.json"
ABYSS_CONFIG_FILE = "abyss_config.json"

ROLE_ID = 1413532222396301322   # Abyss role to ping

# ============================================================
# DEFAULT CONFIG VALUES
# ============================================================

DEFAULT_ABYSS = {
    "days": [1, 4, 6],                # Tue, Fri, Sun
    "hours": [0, 4, 8, 12, 16, 20],   # Abyss hour start times
    "reminder_hours": [0, 4, 8, 12, 16, 20],
    "round2": True
}

# ============================================================
# FILE UTILITIES
# ============================================================

def ensure_file_exists(path, default_data):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default_data, f, indent=2)

def load_json(path, default_data):
    ensure_file_exists(path, default_data)
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ============================================================
# LOAD CONFIG (CRASH PROOF)
# ============================================================

cfg = load_json(ABYSS_CONFIG_FILE, DEFAULT_ABYSS)

# Restore missing keys safely
for k in DEFAULT_ABYSS:
    if k not in cfg:
        cfg[k] = DEFAULT_ABYSS[k]

save_json(ABYSS_CONFIG_FILE, cfg)

ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
ROUND2_ENABLED = cfg["round2"]

# ============================================================
# DISCORD SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
# HELPERS
# ============================================================

def day_name(index):
    names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    return names[index]

def pretty_days(lst):
    return ", ".join(day_name(x) for x in lst)

def pretty_hours(lst):
    return ", ".join(f"{h:02}:00" for h in lst)

async def log_action(msg):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(msg)

def parse_datetime(input_str: str) -> datetime:
    """Parse either absolute datetime or relative format."""
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except:
        pass
    now = datetime.utcnow()
    d=h=m=0
    for part in input_str.split():
        if part.endswith("d"): d = int(part[:-1])
        if part.endswith("h"): h = int(part[:-1])
        if part.endswith("m"): m = int(part[:-1])
    return now + timedelta(days=d, hours=h, minutes=m)

def has_admin(inter):
    if inter.user.id == OWNER_ID:
        return True
    return any(r.permissions.administrator for r in inter.user.roles)

# ============================================================
# ON_READY
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        cmds = await bot.tree.sync()
        print(f"Synced {len(cmds)} commands.")
    except Exception as e:
        print("Sync failed:", e)

    abyss_reminder_loop.start()
    custom_event_loop.start()

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Bot restarted successfully.")

# ============================================================
# WEEKLY EVENT COMMAND
# ============================================================

weekly_events = ["Melee Wheel","Melee Forge","Range Wheel","Range Forge"]
event_emojis = {
    "Range Forge":"🏹",
    "Melee Wheel":"⚔️",
    "Melee Forge":"🔨",
    "Range Wheel":"🎯",
}

start_date = date(2025, 9, 16)

@bot.tree.command(name="weeklyevent", description="Check weekly Abyss rotation")
async def weeklyevent(inter):
    today = date.today()
    sunday = start_date - timedelta(days=start_date.weekday()+1)
    weeks = (today - sunday).days // 7

    this_tue = sunday + timedelta(weeks=weeks, days=2)
    now = datetime.utcnow()

    event_start = datetime.combine(this_tue, time(0,0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks += 1
        this_tue = sunday + timedelta(weeks=weeks, days=2)
        event_start = datetime.combine(this_tue, time(0,0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    nums=["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i in range(4):
        idx = (weeks+i) % 4
        nm = weekly_events[idx]
        emoji = event_emojis.get(nm,"📌")
        ev_date = sunday + timedelta(weeks=weeks+i, days=2)
        base_dt = datetime.combine(ev_date, time(0,0))

        if i==0 and event_start <= now < event_end:
            left = event_end - now
            st = f"🟢 LIVE NOW (ends in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m)"
        else:
            left = base_dt - now
            st = f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"

        msg += f"{nums[i]} {emoji} **{nm}** — <t:{int(base_dt.timestamp())}:F>\n{st}\n\n"

    await inter.response.send_message(msg)

# ============================================================
# ABYSS CONFIG VIEW (LIVE REFRESH)
# ============================================================

class AbyssConfigView(View):
    def __init__(self, days, hours, rem_hours, round2):
        super().__init__(timeout=300)
        self.days = days
        self.hours = hours
        self.rem_hours = rem_hours
        self.round2 = round2

        # Day Select
        self.day_sel = Select(
            placeholder="Select Abyss Days",
            min_values=1, max_values=7,
            options=[
                discord.SelectOption(label=day_name(i), value=str(i), default=(i in days))
                for i in range(7)
            ]
        )
        self.day_sel.callback = self.change_days
        self.add_item(self.day_sel)

        # Hours Select
        self.hour_sel = Select(
            placeholder="Select Abyss Hours",
            min_values=1, max_values=24,
            options=[
                discord.SelectOption(label=f"{h:02}:00", value=str(h), default=(h in hours))
                for h in range(24)
            ]
        )
        self.hour_sel.callback = self.change_hours
        self.add_item(self.hour_sel)

        # Reminder Select (dynamic)
        self.rem_sel = Select(
            placeholder="Select Reminder Hours",
            min_values=0, max_values=len(hours),
            options=[
                discord.SelectOption(label=f"{h:02}:00", value=str(h), default=(h in rem_hours))
                for h in hours
            ]
        )
        self.rem_sel.callback = self.change_reminders
        self.add_item(self.rem_sel)

        # Round2 toggle
        self.round_sel = Select(
            placeholder="Enable Round 2?",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Enabled", value="true", default=round2),
                discord.SelectOption(label="Disabled", value="false", default=not round2),
            ]
        )
        self.round_sel.callback = self.change_round2
        self.add_item(self.round_sel)

        # Save button
        self.save_btn = Button(label="Save", style=discord.ButtonStyle.green)
        self.save_btn.callback = self.save
        self.add_item(self.save_btn)

    # LIVE REFRESH CALLBACKS
    async def change_days(self, inter):
        self.days = [int(v) for v in self.day_sel.values]
        await self.refresh(inter)

    async def change_hours(self, inter):
        self.hours = [int(v) for v in self.hour_sel.values]
        if not self.hours:
            self.hours = []
        self.rem_hours = [h for h in self.rem_hours if h in self.hours]
        await self.refresh(inter)

    async def change_reminders(self, inter):
        self.rem_hours = [int(v) for v in self.rem_sel.values]
        await self.refresh(inter)

    async def change_round2(self, inter):
        self.round2 = (self.round_sel.values[0] == "true")
        await self.refresh(inter)

    async def refresh(self, inter):
        """Rebuild the entire UI dynamically."""
        new = AbyssConfigView(self.days, self.hours, self.rem_hours, self.round2)
        emb = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
        emb.add_field(name="Days", value=pretty_days(self.days) or "None", inline=False)
        emb.add_field(name="Hours", value=pretty_hours(self.hours) or "None", inline=False)
        emb.add_field(name="Reminder Hours", value=pretty_hours(self.rem_hours) or "None", inline=False)
        emb.add_field(name="Round 2", value=("Enabled" if self.round2 else "Disabled"), inline=False)

        await inter.response.edit_message(embed=emb, view=new)

    async def save(self, inter):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg

        ABYSS_DAYS = self.days
        ABYSS_HOURS = self.hours
        REMINDER_HOURS = self.rem_hours
        ROUND2_ENABLED = self.round2

        cfg = {
            "days": ABYSS_DAYS,
            "hours": ABYSS_HOURS,
            "reminder_hours": REMINDER_HOURS,
            "round2": ROUND2_ENABLED
        }
        save_json(ABYSS_CONFIG_FILE, cfg)

        await inter.response.send_message("✅ Abyss Config Saved!", ephemeral=True)

# SLASH COMMAND FOR CONFIG
@bot.tree.command(name="abyssconfig", description="Configure Abyss schedule")
async def abyssconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    emb = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
    emb.add_field(name="Days", value=pretty_days(ABYSS_DAYS), inline=False)
    emb.add_field(name="Hours", value=pretty_hours(ABYSS_HOURS), inline=False)
    emb.add_field(name="Reminder Hours", value=pretty_hours(REMINDER_HOURS), inline=False)
    emb.add_field(name="Round 2", value=("Enabled" if ROUND2_ENABLED else "Disabled"), inline=False)

    view = AbyssConfigView(ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED)
    await inter.response.send_message(embed=emb, view=view, ephemeral=True)

# ============================================================
# CUSTOM EVENTS SYSTEM
# (Add, Edit, Remove, Show)
# ============================================================

ensure_file_exists(CUSTOM_FILE, [])

def load_custom_events():
    return load_json(CUSTOM_FILE, [])

def save_custom_events(events):
    save_json(CUSTOM_FILE, events)

@bot.tree.command(name="kvkevent", description="Show next 4 custom events")
async def kvkevent(inter):
    now = datetime.utcnow()
    events = load_custom_events()

    def to_dt(e):
        return datetime.fromisoformat(e["datetime"])

    events_sorted = sorted(events, key=to_dt)

    upcoming=[]
    for ev in events_sorted:
        dt = to_dt(ev)
        if dt > now:
            upcoming.append(ev)
        if len(upcoming)==4:
            break

    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    msg="📅 **Upcoming Events**\n\n"
    nums=["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i,ev in enumerate(upcoming):
        dt = to_dt(ev)
        left = dt - now
        msg += f"{nums[i]} **{ev['name']}** — <t:{int(dt.timestamp())}:F>\nStarts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m\n\n"

    await inter.response.send_message(msg, ephemeral=True)

# ADD EVENT
class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name")
    dt_input = TextInput(label="Datetime (UTC)", placeholder="DD-MM-YYYY HH:MM or 1d 2h")
    reminder = TextInput(label="Reminder (minutes or 'no')", placeholder="10")

    async def on_submit(self, inter):
        try:
            dt = parse_datetime(self.dt_input.value)
            rem = 0 if self.reminder.value.lower()=="no" else int(self.reminder.value)

            ev = {
                "name": self.name.value,
                "datetime": dt.isoformat(),
                "reminder": rem
            }

            events = load_custom_events()
            events.append(ev)
            save_custom_events(events)

            await inter.response.send_message(f"✅ Added **{ev['name']}** at <t:{int(dt.timestamp())}:F>", ephemeral=True)
            await log_action(f"📝 Event Added: {ev}")

        except Exception as e:
            await inter.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="addevent", description="Add custom event")
async def addevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)
    await inter.response.send_modal(AddEventModal())

# EDIT EVENT
@bot.tree.command(name="editevent", description="Edit a custom event")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    events = load_custom_events()
    if not events:
        return await inter.response.send_message("No events available.", ephemeral=True)

    class PickEvent(Select):
        def __init__(self):
            opts=[
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M"),
                    value=str(i)
                )
                for i,e in enumerate(events)
            ]
            super().__init__(placeholder="Select event", options=opts)

        async def callback(self, inter2):
            idx = int(self.values[0])

            class Editor(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def en(btn, ix):
                    await ix.response.send_message("Enter new name:", ephemeral=True)
                    bot.active_edit = (ix.user.id, idx, "name")

                @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.secondary)
                async def et(btn, ix):
                    await ix.response.send_message("Enter new datetime:", ephemeral=True)
                    bot.active_edit = (ix.user.id, idx, "datetime")

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def er(btn, ix):
                    await ix.response.send_message("Enter reminder minutes or 'no':", ephemeral=True)
                    bot.active_edit = (ix.user.id, idx, "reminder")

            await inter2.response.send_message("Choose field:", view=Editor(), ephemeral=True)

    view=View()
    view.add_item(PickEvent())
    await inter.response.send_message("Select event:", view=view, ephemeral=True)

bot.active_edit = None

@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    if bot.active_edit is None:
        return

    uid, idx, field = bot.active_edit
    if msg.author.id != uid:
        return

    events = load_custom_events()
    if not (0 <= idx < len(events)):
        bot.active_edit=None
        return

    if field=="name":
        events[idx]["name"]=msg.content
        save_custom_events(events)
        await msg.channel.send("✅ Name updated.")
        bot.active_edit=None
        return

    if field=="datetime":
        try:
            events[idx]["datetime"]=parse_datetime(msg.content).isoformat()
            save_custom_events(events)
            await msg.channel.send("✅ Datetime updated.")
        except:
            await msg.channel.send("❌ Invalid datetime.")
        bot.active_edit=None
        return

    if field=="reminder":
        try:
            if msg.content.lower()=="no":
                events[idx]["reminder"]=0
            else:
                val=int(msg.content)
                if val<0: raise ValueError
                events[idx]["reminder"]=val
            save_custom_events(events)
            await msg.channel.send("✅ Reminder updated.")
        except:
            await msg.channel.send("❌ Reminder must be number or 'no'.")
        bot.active_edit=None
        return

# REMOVE EVENT
@bot.tree.command(name="removeevent", description="Delete a custom event")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    events = load_custom_events()
    if not events:
        return await inter.response.send_message("No events available.", ephemeral=True)

    class RemovePick(Select):
        def __init__(self):
            opts=[
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M"),
                    value=str(i)
                )
                for i,e in enumerate(events)
            ]
            super().__init__(placeholder="Select event to remove", options=opts)

        async def callback(self, inter2):
            idx=int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(btn, ix):
                    events2=load_custom_events()
                    if 0 <= idx < len(events2):
                        rm=events2.pop(idx)
                        save_custom_events(events2)
                        await ix.response.send_message(f"🗑 Removed **{rm['name']}**")
                        await log_action(f"🗑 Event Removed: {rm}")
                    else:
                        await ix.response.send_message("❌ Invalid index.")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(btn, ix):
                    await ix.response.send_message("Cancelled.", ephemeral=True)

            await inter2.response.send_message("Confirm deletion:", view=Confirm(), ephemeral=True)

    view=View()
    view.add_item(RemovePick())
    await inter.response.send_message("Select event:", view=view, ephemeral=True)

# ============================================================
# EXPORT / IMPORT
# ============================================================

@bot.tree.command(name="exportconfig", description="Export Abyss + Events config")
async def exportconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    mem=io.BytesIO()
    with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(ABYSS_CONFIG_FILE)
        z.write(CUSTOM_FILE)
    mem.seek(0)

    await inter.response.send_message("📦 Exported config.", file=discord.File(mem,"config.zip"), ephemeral=True)

@bot.tree.command(name="importconfig", description="Import settings ZIP")
async def importconfig(inter, file: discord.Attachment):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)
    if not file.filename.endswith(".zip"):
        return await inter.response.send_message("Upload a ZIP.", ephemeral=True)

    raw=await file.read()
    mem=io.BytesIO(raw)

    try:
        z=zipfile.ZipFile(mem)
    except:
        return await inter.response.send_message("Invalid ZIP.", ephemeral=True)

    abyss=None
    events=None

    for name in z.namelist():
        if name==ABYSS_CONFIG_FILE:
            try: abyss=json.loads(z.read(name))
            except: pass
        if name==CUSTOM_FILE:
            try: events=json.loads(z.read(name))
            except: pass

    changed=[]

    if abyss:
        for k in DEFAULT_ABYSS:
            if k not in abyss:
                abyss[k]=DEFAULT_ABYSS[k]
        save_json(ABYSS_CONFIG_FILE, abyss)
        changed.append("Abyss")

    if events is not None:
        save_custom_events(events)
        changed.append("Events")

    if not changed:
        return await inter.response.send_message("ZIP contained no valid data.", ephemeral=True)

    global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg
    cfg=load_json(ABYSS_CONFIG_FILE,DEFAULT_ABYSS)
    ABYSS_DAYS=cfg["days"]
    ABYSS_HOURS=cfg["hours"]
    REMINDER_HOURS=cfg["reminder_hours"]
    ROUND2_ENABLED=cfg["round2"]

    await inter.response.send_message("Imported:\n"+"\n".join(changed), ephemeral=True)

# ============================================================
# ABYSS REMINDER LOOP
# ============================================================

@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    if now.weekday() not in ABYSS_DAYS:
        return

    ch = bot.get_channel(channel_id)
    if not ch:
        return

    # Round 1 at HH:00
    if now.hour in REMINDER_HOURS and now.minute == 0:
        await ch.send(
            f"<@&{ROLE_ID}>, Abyss will start in 15 minutes!"
        )

    # Round 2 at HH:30
    if ROUND2_ENABLED:
        if now.hour in REMINDER_HOURS and now.minute == 30:
            await ch.send(
                f"<@&{ROLE_ID}>, Round 2 of Abyss will start in 15 minutes!"
            )

# ============================================================
# CUSTOM EVENT REMINDER LOOP
# ============================================================

sent_custom=set()

@tasks.loop(minutes=1)
async def custom_event_loop():
    now=datetime.utcnow().replace(second=0,microsecond=0)
    ch=bot.get_channel(channel_id)
    if not ch:
        return

    events=load_custom_events()
    for ev in events:
        dt=datetime.fromisoformat(ev["datetime"])
        rem=ev["reminder"]

        if rem<=0:
            continue

        rtime = dt - timedelta(minutes=rem)
        key = (ev["name"], rtime.isoformat())

        if rtime <= now < rtime + timedelta(minutes=1):
            if key not in sent_custom:
                await ch.send(
                    f"⏰ Reminder: **{ev['name']}** starts in {rem} minutes! <t:{int(dt.timestamp())}:F>"
                )
                sent_custom.add(key)

    if len(sent_custom) > 300:
        sent_custom.clear()

# ============================================================
# BOT RUN
# ============================================================

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ Missing DISCORD_BOT_TOKEN")
else:
    bot.run(TOKEN)
