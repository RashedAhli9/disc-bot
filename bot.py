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

DB = os.path.join(os.path.dirname(__file__), "events.db")

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

@bot.tree.command(name="weeklyevent", description="Shows list of weekly events (Forge/Wheel)")
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



@bot.tree.command(name="addrole", description="Receive the Abyss notification role.")
async def addrole(inter):
    role_id = 1413532222396301322
    role = inter.guild.get_role(role_id)

    if role is None:
        return await inter.response.send_message("❌ Role not found in this server.", ephemeral=True)

    # If user already has the role
    if role in inter.user.roles:
        return await inter.response.send_message("You already have this role!", ephemeral=True)

    try:
        await inter.user.add_roles(role)
        await inter.response.send_message(f"✅ Role **{role.name}** added successfully!", ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message("❌ I don't have permission to give that role.", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="removerole", description="Remove the Abyss notification role from yourself.")
async def removerole(inter):
    role_id = 1413532222396301322
    role = inter.guild.get_role(role_id)

    if role is None:
        return await inter.response.send_message("❌ Role not found in this server.", ephemeral=True)

    # If user doesn't have the role
    if role not in inter.user.roles:
        return await inter.response.send_message("You don't have this role.", ephemeral=True)

    try:
        await inter.user.remove_roles(role)
        await inter.response.send_message(f"✅ Role **{role.name}** removed successfully!", ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message("❌ I don't have permission to remove that role.", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"❌ Error: {e}", ephemeral=True)

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

@bot.tree.command(name="abyssconfig", description="Edit Rules for abyss")
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

@bot.tree.command(name="kvkevent", description="Display Kvk Events Like (Pass...etc)")
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
# ADD EVENT (Restored Modal UI + 14UTC Support)
# ============================================================

# --- Improved datetime parser ---
def parse_datetime(input_str: str):
    """Parse datetime in formats:
    - DD-MM-YYYY HH:MM
    - 1d 2h 30m (relative)
    - 14utc (today 14:00 UTC, or tomorrow if passed)
    """

    raw = input_str.strip().lower().replace(" ", "")

    # ------------------------------------------------------------
    # NEW FEATURE: "14utc" → today at 14:00 UTC OR tomorrow
    # ------------------------------------------------------------
    if raw.endswith("utc") and raw[:-3].isdigit():
        hour = int(raw[:-3])

        now = datetime.utcnow()
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)

        # If the time already passed today → schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)

        return target

    # ------------------------------------------------------------
    # Absolute date format: DD-MM-YYYY HH:MM
    # ------------------------------------------------------------
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except:
        pass

    # ------------------------------------------------------------
    # Relative format: "1d 2h 30m"
    # ------------------------------------------------------------
    now = datetime.utcnow()
    d = h = m = 0

    for part in input_str.split():
        part = part.lower()
        if part.endswith("d"):
            d = int(part[:-1])
        elif part.endswith("h"):
            h = int(part[:-1])
        elif part.endswith("m"):
            m = int(part[:-1])

    return now + timedelta(days=d, hours=h, minutes=m)


# ============================================================
# MODAL UI FOR ADDING EVENTS
# ============================================================

from discord.ui import Modal, TextInput

class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name")

    dt_input = TextInput(
        label="Datetime (UTC)",
        placeholder="DD-MM-YYYY HH:MM | 1d2h | 14utc"
    )

    reminder = TextInput(
        label="Reminder (minutes or 'no')",
        placeholder="10"
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse datetime using upgraded function
            dt = parse_datetime(self.dt_input.value)

            # Parse reminder
            rem = 0 if self.reminder.value.lower() == "no" else int(self.reminder.value)

            # Store using ISO with "T" for best compatibility
            iso_dt = dt.isoformat(sep="T", timespec="seconds")

            db_add_event(self.name.value, iso_dt, rem)

            await interaction.response.send_message(
                f"✅ **Event Added:** {self.name.value}\n"
                f"🕒 Time: <t:{int(dt.timestamp())}:F>\n"
                f"🔔 Reminder: {rem} min",
                ephemeral=True
            )

            await log_action(f"Added event: {self.name.value} at {iso_dt}")

        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# ============================================================
# /addevent COMMAND (UNCHANGED UI, JUST FIXED)
# ============================================================

@bot.tree.command(name="addevent", description="Add a custom scheduled event.")
async def addevent(interaction: discord.Interaction):
    if not has_admin(interaction):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    await interaction.response.send_modal(AddEventModal())


# EDIT EVENT
@bot.tree.command(name="editevent", description="Edit a custom scheduled event.")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    rows = db_get_events()
    if not rows:
        return await inter.response.send_message("📭 No events to edit.", ephemeral=True)

    # Build dropdown
    options = []
    for event_id, name, dt, rem in rows:
        try:
            dt_fmt = datetime.fromisoformat(dt).strftime("%d-%m %H:%M")
        except:
            dt_fmt = "Invalid date"

        options.append(
            discord.SelectOption(
                label=f"{event_id}: {name}",
                description=f"{dt_fmt} | Reminder: {rem}m",
                value=str(event_id)
            )
        )

    class EventSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="Choose an event to edit…",
                min_values=1,
                max_values=1,
                options=options
            )

        async def callback(self, interaction: discord.Interaction):
            eid = int(self.values[0])

            class EditMenu(discord.ui.View):
                def __init__(self, event_id):
                    super().__init__(timeout=120)
                    self.event_id = event_id

                # -------- EDIT NAME ----------
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self, interaction2: discord.Interaction, button):
                    class NameModal(discord.ui.Modal, title="Edit Event Name"):
                        new_name = discord.ui.TextInput(label="New Event Name")

                        async def on_submit(self, inter3: discord.Interaction):
                            db_update_event(eid, name=str(self.new_name))
                            await inter3.response.send_message("✔ Name updated.", ephemeral=True)
                            await log_action(f"Edited event {eid}: name changed")

                    await interaction2.response.send_modal(NameModal())

                # -------- EDIT DATE ----------
                @discord.ui.button(label="Edit Datetime", style=discord.ButtonStyle.secondary)
                async def edit_time(self, interaction2: discord.Interaction, button):
                    class TimeModal(discord.ui.Modal, title="Edit Datetime"):
                        new_dt = discord.ui.TextInput(
                            label="New Datetime",
                            placeholder="DD-MM-YYYY HH:MM or 1d2h or 14utc"
                        )

                        async def on_submit(self, inter3: discord.Interaction):
                            try:
                                new_time = parse_datetime(self.new_dt.value)
                                db_update_event(eid, dt=new_time.isoformat())
                                await inter3.response.send_message("✔ Time updated.", ephemeral=True)
                                await log_action(f"Edited event {eid}: time changed")
                            except:
                                await inter3.response.send_message("❌ Invalid datetime.", ephemeral=True)

                    await interaction2.response.send_modal(TimeModal())

                # -------- EDIT REMINDER ----------
                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_reminder(self, interaction2: discord.Interaction, button):
                    class ReminderModal(discord.ui.Modal, title="Edit Reminder"):
                        new_rem = discord.ui.TextInput(
                            label="New Reminder",
                            placeholder="Minutes or 'no'"
                        )

                        async def on_submit(self, inter3: discord.Interaction):
                            try:
                                if self.new_rem.value.lower() == "no":
                                    db_update_event(eid, reminder=0)
                                else:
                                    db_update_event(eid, reminder=int(self.new_rem.value))

                                await inter3.response.send_message("✔ Reminder updated.", ephemeral=True)
                                await log_action(f"Edited event {eid}: reminder changed")
                            except:
                                await inter3.response.send_message("❌ Invalid reminder.", ephemeral=True)

                    await interaction2.response.send_modal(ReminderModal())

            await interaction.response.send_message(
                f"Editing event **{eid}**",
                view=EditMenu(eid),
                ephemeral=True
            )

    class EditView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.add_item(EventSelect())

    await inter.response.send_message(
        "Select an event to edit:",
        view=EditView(),
        ephemeral=True
    )


# REMOVE EVENT
@bot.tree.command(name="removeevent", description="Remove a custom scheduled event.")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    rows = db_get_events()
    if not rows:
        return await inter.response.send_message("📭 No events to remove.", ephemeral=True)

    # Build dropdown options
    options = []
    for event_id, name, dt, rem in rows:
        try:
            dt_fmt = datetime.fromisoformat(dt).strftime("%d-%m %H:%M")
        except:
            dt_fmt = "Invalid date"
        options.append(
            discord.SelectOption(
                label=f"{event_id}: {name}",
                description=dt_fmt,
                value=str(event_id)
            )
        )

    class RemoveSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="Choose an event to delete…",
                min_values=1,
                max_values=1,
                options=options
            )

        async def callback(self, interaction: discord.Interaction):
            eid = int(self.values[0])

            class ConfirmDelete(discord.ui.View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(self, interaction2: discord.Interaction, button):
                    db_delete_event(eid)
                    await interaction2.response.edit_message(
                        content=f"🗑️ Event **{eid}** deleted.",
                        view=None
                    )
                    await log_action(f"Deleted event ID: {eid}")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(self, interaction2: discord.Interaction, button):
                    await interaction2.response.edit_message(
                        content="❌ Cancelled.",
                        view=None
                    )

            await interaction.response.edit_message(
                content=f"Confirm delete **event {eid}**?",
                view=ConfirmDelete()
            )

    class RemoveView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.add_item(RemoveSelect())

    await inter.response.send_message(
        "Select an event:",
        view=RemoveView(),
        ephemeral=True
    )

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








