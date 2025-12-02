import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, pytz, io, zipfile
from datetime import datetime, timedelta, date, time
from discord.ui import View, Select, Button

# =========================================
# CONFIG
# =========================================
MY_TIMEZONE = "UTC"
CHANNEL_ID = 1328658110897983549
UPDATE_CHANNEL_ID = 1332676174995918859
OWNER_ID = 1084884048884797490

ABYSS_CONFIG_FILE = "abyss_config.json"
CUSTOM_FILE = "custom_events.json"

DEFAULT_ABYSS = {
    "days": [1,4,6],
    "hours": [0,4,8,12,16,20],
    "reminder_hours": [0,4,8,12,16,20],
    "round2": True
}

def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path,"w") as f:
            json.dump(default,f,indent=2)

def load_json(path, default):
    ensure_file(path, default)
    with open(path,"r") as f:
        return json.load(f)

def save_json(path,data):
    with open(path,"w") as f:
        json.dump(data,f,indent=2)

# Load Abyss config safely
def load_or_reset_abyss():
    try:
        with open(ABYSS_CONFIG_FILE,"r") as f:
            d=json.load(f)
        for k in DEFAULT_ABYSS:
            if k not in d:
                raise KeyError
        return d
    except:
        save_json(ABYSS_CONFIG_FILE,DEFAULT_ABYSS)
        return DEFAULT_ABYSS.copy()

cfg = load_or_reset_abyss()
ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
ROUND2_ENABLED = cfg["round2"]

# Load custom events
ensure_file(CUSTOM_FILE, [])
def load_events():
    return load_json(CUSTOM_FILE,[])
def save_events(d):
    save_json(CUSTOM_FILE,d)

# =========================================
# DISCORD SETUP
# =========================================
intents = discord.Intents.default()
intents.messages=True
intents.message_content=True
bot = commands.Bot(command_prefix="!", intents=intents)

active_edits={}
sent_custom=set()

def parse_dt(s):
    try:
        return datetime.strptime(s,"%d-%m-%Y %H:%M")
    except:
        now=datetime.utcnow()
        d=h=m=0
        for p in s.split():
            if p.endswith("d"): d=int(p[:-1])
            elif p.endswith("h"): h=int(p[:-1])
            elif p.endswith("m"): m=int(p[:-1])
        return now+timedelta(days=d,hours=h,minutes=m)

def is_admin(inter):
    return inter.user.id==OWNER_ID or any(r.permissions.administrator for r in inter.user.roles)

async def log_action(msg):
    ch=bot.get_channel(UPDATE_CHANNEL_ID)
    if ch: await ch.send(msg)

# =========================================
# READY
# =========================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        s=await bot.tree.sync()
        print(f"Synced {len(s)} commands")
    except Exception as e:
        print(e)
    abyss_loop.start()
    custom_loop.start()
    ch=bot.get_channel(UPDATE_CHANNEL_ID)
    if ch: await ch.send("🤖 Bot updated and online!")

# =========================================
# /abyssconfig UI
# =========================================
class AbyssConfigView(View):
    def __init__(self, inter):
        super().__init__(timeout=600)

        self.day_sel = Select(
            placeholder="Select Abyss Days",
            min_values=1, max_values=7,
            options=[
                discord.SelectOption(label="Monday",value="0"),
                discord.SelectOption(label="Tuesday",value="1"),
                discord.SelectOption(label="Wednesday",value="2"),
                discord.SelectOption(label="Thursday",value="3"),
                discord.SelectOption(label="Friday",value="4"),
                discord.SelectOption(label="Saturday",value="5"),
                discord.SelectOption(label="Sunday",value="6")
            ]
        )
        self.day_sel.values=[str(x) for x in ABYSS_DAYS]
        self.day_sel.callback=self.day_cb
        self.add_item(self.day_sel)

        self.hour_sel = Select(
            placeholder="Select Abyss Hours",
            min_values=1, max_values=24,
            options=[discord.SelectOption(label=f"{h:02}:00",value=str(h)) for h in range(24)]
        )
        self.hour_sel.values=[str(x) for x in ABYSS_HOURS]
        self.hour_sel.callback=self.hour_cb
        self.add_item(self.hour_sel)

        # reminder hours must be subset of selected hours
        self.rem_sel = Select(
            placeholder="Select Reminder Hours",
            min_values=0, max_values=24,
            options=[discord.SelectOption(label=f"{h:02}:00", value=str(h)) for h in ABYSS_HOURS]
        )
        self.rem_sel.values=[str(x) for x in REMINDER_HOURS if x in ABYSS_HOURS]
        self.rem_sel.callback=self.rem_cb
        self.add_item(self.rem_sel)

        self.r2_sel = Select(
            placeholder="Round 2?",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Enabled",value="true"),
                discord.SelectOption(label="Disabled",value="false")
            ]
        )
        self.r2_sel.values=["true" if ROUND2_ENABLED else "false"]
        self.r2_sel.callback=self.r2_cb
        self.add_item(self.r2_sel)

        self.add_item(AbyssSaveBtn(self))

    async def day_cb(self,i):
        self.day_sel.values=self.day_sel.values
        await i.response.defer()

    async def hour_cb(self,i):
        self.hour_sel.values=self.hour_sel.values
        # rebuild reminder list to only show selected hours
        hrs=[int(x) for x in self.hour_sel.values]
        self.rem_sel.options=[discord.SelectOption(label=f"{h:02}:00",value=str(h)) for h in hrs]
        # clean invalid reminder values
        self.rem_sel.values=[x for x in self.rem_sel.values if int(x) in hrs]
        await i.response.edit_message(view=self)

    async def rem_cb(self,i):
        self.rem_sel.values=self.rem_sel.values
        await i.response.defer()

    async def r2_cb(self,i):
        self.r2_sel.values=self.r2_sel.values
        await i.response.defer()

class AbyssSaveBtn(Button):
    def __init__(self,parent):
        super().__init__(label="Save",style=discord.ButtonStyle.green)
        self.parent=parent

    async def callback(self,i):
        if i.user.id!=OWNER_ID:
            return await i.response.send_message("❌ Owner only.",ephemeral=True)

        global ABYSS_DAYS,ABYSS_HOURS,REMINDER_HOURS,ROUND2_ENABLED,cfg

        ABYSS_DAYS=[int(x) for x in self.parent.day_sel.values]
        ABYSS_HOURS=[int(x) for x in self.parent.hour_sel.values]
        REMINDER_HOURS=[int(x) for x in self.parent.rem_sel.values]
        ROUND2_ENABLED=(self.parent.r2_sel.values[0]=="true")

        cfg={
            "days":ABYSS_DAYS,
            "hours":ABYSS_HOURS,
            "reminder_hours":REMINDER_HOURS,
            "round2":ROUND2_ENABLED
        }
        save_json(ABYSS_CONFIG_FILE,cfg)

        await i.response.send_message("✅ Abyss config saved!",ephemeral=True)

@bot.tree.command(name="abyssconfig",description="Configure Abyss times")
async def abyssconfig(inter):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌ Owner only.",ephemeral=True)

    emb=discord.Embed(title="⚙️ Abyss Config",color=0x2ecc71)
    emb.add_field(name="Days",value=str(ABYSS_DAYS),inline=False)
    emb.add_field(name="Hours",value=str(ABYSS_HOURS),inline=False)
    emb.add_field(name="Reminder Hours",value=str(REMINDER_HOURS),inline=False)
    emb.add_field(name="Round 2 Enabled",value=str(ROUND2_ENABLED),inline=False)

    await inter.response.send_message(embed=emb, view=AbyssConfigView(inter), ephemeral=True)
# =========================================
# WEEKLY EVENT
# =========================================
weekly_events=["Melee Wheel","Melee Forge","Range Wheel","Range Forge"]
event_emojis={
    "Range Forge":"🏹",
    "Melee Wheel":"⚔️",
    "Melee Forge":"🔨",
    "Range Wheel":"🎯"
}
start_date=date(2025,9,16)

@bot.tree.command(name="weeklyevent",description="Show next 4 weekly events")
async def weeklyevent(inter):
    today=date.today()
    start_sun=start_date - timedelta(days=start_date.weekday()+1)
    weeks=(today-start_sun).days//7
    now=datetime.utcnow()
    tue=start_sun+timedelta(weeks=weeks,days=2)
    start=datetime.combine(tue,time(0,0))
    end=start+timedelta(days=3)
    if now>=end:
        weeks+=1
        tue=start_sun+timedelta(weeks=weeks,days=2)
        start=datetime.combine(tue,time(0,0))
        end=start+timedelta(days=3)
    msg="📅 **Weekly Abyss Events**\n\n"
    nums=["1️⃣","2️⃣","3️⃣","4️⃣"]
    for i in range(4):
        idx=(weeks+i)%len(weekly_events)
        name=weekly_events[idx]
        emoji=event_emojis.get(name,"📌")
        dt=start_sun+timedelta(weeks=weeks+i,days=2)
        base=datetime.combine(dt,time(0,0))
        if i==0 and start<=now<end:
            left=end-now
            status=f"🟢 LIVE NOW (ends in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m)"
        else:
            left=base-now
            status=f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"
        msg+=f"{nums[i]} {emoji} **{name}** — <t:{int(base.timestamp())}:F>\n{status}\n\n"
    await inter.response.send_message(msg)

# =========================================
# KVK EVENTS
# =========================================
@bot.tree.command(name="kvkevent",description="Show upcoming custom events")
async def kvkevent(inter):
    now=datetime.utcnow()
    evs=load_events()
    def to_dt(e): return datetime.fromisoformat(e["datetime"])
    sorted_e=sorted(evs,key=to_dt)
    upcoming=[]
    for e in sorted_e:
        dt=datetime.fromisoformat(e["datetime"])
        if dt<=now<dt+timedelta(hours=1):
            upcoming.append((e["name"],dt,"live"))
        elif dt>now:
            upcoming.append((e["name"],dt,"up"))
        if len(upcoming)==4: break
    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.",ephemeral=True)
    msg="📅 **Upcoming Events**\n\n"
    nums=["1️⃣","2️⃣","3️⃣","4️⃣"]
    for i,(name,dt,status) in enumerate(upcoming):
        if status=="live":
            left=(dt+timedelta(hours=1))-now
            mins=max(1,left.seconds//60)
            st=f"🟢 LIVE (ends in ~{mins}m)"
        else:
            left=dt-now
            st=f"⏳ Starts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"
        msg+=f"{nums[i]} **{name}** — <t:{int(dt.timestamp())}:F>\n{st}\n\n"
    await inter.response.send_message(msg)

class AddEventModal(discord.ui.Modal,title="➕ Add Event"):
    name=discord.ui.TextInput(label="Event Name")
    dt=discord.ui.TextInput(label="Datetime (UTC)")
    rem=discord.ui.TextInput(label="Reminder (min or 'no')")

    async def on_submit(self,inter):
        try:
            dt=parse_dt(self.dt.value)
            rem=0 if self.rem.value.lower()=="no" else int(self.rem.value)
            e={"name":self.name.value,"datetime":dt.isoformat(),"reminder":rem}
            evs=load_events()
            evs.append(e)
            save_events(evs)
            await inter.response.send_message(
                f"✅ Added **{e['name']}** at <t:{int(dt.timestamp())}:F>",ephemeral=True)
            await log_action(f"📝 Event Added: {e}")
        except Exception as ex:
            await inter.response.send_message(f"❌ Error: {ex}",ephemeral=True)

@bot.tree.command(name="addevent",description="Add custom event")
async def addevent(inter):
    if not is_admin(inter):
        return await inter.response.send_message("❌ No permission.",ephemeral=True)
    await inter.response.send_modal(AddEventModal())

@bot.tree.command(name="editevent",description="Edit event")
async def editevent(inter):
    if not is_admin(inter):
        return await inter.response.send_message("❌ No permission.",ephemeral=True)
    evs=load_events()
    if not evs:
        return await inter.response.send_message("No events.",ephemeral=True)
    class Sel(Select):
        def __init__(self):
            super().__init__(placeholder="Select event",options=[
                discord.SelectOption(label=e["name"],
                description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                value=str(i)) for i,e in enumerate(evs)
            ])
        async def callback(self,i2):
            idx=int(self.values[0])
            active_edits[inter.user.id]={"idx":idx}
            class Menu(View):
                @discord.ui.button(label="Edit Name",style=discord.ButtonStyle.primary)
                async def n(btn,i3):
                    active_edits[inter.user.id]["field"]="name"
                    await i3.response.send_message("Enter new name:",ephemeral=True)
                @discord.ui.button(label="Edit Time",style=discord.ButtonStyle.secondary)
                async def t(btn,i3):
                    active_edits[inter.user.id]["field"]="datetime"
                    await i3.response.send_message("Enter new datetime:",ephemeral=True)
                @discord.ui.button(label="Edit Reminder",style=discord.ButtonStyle.success)
                async def r(btn,i3):
                    active_edits[inter.user.id]["field"]="reminder"
                    await i3.response.send_message("Enter reminder minutes:",ephemeral=True)
            await i2.response.send_message("Choose field:",view=Menu(),ephemeral=True)
    v=View()
    v.add_item(Sel())
    await inter.response.send_message("Select event:",view=v,ephemeral=True)

@bot.tree.command(name="removeevent",description="Delete event")
async def removeevent(inter):
    if not is_admin(inter):
        return await inter.response.send_message("❌ No permission.",ephemeral=True)
    evs=load_events()
    if not evs:
        return await inter.response.send_message("No events.",ephemeral=True)
    class Sel(Select):
        def __init__(self):
            super().__init__(placeholder="Select event",options=[
                discord.SelectOption(label=e["name"],
                description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                value=str(i)) for i,e in enumerate(evs)
            ])
        async def callback(self,i2):
            idx=int(self.values[0])
            class C(View):
                @discord.ui.button(label="YES",style=discord.ButtonStyle.danger)
                async def y(btn,i3):
                    e=load_events()
                    if 0<=idx<len(e):
                        rem=e.pop(idx)
                        save_events(e)
                        await i3.response.send_message(f"🗑 Removed {rem['name']}")
                        await log_action(f"🗑 Removed {rem}")
                    else:
                        await i3.response.send_message("Invalid index.")
                @discord.ui.button(label="NO",style=discord.ButtonStyle.secondary)
                async def n(btn,i3):
                    await i3.response.send_message("Cancelled.",ephemeral=True)
            await i2.response.send_message("Confirm:",view=C(),ephemeral=True)
    v=View()
    v.add_item(Sel())
    await inter.response.send_message("Select:",view=v,ephemeral=True)

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    uid=msg.author.id
    if uid not in active_edits: return
    flow=active_edits[uid]
    idx=flow["idx"]
    field=flow["field"]
    evs=load_events()
    if not (0<=idx<len(evs)):
        del active_edits[uid]
        return
    if field=="name":
        evs[idx]["name"]=msg.content
        save_events(evs)
        await msg.channel.send("✅ Name updated.")
        del active_edits[uid]
        return
    if field=="datetime":
        try:
            evs[idx]["datetime"]=parse_dt(msg.content).isoformat()
        except:
            await msg.channel.send("❌ Invalid datetime.")
            del active_edits[uid];return
        save_events(evs)
        await msg.channel.send("✅ Time updated.")
        del active_edits[uid];return
    if field=="reminder":
        try:
            if msg.content.lower()=="no": r=0
            else:
                r=int(msg.content)
                if r<0: raise ValueError
            evs[idx]["reminder"]=r
        except:
            await msg.channel.send("❌ Reminder must be number.")
            del active_edits[uid];return
        save_events(evs)
        await msg.channel.send("✅ Reminder updated.")
        del active_edits[uid]
        return

# =========================================
# EXPORT / IMPORT
# =========================================
@bot.tree.command(name="exportconfig",description="Export configuration")
async def exportconfig(inter):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌ Owner only.",ephemeral=True)
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(ABYSS_CONFIG_FILE)
        z.write(CUSTOM_FILE)
    mem.seek(0)
    await inter.response.send_message("📦 Exported.",file=discord.File(mem,"config.zip"),ephemeral=True)

def strict_ev(d):
    if not isinstance(d,list): return False
    for e in d:
        if not isinstance(e,dict): return False
        if "name" not in e or "datetime" not in e or "reminder" not in e:
            return False
    return True

def strict_ab(d):
    return all(k in d for k in ["days","hours","reminder_hours","round2"])

def soft_ab(d):
    o={}
    if "days" in d: o["days"]=[int(x) for x in d["days"]]
    if "hours" in d: o["hours"]=[int(x) for x in d["hours"]]
    if "reminder_hours" in d: o["reminder_hours"]=[int(x) for x in d["reminder_hours"]]
    if "round2" in d: o["round2"]=bool(d["round2"])
    return o

@bot.tree.command(name="importconfig",description="Import config.zip")
async def importconfig(inter,file:discord.Attachment):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌ Owner only.",ephemeral=True)
    if not file.filename.endswith(".zip"):
        return await inter.response.send_message("❌ Upload ZIP.",ephemeral=True)
    raw=await file.read()
    try:
        z=zipfile.ZipFile(io.BytesIO(raw))
    except:
        return await inter.response.send_message("❌ Invalid ZIP.",ephemeral=True)

    evd=None; abd=None
    for n in z.namelist():
        if n==CUSTOM_FILE:
            try: evd=json.loads(z.read(n))
            except: pass
        if n==ABYSS_CONFIG_FILE:
            try: abd=json.loads(z.read(n))
            except: pass

    if evd and abd:
        if strict_ev(evd) and strict_ab(abd):
            save_events(evd)
            save_json(ABYSS_CONFIG_FILE,abd)
            global cfg,ABYSS_DAYS,ABYSS_HOURS,REMINDER_HOURS,ROUND2_ENABLED
            cfg=abd
            ABYSS_DAYS=cfg["days"]
            ABYSS_HOURS=cfg["hours"]
            REMINDER_HOURS=cfg["reminder_hours"]
            ROUND2_ENABLED=cfg["round2"]
            return await inter.response.send_message("✅ Strict import complete.",ephemeral=True)

    imported=[]
    if evd:
        save_events(evd); imported.append("Events")
    if abd:
        soft=soft_ab(abd)
        cfg.update(soft)
        save_json(ABYSS_CONFIG_FILE,cfg)
        ABYSS_DAYS=cfg["days"]
        ABYSS_HOURS=cfg["hours"]
        REMINDER_HOURS=cfg["reminder_hours"]
        ROUND2_ENABLED=cfg["round2"]
        imported.append("Abyss Config")

    if not imported:
        return await inter.response.send_message("⚠ Nothing valid.",ephemeral=True)

    await inter.response.send_message("⚠ Soft import:\n• "+"\n• ".join(imported),ephemeral=True)

# =========================================
# ABYSS REMINDER SYSTEM
# =========================================
@tasks.loop(minutes=1)
async def abyss_loop():
    tz=pytz.timezone(MY_TIMEZONE)
    now=datetime.now(tz)
    if now.weekday() not in ABYSS_DAYS: return
    ch=bot.get_channel(CHANNEL_ID)
    if not ch: return

    if now.minute==0 and now.hour in REMINDER_HOURS:
        await ch.send(f"<@&1413532222396301322>, Abyss will start in 15 minutes!")

    if ROUND2_ENABLED and now.minute==30 and now.hour in REMINDER_HOURS:
        await ch.send(f"<@&1413532222396301322>, Round 2 of Abyss will start in 15 minutes!")

# =========================================
# CUSTOM EVENT REMINDERS
# =========================================
@tasks.loop(minutes=1)
async def custom_loop():
    global sent_custom
    now=datetime.utcnow().replace(second=0,microsecond=0)
    ch=bot.get_channel(CHANNEL_ID)
    if not ch: return
    evs=load_events()
    for e in evs:
        dt=datetime.fromisoformat(e["datetime"])
        r=e["reminder"]
        if r<=0: continue
        t=dt-timedelta(minutes=r)
        key=(e["name"],t.isoformat())
        if t<=now<t+timedelta(minutes=1):
            if key not in sent_custom:
                await ch.send(f"⏰ Reminder: **{e['name']}** starts in {r} minutes! <t:{int(dt.timestamp())}:F>")
                sent_custom.add(key)
    if len(sent_custom)>300:
        sent_custom=set(list(sent_custom)[-100:])

# =========================================
# RUN BOT
# =========================================
TOKEN=os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ Missing token")
else:
    bot.run(TOKEN)
