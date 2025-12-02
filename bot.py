import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
import json, os, pytz, io, zipfile
from datetime import datetime, timedelta, date, time

# ============================================================
# CONFIG + CONSTANTS
# ============================================================

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OWNER_ID = 1084884048884797490
MY_TIMEZONE = "UTC"

channel_id = 1328658110897983549
update_channel_id = 1332676174995918859

CUSTOM_FILE = "custom_events.json"
ABYSS_CONFIG_FILE = "abyss_config.json"

DEFAULT_CFG = {
    "days": [1, 4, 6],
    "hours": [0, 4, 8, 12, 16, 20],
    "reminder_hours": [0, 4, 8, 12, 16, 20],
    "round2": True
}

# ============================================================
# FILE HELPERS
# ============================================================

def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f: json.dump(default, f, indent=2)
        return default
    try:
        with open(path, "r") as f: return json.load(f)
    except:
        with open(path, "w") as f: json.dump(default, f, indent=2)
        return default

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

cfg = load_json(ABYSS_CONFIG_FILE, DEFAULT_CFG)
ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
ROUND2_ENABLED = cfg["round2"]

def load_events(): return load_json(CUSTOM_FILE, [])
def save_events(data): save_json(CUSTOM_FILE, data)

# ============================================================
# DISCORD SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def log(msg):
    ch = bot.get_channel(update_channel_id)
    if ch: await ch.send(msg)

def parse_dt(s):
    try: return datetime.strptime(s, "%d-%m-%Y %H:%M")
    except: pass
    now = datetime.utcnow()
    d=h=m=0
    for p in s.split():
        if p.endswith("d"): d=int(p[:-1])
        if p.endswith("h"): h=int(p[:-1])
        if p.endswith("m"): m=int(p[:-1])
    return now + timedelta(days=d, hours=h, minutes=m)

def is_admin(i):
    return i.user.id == OWNER_ID or any(r.permissions.administrator for r in i.user.roles)

# ============================================================
# READY + SYNC
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        s = await bot.tree.sync()
        print(f"Synced {len(s)} commands")
    except Exception as e:
        print("Sync error:", e)
    abyss_loop.start()
    custom_loop.start()
    await log("🤖 Bot updated & online!")

# ============================================================
# WEEKLY EVENT
# ============================================================

weekly_events = ["Melee Wheel","Melee Forge","Range Wheel","Range Forge"]
event_emoji = {"Range Forge":"🏹","Melee Wheel":"⚔️","Melee Forge":"🔨","Range Wheel":"🎯"}
start_date = date(2025,9,16)

@bot.tree.command(name="weeklyevent")
async def weeklyevent(inter):
    today = date.today()
    base_sun = start_date - timedelta(days=start_date.weekday()+1)
    weeks = (today - base_sun).days//7
    tuesday = base_sun + timedelta(weeks=weeks,days=2)

    now = datetime.utcnow()
    st = datetime.combine(tuesday, time(0,0))
    en = st + timedelta(days=3)
    if now>=en:
        weeks+=1
        tuesday = base_sun + timedelta(weeks=weeks,days=2)
        st = datetime.combine(tuesday, time(0,0))
        en = st + timedelta(days=3)

    msg="📅 **Weekly Abyss Events**\n\n"
    nums=["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i in range(4):
        idx=(weeks+i)%4
        name=weekly_events[idx]
        emoji=event_emoji.get(name,"📌")
        evd = base_sun + timedelta(weeks=weeks+i,days=2)
        dt = datetime.combine(evd,time(0,0))
        if i==0 and st<=now<en:
            left=en-now
            stt=f"🟢 LIVE NOW (ends in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m)"
        else:
            left=dt-now
            stt=f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"
        msg+=f"{nums[i]} {emoji} **{name}** — <t:{int(dt.timestamp())}:F>\n{stt}\n\n"

    await inter.response.send_message(msg)

# ============================================================
# ABYSS CONFIG — FULL TOGGLE UI
# ============================================================

class Toggle(Button):
    def __init__(self, label, key, state_dict):
        self.key = key
        self.state = state_dict
        style = discord.ButtonStyle.green if state_dict[key] else discord.ButtonStyle.secondary
        super().__init__(label=label, style=style)

    async def callback(self, inter):
        self.state[self.key] = not self.state[self.key]
        self.style = discord.ButtonStyle.green if self.state[self.key] else discord.ButtonStyle.secondary
        await inter.response.edit_message(view=self.view)

class AbyssConfigView(View):
    def __init__(self, i):
        super().__init__(timeout=300)
        self.user = i.user.id

        # Local live state
        self.days = {d:(d in ABYSS_DAYS) for d in range(7)}
        self.hours = {h:(h in ABYSS_HOURS) for h in range(24)}
        self.rem = {h:(h in REMINDER_HOURS) for h in ABYSS_HOURS}
        self.r2 = {"r2": ROUND2_ENABLED}

        # --- Days ---
        day_names=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        for d in range(7):
            self.add_item(Toggle(day_names[d], d, self.days))

        # --- Hours (3 rows × 8) ---
        for h in range(24):
            self.add_item(Toggle(f"{h:02}", h, self.hours))

        # --- Round2 toggle ---
        self.add_item(Toggle("Round2", "r2", self.r2))

        # --- Save button ---
        self.add_item(Button(label="💾 Save", style=discord.ButtonStyle.blurple, custom_id="save"))

    async def interaction_check(self, inter):
        return inter.user.id == self.user

    @discord.ui.button(label="SAVE_HIDDEN", style=discord.ButtonStyle.blurple, custom_id="save", row=10)
    async def save_config(self, inter, btn):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg

        ABYSS_DAYS = [d for d,v in self.days.items() if v]
        ABYSS_HOURS = [h for h,v in self.hours.items() if v]
        REMINDER_HOURS = [h for h in ABYSS_HOURS if self.rem.get(h, False)]
        ROUND2_ENABLED = self.r2["r2"]

        cfg = {
            "days": ABYSS_DAYS,
            "hours": ABYSS_HOURS,
            "reminder_hours": REMINDER_HOURS,
            "round2": ROUND2_ENABLED
        }
        save_json(ABYSS_CONFIG_FILE, cfg)

        await inter.response.send_message("✅ Config Saved!", ephemeral=True)

@bot.tree.command(name="abyssconfig")
async def abyssconfig(inter):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)
    emb = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
    emb.add_field(name="Days",value=str(ABYSS_DAYS),inline=False)
    emb.add_field(name="Hours",value=str(ABYSS_HOURS),inline=False)
    emb.add_field(name="Reminder Hours",value=str(REMINDER_HOURS),inline=False)
    emb.add_field(name="Round2",value=str(ROUND2_ENABLED), inline=False)
    await inter.response.send_message(embed=emb,view=AbyssConfigView(inter),ephemeral=True)

# ============================================================
# KVK: VIEW EVENTS
# ============================================================

@bot.tree.command(name="kvkevent")
async def kvkevent(inter):
    now = datetime.utcnow()
    evs = sorted(load_events(), key=lambda e: datetime.fromisoformat(e["datetime"]))
    out=[]
    for e in evs:
        dt=datetime.fromisoformat(e["datetime"])
        if dt<=now<dt+timedelta(hours=1): out.append((e,"live"))
        elif dt>now: out.append((e,"up"))
        if len(out)==4: break
    if not out:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    msg="📅 **Upcoming Events**\n\n"; ic=["1️⃣","2️⃣","3️⃣","4️⃣"]
    for i,(ev,st) in enumerate(out):
        dt=datetime.fromisoformat(ev["datetime"])
        if st=="live":
            left=(dt+timedelta(hours=1))-now
            m=max(1,left.seconds//60)
            s=f"🟢 LIVE (ends ~{m}m)"
        else:
            left=dt-now
            s=f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"
        msg+=f"{ic[i]} **{ev['name']}** — <t:{int(dt.timestamp())}:F>\n{s}\n\n"
    await inter.response.send_message(msg)

# ============================================================
# ADD EVENT
# ============================================================

class AddEventModal(discord.ui.Modal, title="➕ Add Event"):
    name = discord.ui.TextInput(label="Event Name")
    dt = discord.ui.TextInput(label="Datetime UTC",placeholder="DD-MM-YYYY HH:MM or 1d 2h")
    rem = discord.ui.TextInput(label="Reminder (min or 'no')",placeholder="10")

    async def on_submit(self, inter):
        try:
            dt = parse_dt(self.dt.value)
            r = 0 if self.rem.value.lower()=="no" else int(self.rem.value)
            ev = {"name":self.name.value,"datetime":dt.isoformat(),"reminder":r}
            data=load_events(); data.append(ev); save_events(data)
            await inter.response.send_message(f"✅ Added **{ev['name']}**",ephemeral=True)
            await log(f"📝 Added {ev}")
        except Exception as e:
            await inter.response.send_message(str(e),ephemeral=True)

@bot.tree.command(name="addevent")
async def addevent(inter):
    if not is_admin(inter):
        return await inter.response.send_message("❌ No permission.",ephemeral=True)
    await inter.response.send_modal(AddEventModal())

# ============================================================
# EDIT / REMOVE EVENTS (Optimized View)
# ============================================================

active_flows={}

@bot.tree.command(name="editevent")
async def editevent(inter):
    if not is_admin(inter): return await inter.response.send_message("❌",ephemeral=True)
    evs=load_events()
    if not evs: return await inter.response.send_message("No events.",ephemeral=True)

    class Picker(View):
        def __init__(self): super().__init__(timeout=60)
    v=Picker()
    for i,e in enumerate(evs):
        async def cb(i2,idx=i):
            active_flows[inter.user.id]={"idx":idx}
            await i2.response.send_message("Type new value:\n(name/datetime/reminder)",ephemeral=True)
        b=Button(label=e["name"],style=discord.ButtonStyle.blurple)
        b.callback=cb; v.add_item(b)
    await inter.response.send_message("Select event:",view=v,ephemeral=True)

@bot.tree.command(name="removeevent")
async def removeevent(inter):
    if not is_admin(inter): return await inter.response.send_message("❌",ephemeral=True)
    evs=load_events()
    if not evs: return await inter.response.send_message("No events.",ephemeral=True)

    class Picker(View):
        def __init__(self): super().__init__(timeout=60)
    v=Picker()
    for i,e in enumerate(evs):
        async def cb(i2,idx=i):
            evs=load_events()
            if idx<len(evs):
                rm=evs.pop(idx); save_events(evs)
                await i2.response.send_message(f"🗑 Removed {rm['name']}")
                await log(f"Removed {rm}")
        b=Button(label=e["name"],style=discord.ButtonStyle.danger)
        b.callback=cb; v.add_item(b)
    await inter.response.send_message("Select event:",view=v,ephemeral=True)

# ============================================================
# ON MESSAGE EDIT FLOW
# ============================================================

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    uid=msg.author.id
    if uid not in active_flows: return
    flow=active_flows.pop(uid)
    idx=flow["idx"]
    evs=load_events()
    if not(0<=idx<len(evs)): return

    content=msg.content
    if content.lower().startswith("name "):
        evs[idx]["name"]=content[5:].strip()
    elif content.lower().startswith("datetime "):
        evs[idx]["datetime"]=parse_dt(content[9:].strip()).isoformat()
    elif content.lower().startswith("reminder "):
        val=content[9:].strip()
        evs[idx]["reminder"]=0 if val=="no" else int(val)
    else:
        return

    save_events(evs)
    await msg.channel.send("✅ Updated.")
    await log("Edited event")

# ============================================================
# EXPORT / IMPORT CONFIG
# ============================================================

@bot.tree.command(name="exportconfig")
async def exportconfig(inter):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌",ephemeral=True)
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(ABYSS_CONFIG_FILE); z.write(CUSTOM_FILE)
    mem.seek(0)
    await inter.response.send_message("📦 Exported!",file=discord.File(mem,"config.zip"),ephemeral=True)

def valid_events(d):
    return isinstance(d,list) and all(isinstance(x,dict) and "name" in x for x in d)

def valid_cfg(d):
    return all(k in d for k in ["days","hours","reminder_hours","round2"])

@bot.tree.command(name="importconfig")
async def importconfig(inter, file: discord.Attachment):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌",ephemeral=True)
    if not file.filename.endswith(".zip"):
        return await inter.response.send_message("❌ Must be zip.",ephemeral=True)
    raw=await file.read()
    try: z=zipfile.ZipFile(io.BytesIO(raw))
    except: return await inter.response.send_message("❌ Invalid zip",ephemeral=True)

    events=None; cfg2=None
    for n in z.namelist():
        if n==CUSTOM_FILE: events=json.loads(z.read(n))
        if n==ABYSS_CONFIG_FILE: cfg2=json.loads(z.read(n))

    imported=[]
    if events and valid_events(events):
        save_events(events); imported.append("Events")
    if cfg2 and valid_cfg(cfg2):
        save_json(ABYSS_CONFIG_FILE,cfg2)
        global ABYSS_DAYS,ABYSS_HOURS,REMINDER_HOURS,ROUND2_ENABLED,cfg
        cfg=cfg2
        ABYSS_DAYS=cfg["days"]; ABYSS_HOURS=cfg["hours"]
        REMINDER_HOURS=cfg["reminder_hours"]; ROUND2_ENABLED=cfg["round2"]
        imported.append("Abyss Config")

    if not imported:
        return await inter.response.send_message("⚠ Nothing imported.",ephemeral=True)
    await inter.response.send_message("Imported:\n"+", ".join(imported),ephemeral=True)

# ============================================================
# ABYSS REMINDER LOOP — EXACT OLD BEHAVIOR
# ============================================================

@tasks.loop(minutes=1)
async def abyss_loop():
    tz=pytz.timezone(MY_TIMEZONE)
    now=datetime.now(tz)
    if now.weekday() not in ABYSS_DAYS: return
    ch=bot.get_channel(channel_id)
    if not ch: return

    # Round 1 — EXACT old logic
    if now.hour in REMINDER_HOURS and now.minute==0:
        await ch.send(f"<@&1413532222396301322>, Abyss will start in 15 minutes!")

    # Round 2 — EXACT old logic
    if ROUND2_ENABLED and now.hour in REMINDER_HOURS and now.minute==30:
        await ch.send(f"<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes!")

# ============================================================
# CUSTOM EVENT REMINDER LOOP
# ============================================================

sent_custom=set()

@tasks.loop(minutes=1)
async def custom_loop():
    now=datetime.utcnow().replace(second=0,microsecond=0)
    ch=bot.get_channel(channel_id)
    if not ch: return
    evs=load_events()
    for ev in evs:
        dt=datetime.fromisoformat(ev["datetime"])
        rem=ev["reminder"]
        if rem<=0: continue
        rt=dt-timedelta(minutes=rem)
        key=(ev["name"],rt.isoformat())
        if rt<=now<rt+timedelta(minutes=1) and key not in sent_custom:
            await ch.send(f"⏰ **{ev['name']}** starts in {rem} minutes! <t:{int(dt.timestamp())}:F>")
            sent_custom.add(key)
    if len(sent_custom)>200:
        sent_custom=set(list(sent_custom)[-100:])

# ============================================================
# RUN BOT
# ============================================================

if not TOKEN: print("❌ Missing token")
else: bot.run(TOKEN)
