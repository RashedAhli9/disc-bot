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
# CONSTANTS & BASE CONFIG
# ============================================================

MY_TIMEZONE = "UTC"

CHANNEL_ID = 1328658110897983549                 # Abyss reminders channel
LOG_CHANNEL_ID = 1332676174995918859             # Updates + logs
OWNER_ID = 1084884048884797490
ABYSS_ROLE_ID = 1413532222396301322              # <-- CONFIRMED

ABYSS_CONFIG_FILE = "abyss_config.json"
CUSTOM_EVENTS_FILE = "custom_events.json"

DEFAULT_ABYSS = {
    "days": [1, 4, 6],             # Tue, Fri, Sun
    "hours": [0, 4, 8, 12, 16, 20],
    "reminder_hours": [0, 4, 8, 12, 16, 20],
    "round2": True
}

# ============================================================
# SAFE CONFIG LOADER (NEVER CRASH)
# ============================================================

def ensure_file_exists(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=2)

def load_json(path, default):
    ensure_file_exists(path, default)
    with open(path, "r") as f:
        try:
            data = json.load(f)
        except:
            data = default
    return data

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# Load main config
cfg = load_json(ABYSS_CONFIG_FILE, DEFAULT_ABYSS)

# Auto-fix missing keys
for key in DEFAULT_ABYSS:
    if key not in cfg:
        cfg[key] = DEFAULT_ABYSS[key]

save_json(ABYSS_CONFIG_FILE, cfg)

ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
ROUND2_ENABLED = cfg["round2"]

# Custom events
ensure_file_exists(CUSTOM_EVENTS_FILE, [])


# ============================================================
# DISCORD SETUP
# ============================================================

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
active_flows = {}
sent_custom_reminders = set()


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def parse_datetime(text: str) -> datetime:
    """Handles exact datetime or relative times like '1d 2h'."""
    try:
        return datetime.strptime(text, "%d-%m-%Y %H:%M")
    except:
        pass

    now = datetime.utcnow()
    d = h = m = 0
    for p in text.split():
        if p.endswith("d"): d = int(p[:-1])
        elif p.endswith("h"): h = int(p[:-1])
        elif p.endswith("m"): m = int(p[:-1])
    return now + timedelta(days=d, hours=h, minutes=m)

def is_admin(inter):
    return (
        inter.user.id == OWNER_ID or
        any(r.permissions.administrator for r in inter.user.roles)
    )

async def log_action(msg):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(msg)


# ============================================================
# READY EVENT
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands globally")
    except Exception as e:
        print("Sync error:", e)

    abyss_loop.start()
    custom_event_loop.start()

    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send("🤖 Bot is online & updated.")


# ============================================================
# WEEKLY EVENT COMMAND (unchanged)
# ============================================================

weekly_events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
event_icons = {"Range Forge":"🏹","Melee Wheel":"⚔️","Melee Forge":"🔨","Range Wheel":"🎯"}
start_date = date(2025, 9, 16)

@bot.tree.command(name="weeklyevent")
async def weeklyevent(inter):
    today = date.today()
    start_sunday = start_date - timedelta(days=start_date.weekday()+1)
    weeks_passed = (today - start_sunday).days // 7

    this_tue = start_sunday + timedelta(weeks=weeks_passed, days=2)
    now = datetime.utcnow()

    event_start = datetime.combine(this_tue, time(0,0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks_passed += 1
        this_tue = start_sunday + timedelta(weeks=weeks_passed, days=2)
        event_start = datetime.combine(this_tue, time(0,0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    nums = ["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i in range(4):
        idx = (weeks_passed + i) % len(weekly_events)
        name = weekly_events[idx]
        icon = event_icons[name]

        ev_date = start_sunday + timedelta(weeks=weeks_passed+i, days=2)
        base_dt = datetime.combine(ev_date, time(0,0))

        if i==0 and event_start <= now < event_end:
            left = event_end - now
            status = f"🟢 LIVE NOW (ends in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m)"
        else:
            left = base_dt - now
            status = f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"

        msg += f"{nums[i]} {icon} **{name}** — <t:{int(base_dt.timestamp())}:F>\n{status}\n\n"

    await inter.response.send_message(msg)


# ============================================================
# ABYSS CONFIG UI — CLEAN & FULLY FIXED
# ============================================================

class AbyssConfigView(View):
    def __init__(self, inter):
        super().__init__(timeout=300)
        self.inter = inter

        # DAY SELECT
        day = Select(
            placeholder="Select Abyss Days",
            min_values=1,
            max_values=7,
            options=[
                discord.SelectOption(label="Monday", value="0"),
                discord.SelectOption(label="Tuesday", value="1"),
                discord.SelectOption(label="Wednesday", value="2"),
                discord.SelectOption(label="Thursday", value="3"),
                discord.SelectOption(label="Friday", value="4"),
                discord.SelectOption(label="Saturday", value="5"),
                discord.SelectOption(label="Sunday", value="6"),
            ],
            default_values=[str(x) for x in ABYSS_DAYS]
        )
        day.callback = self.day_callback
        self.day_select = day
        self.add_item(day)

        # HOUR SELECT (0–23)
        hour = Select(
            placeholder="Select Abyss Hours (UTC)",
            min_values=1,
            max_values=24,
            options=[discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in range(24)],
            default_values=[str(x) for x in ABYSS_HOURS]
        )
        hour.callback = self.hour_callback
        self.hour_select = hour
        self.add_item(hour)

        # REMINDER HOURS — depends on selected hours (filtered)
        rem = Select(
            placeholder="Select Reminder Hours",
            min_values=0,
            max_values=24,
            options=[discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in ABYSS_HOURS],
            default_values=[str(x) for x in REMINDER_HOURS if x in ABYSS_HOURS]
        )
        rem.callback = self.reminder_callback
        self.reminder_select = rem
        self.add_item(rem)

        # ROUND 2
        r2 = Select(
            placeholder="Enable Round 2?",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Enabled", value="true"),
                discord.SelectOption(label="Disabled", value="false"),
            ],
            default_values=["true" if ROUND2_ENABLED else "false"]
        )
        r2.callback = self.round2_callback
        self.round2_select = r2
        self.add_item(r2)

        # SAVE BUTTON
        self.add_item(AbyssSaveButton())

    async def day_callback(self, i):
        await i.response.defer()

    async def hour_callback(self, i):
        # rebuild reminder list to match hour list
        new_hours = [int(v) for v in self.hour_select.values]
        self.reminder_select.options = [
            discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in new_hours
        ]
        await i.response.defer()

    async def reminder_callback(self, i):
        await i.response.defer()

    async def round2_callback(self, i):
        await i.response.defer()


class AbyssSaveButton(Button):
    def __init__(self):
        super().__init__(label="Save", style=discord.ButtonStyle.green)

    async def callback(self, inter):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg

        view: AbyssConfigView = self.view

        ABYSS_DAYS = [int(x) for x in view.day_select.values]
        ABYSS_HOURS = [int(x) for x in view.hour_select.values]
        REMINDER_HOURS = [int(x) for x in view.reminder_select.values]
        ROUND2_ENABLED = (view.round2_select.values[0] == "true")

        cfg = {
            "days": ABYSS_DAYS,
            "hours": ABYSS_HOURS,
            "reminder_hours": REMINDER_HOURS,
            "round2": ROUND2_ENABLED
        }

        save_json(ABYSS_CONFIG_FILE, cfg)
        await inter.response.send_message("✅ Config saved!", ephemeral=True)


@bot.tree.command(name="abyssconfig")
async def abyssconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    emb = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
    emb.add_field(name="Days", value=str(ABYSS_DAYS))
    emb.add_field(name="Hours", value=str(ABYSS_HOURS))
    emb.add_field(name="Reminders", value=str(REMINDER_HOURS))
    emb.add_field(name="Round 2", value=str(ROUND2_ENABLED))

    await inter.response.send_message(embed=emb, view=AbyssConfigView(inter), ephemeral=True)


# ============================================================
# CUSTOM EVENTS (addevent, editevent, etc.) — UNCHANGED & FIXED
# ============================================================

def load_events():
    return load_json(CUSTOM_EVENTS_FILE, [])

def save_events(ev):
    save_json(CUSTOM_EVENTS_FILE, ev)


@bot.tree.command(name="kvkevent")
async def kvkevent(inter):
    now = datetime.utcnow()
    events = load_events()

    def to_dt(ev): return datetime.fromisoformat(ev["datetime"])
    events_sorted = sorted(events, key=to_dt)

    upcoming = []
    for ev in events_sorted:
        dt = datetime.fromisoformat(ev["datetime"])
        if dt <= now < dt + timedelta(hours=1):
            upcoming.append((ev["name"], dt, "live"))
        elif dt > now:
            upcoming.append((ev["name"], dt, "upcoming"))
        if len(upcoming)==4: break

    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    msg = "📅 **Upcoming Events**\n\n"
    icons = ["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i,(name, dt, state) in enumerate(upcoming):
        if state=="live":
            left = (dt + timedelta(hours=1)) - now
            mins = left.seconds//60
            st=f"🟢 LIVE (ends in ~{mins}m)"
        else:
            left = dt-now
            st=f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"
        msg+=f"{icons[i]} **{name}** — <t:{int(dt.timestamp())}:F>\n{st}\n\n"

    await inter.response.send_message(msg)


# ADD EVENT
class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Name")
    dt = TextInput(label="Datetime", placeholder="DD-MM-YYYY HH:MM or 1d 2h")
    rem = TextInput(label="Reminder", placeholder="10 or 'no'")

    async def on_submit(self, inter):
        try:
            dt = parse_datetime(self.dt.value)
            r = 0 if self.rem.value.lower()=="no" else int(self.rem.value)

            ev = {"name":self.name.value, "datetime":dt.isoformat(), "reminder":r}
            evs = load_events()
            evs.append(ev)
            save_events(evs)

            await inter.response.send_message(f"✅ Added **{ev['name']}**", ephemeral=True)
            await log_action(f"📝 Added event: {ev}")
        except:
            await inter.response.send_message("❌ Invalid input", ephemeral=True)

@bot.tree.command(name="addevent")
async def addevent(inter):
    if not is_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)
    await inter.response.send_modal(AddEventModal())


# EDIT EVENT
@bot.tree.command(name="editevent")
async def editevent(inter):
    if not is_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    evs = load_events()
    if not evs:
        return await inter.response.send_message("No events.", ephemeral=True)

    class SelectEvent(Select):
        def __init__(self):
            opts = []
            for i,e in enumerate(evs):
                t=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC")
                opts.append(discord.SelectOption(label=e["name"], value=str(i), description=t))
            super().__init__(placeholder="Choose event", options=opts)

        async def callback(self, i2):
            idx=int(self.values[0])
            active_flows[inter.user.id]={"idx":idx}

            class Menu(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def n(btn, i3):
                    active_flows[inter.user.id]["field"]="name"
                    await i3.response.send_message("Enter new name:", ephemeral=True)

                @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.secondary)
                async def t(btn, i3):
                    active_flows[inter.user.id]["field"]="datetime"
                    await i3.response.send_message("Enter new time:", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def r(btn, i3):
                    active_flows[inter.user.id]["field"]="reminder"
                    await i3.response.send_message("Enter minutes or 'no':", ephemeral=True)

            await i2.response.send_message("Choose field:", view=Menu(), ephemeral=True)

    await inter.response.send_message("Select event:", view=View().add_item(SelectEvent()), ephemeral=True)


# REMOVE EVENT
@bot.tree.command(name="removeevent")
async def removeevent(inter):
    if not is_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    evs=load_events()
    if not evs:
        return await inter.response.send_message("No events.", ephemeral=True)

    class Sel(Select):
        def __init__(self):
            opts=[]
            for i,e in enumerate(evs):
                t=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC")
                opts.append(discord.SelectOption(label=e["name"], value=str(i), description=t))
            super().__init__(options=opts)

        async def callback(self, i2):
            idx=int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def y(btn,i3):
                    lst=load_events()
                    if idx<len(lst):
                        rm=lst.pop(idx)
                        save_events(lst)
                        await i3.response.send_message(f"🗑 Removed {rm['name']}")
                        await log_action(f"🗑 Removed event {rm}")
                    else:
                        await i3.response.send_message("Invalid index.")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def n(btn,i3):
                    await i3.response.send_message("Cancelled.", ephemeral=True)

            await i2.response.send_message("Confirm delete:", view=Confirm(), ephemeral=True)

    await inter.response.send_message("Pick event:", view=View().add_item(Sel()), ephemeral=True)


# ============================================================
# ON_MESSAGE EDITOR (fixed)
# ============================================================

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    uid=msg.author.id
    if uid not in active_flows: return

    flow=active_flows[uid]
    idx=flow["idx"]
    field=flow["field"]

    evs=load_events()
    if not (0<=idx<len(evs)):
        del active_flows[uid]
        return

    # name
    if field=="name":
        evs[idx]["name"]=msg.content
        save_events(evs)
        del active_flows[uid]
        return await msg.channel.send("✅ Name updated.")

    # datetime
    if field=="datetime":
        try:
            evs[idx]["datetime"]=parse_datetime(msg.content).isoformat()
            save_events(evs)
            del active_flows[uid]
            return await msg.channel.send("✅ Time updated.")
        except:
            del active_flows[uid]
            return await msg.channel.send("❌ Invalid time.")

    # reminder
    if field=="reminder":
        try:
            if msg.content.lower()=="no":
                evs[idx]["reminder"]=0
            else:
                val=int(msg.content)
                if val<0: raise ValueError
                evs[idx]["reminder"]=val

            save_events(evs)
            del active_flows[uid]
            return await msg.channel.send("✅ Reminder updated.")
        except:
            del active_flows[uid]
            return await msg.channel.send("❌ Invalid minutes.")


# ============================================================
# EXPORT / IMPORT CONFIG
# ============================================================

@bot.tree.command(name="exportconfig")
async def exportconfig(inter):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    mem=io.BytesIO()
    with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(ABYSS_CONFIG_FILE)
        z.write(CUSTOM_EVENTS_FILE)

    mem.seek(0)
    await inter.response.send_message(
        "📦 Exported.",
        file=discord.File(mem,"config.zip"),
        ephemeral=True
    )


@bot.tree.command(name="importconfig")
async def importconfig(inter, file:discord.Attachment):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    if not file.filename.endswith(".zip"):
        return await inter.response.send_message("Upload a .zip file.", ephemeral=True)

    raw=await file.read()
    mem=io.BytesIO(raw)

    try:
        z=zipfile.ZipFile(mem)
    except:
        return await inter.response.send_message("❌ Invalid zip.", ephemeral=True)

    new_cfg=None
    new_ev=None

    for name in z.namelist():
        if name==ABYSS_CONFIG_FILE:
            new_cfg=json.loads(z.read(name))
        if name==CUSTOM_EVENTS_FILE:
            new_ev=json.loads(z.read(name))

    imported=[]

    if isinstance(new_ev,list):
        save_events(new_ev)
        imported.append("Events")

    if isinstance(new_cfg,dict):
        for k in DEFAULT_ABYSS:
            if k not in new_cfg: new_cfg[k]=DEFAULT_ABYSS[k]
        save_json(ABYSS_CONFIG_FILE,new_cfg)

        global ABYSS_DAYS,ABYSS_HOURS,REMINDER_HOURS,ROUND2_ENABLED,cfg
        cfg=new_cfg
        ABYSS_DAYS=cfg["days"]
        ABYSS_HOURS=cfg["hours"]
        REMINDER_HOURS=cfg["reminder_hours"]
        ROUND2_ENABLED=cfg["round2"]

        imported.append("Abyss Config")

    if not imported:
        return await inter.response.send_message("No valid data found.", ephemeral=True)

    await inter.response.send_message(f"Imported:\n• " + "\n• ".join(imported), ephemeral=True)


# ============================================================
# ABYSS REMINDER LOOP — EXACT OLD BEHAVIOR
# ============================================================

@tasks.loop(minutes=1)
async def abyss_loop():
    tz=pytz.timezone(MY_TIMEZONE)
    now=datetime.now(tz)

    if now.weekday() not in ABYSS_DAYS:
        return

    ch=bot.get_channel(CHANNEL_ID)
    if not ch: return

    # Round 1 — EXACT HOUR
    if now.minute==0 and now.hour in REMINDER_HOURS:
        await ch.send(f"<@&{ABYSS_ROLE_ID}>, Abyss will start in 15 minutes!")

    # Round 2 — 30 minutes later
    if ROUND2_ENABLED and now.minute==30 and now.hour in REMINDER_HOURS:
        await ch.send(f"<@&{ABYSS_ROLE_ID}>, Round 2 of Abyss will start in 15 minutes!")


# ============================================================
# CUSTOM EVENT REMINDER LOOP
# ============================================================

@tasks.loop(minutes=1)
async def custom_event_loop():
    global sent_custom_reminders
    now=datetime.utcnow().replace(second=0,microsecond=0)
    ch=bot.get_channel(CHANNEL_ID)
    if not ch: return

    events=load_events()
    for ev in events:
        dt=datetime.fromisoformat(ev["datetime"])
        rem=ev.get("reminder",0)

        if rem<=0: continue
        rt=dt-timedelta(minutes=rem)
        key=(ev["name"],rt.isoformat())

        if rt<=now<rt+timedelta(minutes=1):
            if key not in sent_custom_reminders:
                await ch.send(f"⏰ **{ev['name']}** starts in {rem} minutes! <t:{int(dt.timestamp())}:F>")
                sent_custom_reminders.add(key)

    if len(sent_custom_reminders)>300:
        sent_custom_reminders=set(list(sent_custom_reminders)[-100:])


# ============================================================
# BOT RUN
# ============================================================

TOKEN=os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ Missing bot token!")
else:
    bot.run(TOKEN)
