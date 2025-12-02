# ============================================================
# Abyss Reminder Bot (FINAL + SQLITE EVENT DATABASE)
# ============================================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import sqlite3
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
ROLE_ID = 1413532222396301322

ABYSS_CONFIG_FILE = "abyss_config.json"

# ============================================================
# SQLITE DATABASE INIT
# ============================================================

DB = "events.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            datetime TEXT NOT NULL,
            reminder INTEGER NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def db_add_event(name, dt, reminder):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO events (name, datetime, reminder) VALUES (?, ?, ?)",
              (name, dt, reminder))
    conn.commit()
    conn.close()

def db_get_events():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, name, datetime, reminder FROM events ORDER BY datetime ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def db_update_event(event_id, name=None, dt=None, reminder=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    if name is not None:
        c.execute("UPDATE events SET name=? WHERE id=?", (name, event_id))
    if dt is not None:
        c.execute("UPDATE events SET datetime=? WHERE id=?", (dt, event_id))
    if reminder is not None:
        c.execute("UPDATE events SET reminder=? WHERE id=?", (reminder, event_id))

    conn.commit()
    conn.close()

def db_delete_event(event_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()

init_db()

# ============================================================
# DEFAULT ABYSS CONFIG
# ============================================================

DEFAULT_ABYSS = {
    "days": [1, 4, 6],
    "hours": [0, 4, 8, 12, 16, 20],
    "reminder_hours": [0, 4, 8, 12, 16, 20],
    "round2": True
}

# ============================================================
# FILE UTILITIES
# ============================================================

def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=2)

def load_json(path, default):
    ensure_file(path, default)
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ============================================================
# LOAD ABYSS CONFIG
# ============================================================

cfg = load_json(ABYSS_CONFIG_FILE, DEFAULT_ABYSS)
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
bot = commands.Bot(command_prefix="!", intents=intents)
bot.active_edit = None  # (user_id, event_id, field)

# ============================================================
# HELPERS
# ============================================================

def parse_datetime(input_str):
    """Absolute or relative format."""
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except:
        pass
    now = datetime.utcnow()
    d = h = m = 0
    for part in input_str.split():
        if part.endswith("d"): d = int(part[:-1])
        if part.endswith("h"): h = int(part[:-1])
        if part.endswith("m"): m = int(part[:-1])
    return now + timedelta(days=d, hours=h, minutes=m)

def has_admin(inter):
    if inter.user.id == OWNER_ID:
        return True
    return any(r.permissions.administrator for r in inter.user.roles)

async def log_action(msg):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(msg)

def day_name(i):
    return ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][i]

def pretty_days(lst): return ", ".join(day_name(x) for x in lst)
def pretty_hours(lst): return ", ".join(f"{x:02}:00" for x in lst)

# ============================================================
# ON_READY
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print("Synced", len(synced))
    except Exception as e:
        print("Sync failed:", e)

    abyss_reminder_loop.start()
    custom_event_loop.start()

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Bot restarted successfully.")

# ============================================================
# WEEKLY EVENTS (unchanged)
# ============================================================

weekly_events = ["Melee Wheel","Melee Forge","Range Wheel","Range Forge"]
event_emojis = {"Range Forge":"🏹","Melee Wheel":"⚔️","Melee Forge":"🔨","Range Wheel":"🎯"}

start_date = date(2025, 9, 16)

@bot.tree.command(name="weeklyevent")
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
            left = event_end-now
            st=f"🟢 LIVE NOW ({left.seconds//3600}h {(left.seconds//60)%60}m left)"
        else:
            left = base_dt-now
            st=f"⏳ {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m"

        msg+=f"{nums[i]} {emoji} **{nm}** — <t:{int(base_dt.timestamp())}:F>\n{st}\n\n"

    await inter.response.send_message(msg)

# ============================================================
# ABYSS CONFIG VIEW (unchanged)
# ============================================================

class AbyssConfigView(View):
    def __init__(self, d, h, r, rd2):
        super().__init__(timeout=300)
        self.days=d
        self.hours=h
        self.rem=r
        self.round2=rd2

        self.day_sel = Select(
            placeholder="Select Abyss Days",
            min_values=1, max_values=7,
            options=[discord.SelectOption(label=day_name(i), value=str(i), default=(i in d)) for i in range(7)]
        )
        self.day_sel.callback = self.cb_days
        self.add_item(self.day_sel)

        self.hour_sel = Select(
            placeholder="Select Abyss Hours",
            min_values=1, max_values=24,
            options=[discord.SelectOption(label=f"{i:02}:00", value=str(i), default=(i in h)) for i in range(24)]
        )
        self.hour_sel.callback = self.cb_hours
        self.add_item(self.hour_sel)

        self.rem_sel = Select(
            placeholder="Reminder Hours",
            min_values=0, max_values=len(h),
            options=[discord.SelectOption(label=f"{i:02}:00", value=str(i), default=(i in r)) for i in h]
        )
        self.rem_sel.callback = self.cb_rem
        self.add_item(self.rem_sel)

        self.round_sel = Select(
            placeholder="Round 2?",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Enabled", value="1", default=rd2),
                discord.SelectOption(label="Disabled", value="0", default=not rd2)
            ]
        )
        self.round_sel.callback = self.cb_round2
        self.add_item(self.round_sel)

        btn = Button(label="Save", style=discord.ButtonStyle.green)
        btn.callback = self.save
        self.add_item(btn)

    async def cb_days(self, inter):
        self.days=[int(x) for x in self.day_sel.values]
        await self.refresh(inter)

    async def cb_hours(self, inter):
        self.hours=[int(x) for x in self.hour_sel.values]
        self.rem=[x for x in self.rem if x in self.hours]
        await self.refresh(inter)

    async def cb_rem(self, inter):
        self.rem=[int(x) for x in self.rem_sel.values]
        await self.refresh(inter)

    async def cb_round2(self, inter):
        self.round2=(self.round_sel.values[0]=="1")
        await self.refresh(inter)

    async def refresh(self, inter):
        new=AbyssConfigView(self.days,self.hours,self.rem,self.round2)
        emb=discord.Embed(title="⚙️ Abyss Config",color=0x2ecc71)
        emb.add_field(name="Days",value=pretty_days(self.days))
        emb.add_field(name="Hours",value=pretty_hours(self.hours))
        emb.add_field(name="Reminder Hours",value=pretty_hours(self.rem))
        emb.add_field(name="Round 2",value="Enabled" if self.round2 else "Disabled")

        await inter.response.edit_message(embed=emb,view=new)

    async def save(self, inter):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg

        ABYSS_DAYS=self.days
        ABYSS_HOURS=self.hours
        REMINDER_HOURS=self.rem
        ROUND2_ENABLED=self.round2

        cfg={
            "days":ABYSS_DAYS,
            "hours":ABYSS_HOURS,
            "reminder_hours":REMINDER_HOURS,
            "round2":ROUND2_ENABLED
        }
        save_json(ABYSS_CONFIG_FILE, cfg)

        await inter.response.send_message("Saved!", ephemeral=True)

@bot.tree.command(name="abyssconfig")
async def abyssconfig(inter):
    if inter.user.id!=OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    emb=discord.Embed(title="⚙️ Abyss Config",color=0x2ecc71)
    emb.add_field(name="Days",value=pretty_days(ABYSS_DAYS))
    emb.add_field(name="Hours",value=pretty_hours(ABYSS_HOURS))
    emb.add_field(name="Reminder Hours",value=pretty_hours(REMINDER_HOURS))
    emb.add_field(name="Round 2",value="Enabled" if ROUND2_ENABLED else "Disabled")

    view=AbyssConfigView(ABYSS_DAYS,ABYSS_HOURS,REMINDER_HOURS,ROUND2_ENABLED)
    await inter.response.send_message(embed=emb,view=view,ephemeral=True)

# ============================================================
# CUSTOM EVENTS (SQLITE VERSION)
# ============================================================

@bot.tree.command(name="kvkevent")
async def kvkevent(inter):
    now=datetime.utcnow()
    events=db_get_events()

    upcoming=[ev for ev in events if datetime.fromisoformat(ev[2]) > now]

    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    upcoming=upcoming[:4]

    msg="📅 **Upcoming Events**\n\n"
    nums=["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i,ev in enumerate(upcoming):
        event_id, name, dt, rem = ev
        dt_obj=datetime.fromisoformat(dt)
        left=dt_obj-now
        msg+=f"{nums[i]} **{name}** — <t:{int(dt_obj.timestamp())}:F>\nStarts in {left.days}d {left.seconds//3600}h {(left.seconds//60)%60}m\n\n"

    await inter.response.send_message(msg, ephemeral=True)

# ============================================================
# NEW /addevent — PREMIUM UI VERSION (LATEST DISCORD.PY)
# ============================================================

from discord.ui import View, Button, Modal, TextInput

# Temporary event holder
class EventDraft:
    def __init__(self):
        self.name = None
        self.datetime = None
        self.reminder = 10  # default reminder


# ============================================================
# MODALS
# ============================================================

class NameModal(Modal, title="Edit Event Name"):
    new_name = TextInput(label="Event Name")

    def __init__(self, draft: EventDraft):
        super().__init__()
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction):
        self.draft.name = self.new_name.value
        await interaction.response.send_message("✔ Name updated.", ephemeral=True)


class CustomDTModal(Modal, title="Custom Datetime Input"):
    dt_field = TextInput(label="Datetime", placeholder="14utc | 1d2h | 23-12-2025 14:00")

    def __init__(self, draft: EventDraft):
        super().__init__()
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction):
        try:
            parsed = parse_datetime(self.dt_field.value)
            self.draft.datetime = parsed
            await interaction.response.send_message("✔ Datetime updated.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Invalid datetime.", ephemeral=True)


class CustomReminderModal(Modal, title="Custom Reminder"):
    mins = TextInput(label="Minutes", placeholder="10")

    def __init__(self, draft: EventDraft):
        super().__init__()
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.draft.reminder = int(self.mins.value)
            await interaction.response.send_message("✔ Reminder updated.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Invalid number.", ephemeral=True)


# ============================================================
# DATETIME SUGGESTION VIEW
# ============================================================

class DatetimeSuggestView(View):
    def __init__(self, draft: EventDraft):
        super().__init__(timeout=90)
        self.draft = draft
        self.build_buttons()

    def build_buttons(self):
        now = datetime.utcnow()

        # TODAY suggestions
        today_14 = now.replace(hour=14, minute=0, second=0, microsecond=0)
        today_18 = now.replace(hour=18, minute=0, second=0, microsecond=0)

        # If time passed, move to tomorrow
        if today_14 <= now:
            today_14 += timedelta(days=1)
        if today_18 <= now:
            today_18 += timedelta(days=1)

        # Tomorrow suggestions
        tmrw = now + timedelta(days=1)
        tmrw_14 = tmrw.replace(hour=14, minute=0, second=0, microsecond=0)
        tmrw_18 = tmrw.replace(hour=18, minute=0, second=0, microsecond=0)

        # Relative (1h)
        in1h = now + timedelta(hours=1)
        in1h = in1h.replace(second=0, microsecond=0)

        # Add buttons
        def make_button(label, dt):
            self.add_item(Button(
                label=label,
                style=discord.ButtonStyle.primary,
                custom_id=f"dt|{dt.isoformat()}"
            ))

        make_button(f"Today {today_14.strftime('%H:%M')} UTC", today_14)
        make_button(f"Today {today_18.strftime('%H:%M')} UTC", today_18)
        make_button(f"Tomorrow {tmrw_14.strftime('%H:%M')} UTC", tmrw_14)
        make_button(f"Tomorrow {tmrw_18.strftime('%H:%M')} UTC", tmrw_18)
        make_button(f"In 1 hour (UTC {in1h.strftime('%H:%M')})", in1h)

        # Custom
        self.add_item(Button(
            label="Custom Input",
            style=discord.ButtonStyle.danger,
            custom_id="custom_dt"
        ))

    async def interaction_check(self, interaction: discord.Interaction):
        cid = interaction.data["custom_id"]

        # Custom input modal
        if cid == "custom_dt":
            await interaction.response.send_modal(CustomDTModal(self.draft))
            return True

        # Suggested datetime button
        if cid.startswith("dt|"):
            iso = cid.split("|", 1)[1]
            self.draft.datetime = datetime.fromisoformat(iso)
            await interaction.response.send_message("✔ Datetime selected.", ephemeral=True)
            return True

        return True


# ============================================================
# REMINDER VIEW
# ============================================================

class ReminderView(View):
    def __init__(self, draft: EventDraft):
        super().__init__(timeout=90)
        self.draft = draft

        self.add_item(Button(label="5 min", style=discord.ButtonStyle.primary, custom_id="r|5"))
        self.add_item(Button(label="10 min", style=discord.ButtonStyle.primary, custom_id="r|10"))
        self.add_item(Button(label="15 min", style=discord.ButtonStyle.primary, custom_id="r|15"))
        self.add_item(Button(label="No Reminder", style=discord.ButtonStyle.secondary, custom_id="r|0"))
        self.add_item(Button(label="Custom", style=discord.ButtonStyle.danger, custom_id="r_custom"))

    async def interaction_check(self, interaction: discord.Interaction):
        cid = interaction.data["custom_id"]

        if cid == "r_custom":
            await interaction.response.send_modal(CustomReminderModal(self.draft))
            return True

        if cid.startswith("r|"):
            mins = int(cid.split("|")[1])
            self.draft.reminder = mins
            await interaction.response.send_message("✔ Reminder updated.", ephemeral=True)
            return True

        return True


# ============================================================
# MAIN ADD EVENT UI
# ============================================================

class AddEventView(View):
    def __init__(self, draft: EventDraft):
        super().__init__(timeout=300)
        self.draft = draft

    def embed(self):
        e = discord.Embed(title="📅 Add Custom Event", color=0x2ecc71)

        e.add_field(name="Name", value=self.draft.name or "(not set)", inline=False)
        e.add_field(
            name="Datetime",
            value=self.draft.datetime.isoformat() if self.draft.datetime else "(not set)",
            inline=False
        )
        e.add_field(name="Reminder", value=f"{self.draft.reminder} minutes", inline=False)

        return e

    @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
    async def edit_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NameModal(self.draft))

    @discord.ui.button(label="Edit Datetime", style=discord.ButtonStyle.secondary)
    async def edit_dt(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choose datetime:",
            view=DatetimeSuggestView(self.draft),
            ephemeral=True
        )

    @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
    async def edit_rem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choose reminder:",
            view=ReminderView(self.draft),
            ephemeral=True
        )

    @discord.ui.button(label="Create Event", style=discord.ButtonStyle.green)
    async def create_ev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.draft.name or not self.draft.datetime:
            return await interaction.response.send_message("❌ Name and datetime required.", ephemeral=True)

        dt = self.draft.datetime.isoformat(sep="T", timespec="seconds")
        db_add_event(self.draft.name, dt, self.draft.reminder)

        await interaction.response.send_message(
            f"✅ Event created: **{self.draft.name}**",
            ephemeral=True
        )

        await log_action(f"Added event: {self.draft.name}")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cancelled.", ephemeral=True)


# ============================================================
# /addevent COMMAND
# ============================================================

@bot.tree.command(name="addevent")
async def addevent(interaction: discord.Interaction):
    if not has_admin(interaction):
        return await interaction.response.send_message("No permission.", ephemeral=True)

    draft = EventDraft()
    view = AddEventView(draft)

    await interaction.response.send_message(
        embed=view.embed(),
        view=view,
        ephemeral=True
    )


# EDIT EVENT
@bot.tree.command(name="editevent")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("No permission.", ephemeral=True)

    rows=db_get_events()
    if not rows:
        return await inter.response.send_message("No events available.", ephemeral=True)

    class Pick(Select):
        def __init__(self):
            opts=[]
            for row in rows:
                event_id,name,dt,rem=row
                opts.append(
                    discord.SelectOption(
                        label=f"{event_id}: {name}",
                        description=datetime.fromisoformat(dt).strftime("%d-%m %H:%M"),
                        value=str(event_id)
                    )
                )
            super().__init__(options=opts,placeholder="Select event")

        async def callback(self,inter2):
            eid=int(self.values[0])

            class Editor(View):
                @discord.ui.button(label="Edit Name",style=discord.ButtonStyle.primary)
                async def a(btn,ix):
                    await ix.response.send_message("Enter new name:",ephemeral=True)
                    bot.active_edit=(ix.user.id,eid,"name")

                @discord.ui.button(label="Edit Time",style=discord.ButtonStyle.secondary)
                async def b(btn,ix):
                    await ix.response.send_message("Enter new datetime:",ephemeral=True)
                    bot.active_edit=(ix.user.id,eid,"time")

                @discord.ui.button(label="Edit Reminder",style=discord.ButtonStyle.success)
                async def c(btn,ix):
                    await ix.response.send_message("Enter reminder (minutes or 'no'):",ephemeral=True)
                    bot.active_edit=(ix.user.id,eid,"rem")
            await inter2.response.send_message("Choose field:",view=Editor(),ephemeral=True)

    view=View()
    view.add_item(Pick())
    await inter.response.send_message("Select event:",view=view,ephemeral=True)

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    if bot.active_edit is None: return

    uid,eid,field=bot.active_edit
    if msg.author.id!=uid:
        return

    events=db_get_events()
    if not any(ev[0]==eid for ev in events):
        bot.active_edit=None
        return

    if field=="name":
        db_update_event(eid,name=msg.content)
        await msg.channel.send("Updated ✔")
        bot.active_edit=None
        return

    if field=="time":
        try:
            dt=parse_datetime(msg.content).isoformat()
            db_update_event(eid,dt=dt)
            await msg.channel.send("Updated ✔")
        except:
            await msg.channel.send("Invalid datetime.")
        bot.active_edit=None
        return

    if field=="rem":
        try:
            if msg.content.lower()=="no":
                db_update_event(eid,reminder=0)
            else:
                r=int(msg.content)
                db_update_event(eid,reminder=r)
            await msg.channel.send("Updated ✔")
        except:
            await msg.channel.send("Invalid reminder.")
        bot.active_edit=None
        return

# REMOVE EVENT
@bot.tree.command(name="removeevent")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("No permission.", ephemeral=True)

    rows=db_get_events()
    if not rows:
        return await inter.response.send_message("No events to remove.", ephemeral=True)

    class PickR(Select):
        def __init__(self):
            opts=[]
            for row in rows:
                event_id,name,dt,rem=row
                opts.append(
                    discord.SelectOption(
                        label=f"{event_id}: {name}",
                        description=datetime.fromisoformat(dt).strftime("%d-%m %H:%M"),
                        value=str(event_id)
                    )
                )
            super().__init__(options=opts,placeholder="Choose event")

        async def callback(self,inter2):
            eid=int(self.values[0])

            class Conf(View):
                @discord.ui.button(label="YES",style=discord.ButtonStyle.danger)
                async def y(btn,ix):
                    db_delete_event(eid)
                    await ix.response.send_message("Deleted ✔")
                    await log_action(f"Deleted: {eid}")

                @discord.ui.button(label="NO",style=discord.ButtonStyle.secondary)
                async def n(btn,ix):
                    await ix.response.send_message("Cancelled.",ephemeral=True)

            await inter2.response.send_message("Confirm?",view=Conf(),ephemeral=True)

    v=View()
    v.add_item(PickR())
    await inter.response.send_message("Select event:",view=v,ephemeral=True)

# ============================================================
# REMINDER LOOPS
# ============================================================

@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    tz=pytz.timezone(MY_TIMEZONE)
    now=datetime.now(tz)

    if now.weekday() not in ABYSS_DAYS:
        return

    ch=bot.get_channel(channel_id)
    if not ch: return

    if now.hour in REMINDER_HOURS and now.minute==0:
        await ch.send(f"<@&{ROLE_ID}>, Abyss starts in 15 minutes!")

    if ROUND2_ENABLED and now.hour in REMINDER_HOURS and now.minute==30:
        await ch.send(f"<@&{ROLE_ID}>, Round 2 in 15 minutes!")

sent_custom=set()

@tasks.loop(minutes=1)
async def custom_event_loop():
    now=datetime.utcnow().replace(second=0,microsecond=0)
    ch=bot.get_channel(channel_id)
    if not ch: return

    rows=db_get_events()
    for ev in rows:
        event_id,name,dt,rem=ev
        dt_obj=datetime.fromisoformat(dt)

        # DELETE event after it ends (1 hour after start)
        if now >= dt_obj + timedelta(hours=1):
            db_delete_event(event_id)
            continue

        # Reminder system
        if rem>0:
            rtime=dt_obj - timedelta(minutes=rem)
            key=(event_id, rtime.isoformat())
            if rtime <= now < rtime + timedelta(minutes=1):
                if key not in sent_custom:
                    await ch.send(
                        f"⏰ Reminder: **{name}** in {rem} minutes! <t:{int(dt_obj.timestamp())}:F>"
                    )
                    sent_custom.add(key)

    if len(sent_custom)>300:
        sent_custom.clear()

# ============================================================
# RUN BOT
# ============================================================

TOKEN=os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ Missing DISCORD_BOT_TOKEN")
else:
    bot.run(TOKEN)




