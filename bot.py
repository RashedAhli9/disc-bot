# ================================================
# PART 1 OF 3 — Abyss Reminder Bot (Final Build)
# ================================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import os
import json
import zipfile
import io
from datetime import datetime, timedelta, date, time
from discord.ui import View, Button, Select, Modal, TextInput

# ================================================
# CONFIGURATION
# ================================================
MY_TIMEZONE = "UTC"

channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490
GUILD_ID = 1328405638744641548
ROLE_ID = 1413532222396301322

CUSTOM_FILE = "custom_events.json"
ABYSS_CONFIG_FILE = "abyss_config.json"

DEFAULT_ABYSS_DAYS = [1, 4, 6]     # Tue, Fri, Sun
DEFAULT_ABYSS_HOURS = [8, 12, 16, 20]
DEFAULT_REMINDER_HOURS = []

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================================================
# LOAD / SAVE HELPERS
# ================================================
def load_custom_events():
    if not os.path.exists(CUSTOM_FILE):
        return []
    try:
        return json.load(open(CUSTOM_FILE))
    except:
        return []

def save_custom_events(events):
    json.dump(events, open(CUSTOM_FILE, "w"), indent=2)

def load_abyss_config():
    if not os.path.exists(ABYSS_CONFIG_FILE):
        return {
            "days": DEFAULT_ABYSS_DAYS,
            "hours": DEFAULT_ABYSS_HOURS,
            "reminder_hours": DEFAULT_REMINDER_HOURS,
            "round2": True,
        }
    try:
        return json.load(open(ABYSS_CONFIG_FILE))
    except:
        return {
            "days": DEFAULT_ABYSS_DAYS,
            "hours": DEFAULT_ABYSS_HOURS,
            "reminder_hours": DEFAULT_REMINDER_HOURS,
            "round2": True,
        }

def save_abyss_config(cfg):
    json.dump(cfg, open(ABYSS_CONFIG_FILE, "w"), indent=2)


cfg = load_abyss_config()
ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg.get("reminder_hours", [])
ROUND2_ENABLED = cfg.get("round2", True)

# ================================================
# UTILITY HELPERS
# ================================================
def parse_datetime(text):
    try:
        return datetime.strptime(text, "%d-%m-%Y %H:%M")
    except:
        pass

    now = datetime.utcnow()
    d = h = m = 0
    for part in text.split():
        if "d" in part:
            d = int(part.replace("d", ""))
        elif "h" in part:
            h = int(part.replace("h", ""))
        elif "m" in part:
            m = int(part.replace("m", ""))
    return now + timedelta(days=d, hours=h, minutes=m)

async def log_action(msg):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(msg)

def has_admin(inter):
    return inter.user.id == OWNER_ID or any(r.name.lower() == "admin" for r in inter.user.roles)


# ================================================
# ON READY — SYNC COMMANDS
# ================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print("Synced:", len(synced))
    except Exception as e:
        print("Sync error:", e)

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Abyss Reminder bot updated & live!")

    abyss_loop.start()
# ================================================
# PART 2 OF 3 — AbyssConfig UI + Reminder System
# ================================================

# ------------------------------------------------
# ABYSS CONFIG VIEW
# ------------------------------------------------
class AbyssConfigView(View):
    def __init__(self, inter):
        super().__init__(timeout=300)
        self.inter = inter

        self.selected_days = set(ABYSS_DAYS)
        self.selected_hours = set(ABYSS_HOURS)
        self.selected_reminder_hours = set(REMINDER_HOURS)
        self.round2_enabled = ROUND2_ENABLED

        # ----------- DAY DROPDOWN -----------
        day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        day_opts = [
            discord.SelectOption(
                label=day_names[i],
                value=str(i),
                default=(i in ABYSS_DAYS)
            ) for i in range(7)
        ]

        self.day_dropdown = Select(
            placeholder="Select Abyss Days",
            options=day_opts,
            min_values=0,
            max_values=7
        )
        self.day_dropdown.callback = self.update_days
        self.add_item(self.day_dropdown)

        # ----------- ABYSS HOUR DROPDOWN -----------
        hour_opts = [
            discord.SelectOption(
                label=f"{h:02d}:00",
                value=str(h),
                default=(h in ABYSS_HOURS)
            ) for h in range(24)
        ]

        self.hour_dropdown = Select(
            placeholder="Select Abyss Hours",
            min_values=0,
            max_values=24,
            options=hour_opts
        )
        self.hour_dropdown.callback = self.update_hours
        self.add_item(self.hour_dropdown)

        # ----------- REMINDER HOURS DROPDOWN -----------
        self.refresh_reminder_dropdown()
        self.add_item(self.reminder_dropdown)

        # ----------- ROUND 2 TOGGLE BUTTON -----------
        label = "Disable Round 2" if self.round2_enabled else "Enable Round 2"
        color = discord.ButtonStyle.danger if self.round2_enabled else discord.ButtonStyle.success

        self.round2_button = Button(
            label=label,
            style=color
        )
        self.round2_button.callback = self.toggle_round2
        self.add_item(self.round2_button)

        # ----------- SAVE BUTTON -----------
        save_btn = Button(label="Save", style=discord.ButtonStyle.primary)
        save_btn.callback = self.save_changes
        self.add_item(save_btn)

    # ----------- CALLBACKS -----------
    async def update_days(self, inter2):
        self.selected_days = {int(v) for v in self.day_dropdown.values}
        await inter2.response.defer()

    async def update_hours(self, inter2):
        self.selected_hours = {int(v) for v in self.hour_dropdown.values}

        # Update reminder dropdown to match selected hours
        self.refresh_reminder_dropdown()
        self.clear_items()
        self.__init__(self.inter)

        await inter2.response.defer()

    def refresh_reminder_dropdown(self):
        reminder_opts = [
            discord.SelectOption(
                label=f"{h:02d}:00",
                value=str(h),
                default=(h in REMINDER_HOURS)
            ) for h in sorted(self.selected_hours)
        ]

        if not reminder_opts:
            reminder_opts = [
                discord.SelectOption(label="(No hours selected)", value="none", default=True)
            ]

        self.reminder_dropdown = Select(
            placeholder="Select Reminder Hours",
            min_values=0,
            max_values=len(reminder_opts),
            options=reminder_opts
        )
        self.reminder_dropdown.callback = self.update_reminder_hours

    async def update_reminder_hours(self, inter2):
        if "none" in self.reminder_dropdown.values:
            self.selected_reminder_hours = set()
        else:
            self.selected_reminder_hours = {int(v) for v in self.reminder_dropdown.values}
        await inter2.response.defer()

    async def toggle_round2(self, inter2):
        self.round2_enabled = not self.round2_enabled
        msg = "Round 2 Enabled" if self.round2_enabled else "Round 2 Disabled"
        await inter2.response.send_message(f"🔄 {msg}", ephemeral=True)

    async def save_changes(self, inter2):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg

        ABYSS_DAYS = sorted(list(self.selected_days))
        ABYSS_HOURS = sorted(list(self.selected_hours))
        REMINDER_HOURS = sorted(list(self.selected_reminder_hours))
        ROUND2_ENABLED = self.round2_enabled

        cfg["days"] = ABYSS_DAYS
        cfg["hours"] = ABYSS_HOURS
        cfg["reminder_hours"] = REMINDER_HOURS
        cfg["round2"] = ROUND2_ENABLED

        save_abyss_config(cfg)

        embed = discord.Embed(
            title="Abyss Configuration Saved",
            description=(
                f"**Days:** {ABYSS_DAYS}\n"
                f"**Abyss Hours:** {ABYSS_HOURS}\n"
                f"**Reminder Hours:** {REMINDER_HOURS}\n"
                f"**Round 2:** {ROUND2_ENABLED}"
            ),
            color=0x2ecc71
        )

        await inter2.response.send_message(embed=embed, ephemeral=True)


# ------------------------------------------------
# /abyssconfig COMMAND
# ------------------------------------------------
@bot.tree.command(name="abyssconfig", description="Configure Abyss schedule.")
async def abyssconfig_cmd(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    embed = discord.Embed(
        title="⚙ Abyss Configuration",
        description=(
            f"**Days:** {ABYSS_DAYS}\n"
            f"**Hours:** {ABYSS_HOURS}\n"
            f"**Reminder Hours:** {REMINDER_HOURS}\n"
            f"**Round 2:** {ROUND2_ENABLED}"
        ),
        color=0x3498db
    )

    await inter.response.send_message(embed=embed, view=AbyssConfigView(inter), ephemeral=True)


# ================================================
# UNIFIED REMINDER SYSTEM
# ================================================
@tasks.loop(minutes=1)
async def abyss_loop():
    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(channel_id)
    if not ch:
        return

    weekday = now.weekday()
    hour = now.hour
    minute = now.minute

    # Only run on selected Abyss days
    if weekday not in ABYSS_DAYS:
        return

    # ===========================
    # MAIN ABYSS HOURS (H:00)
    # ===========================
    if hour in ABYSS_HOURS and minute == 0:
        await ch.send(
            f"<@&{ROLE_ID}>, Abyss will start in 15 minutes!"
        )
        return

    # ===========================
    # ROUND 2 (H:30)
    # ===========================
    if ROUND2_ENABLED and hour in ABYSS_HOURS and minute == 30:
        await ch.send(
            f"<@&{ROLE_ID}>, Round 2 of Abyss will start in 15 minutes!"
        )
        return

    # ===========================
    # REMINDER HOURS (H:00 only)
    # ===========================
    # Avoid duplicates: if hour is in Abyss Hours, skip reminder
    if hour in REMINDER_HOURS and hour not in ABYSS_HOURS and minute == 0:
        await ch.send(
            f"<@&{ROLE_ID}>, Abyss will start in 15 minutes!"
        )
        return
# ================================================
# PART 3 OF 3 — Commands + Import/Export + Run
# ================================================

# ------------------------------------------------
# /exportconfig
# ------------------------------------------------
@bot.tree.command(name="exportconfig", description="Export all Abyss & Event data.")
async def exportconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    mem = io.BytesIO()

    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(CUSTOM_FILE):
            z.write(CUSTOM_FILE)
        if os.path.exists(ABYSS_CONFIG_FILE):
            z.write(ABYSS_CONFIG_FILE)

    mem.seek(0)
    await inter.response.send_message(
        "📦 **Configuration Exported**",
        file=discord.File(mem, filename="config.zip"),
        ephemeral=True
    )


# ------------------------------------------------
# VALIDATION HELPERS
# ------------------------------------------------
def strict_validate_events(d):
    if not isinstance(d, list):
        return False
    for ev in d:
        if not isinstance(ev, dict):
            return False
        if "name" not in ev or "datetime" not in ev or "reminder" not in ev:
            return False
    return True

def strict_validate_abyss(d):
    return all(k in d for k in ["days", "hours", "reminder_hours", "round2"])


def soft_validate_abyss(d):
    out = {}
    if "days" in d and isinstance(d["days"], list):
        out["days"] = [int(x) for x in d["days"]]
    if "hours" in d and isinstance(d["hours"], list):
        out["hours"] = [int(x) for x in d["hours"]]
    if "reminder_hours" in d and isinstance(d["reminder_hours"], list):
        out["reminder_hours"] = [int(x) for x in d["reminder_hours"]]
    if "round2" in d:
        out["round2"] = bool(d["round2"])
    return out


# ------------------------------------------------
# /importconfig
# ------------------------------------------------
@bot.tree.command(name="importconfig", description="Import config.zip")
async def importconfig(inter, file: discord.Attachment):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    if not file.filename.endswith(".zip"):
        return await inter.response.send_message("❌ Upload a .zip file.", ephemeral=True)

    raw = await file.read()
    mem_zip = io.BytesIO(raw)

    try:
        z = zipfile.ZipFile(mem_zip)
    except:
        return await inter.response.send_message("❌ Invalid ZIP.", ephemeral=True)

    events_data = None
    abyss_data = None

    for name in z.namelist():
        if name == CUSTOM_FILE:
            try:
                events_data = json.loads(z.read(name))
            except:
                pass
        if name == ABYSS_CONFIG_FILE:
            try:
                abyss_data = json.loads(z.read(name))
            except:
                pass

    # STRICT IMPORT
    strict_ok = True

    if events_data is not None and not strict_validate_events(events_data):
        strict_ok = False
    if abyss_data is not None and not strict_validate_abyss(abyss_data):
        strict_ok = False

    if strict_ok and events_data is not None and abyss_data is not None:
        save_custom_events(events_data)
        save_abyss_config(abyss_data)

        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, ROUND2_ENABLED, cfg
        cfg = abyss_data
        ABYSS_DAYS = cfg["days"]
        ABYSS_HOURS = cfg["hours"]
        REMINDER_HOURS = cfg["reminder_hours"]
        ROUND2_ENABLED = cfg["round2"]

        return await inter.response.send_message("✅ Strict import complete.", ephemeral=True)

    # SOFT IMPORT
    imported = []

    if events_data is not None:
        save_custom_events(events_data)
        imported.append("• custom_events.json (soft)")

    if abyss_data is not None:
        soft = soft_validate_abyss(abyss_data)
        cfg.update(soft)
        save_abyss_config(cfg)

        ABYSS_DAYS = cfg["days"]
        ABYSS_HOURS = cfg["hours"]
        REMINDER_HOURS = cfg["reminder_hours"]
        ROUND2_ENABLED = cfg["round2"]

        imported.append("• abyss_config.json (soft)")

    if not imported:
        return await inter.response.send_message("❌ Nothing importable.", ephemeral=True)

    await inter.response.send_message(
        "⚠️ Soft import completed:\n" + "\n".join(imported),
        ephemeral=True
    )


# ------------------------------------------------
# WEEKLYEVENT
# ------------------------------------------------
weekly_events = ["Melee Wheel","Melee Forge","Range Wheel","Range Forge"]
start_date = date(2025, 9, 16)
event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯",
}

@bot.tree.command(name="weeklyevent", description="Show upcoming weekly Abyss events.")
async def weeklyevent(inter):
    today = date.today()
    start_sunday = start_date - timedelta(days=start_date.weekday() + 1)
    weeks_passed = (today - start_sunday).days // 7

    this_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
    now = datetime.utcnow()
    event_start = datetime.combine(this_tuesday, time(0,0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks_passed += 1
        this_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
        event_start = datetime.combine(this_tuesday, time(0,0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    numbers = ["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i in range(4):
        idx = (weeks_passed + i) % len(weekly_events)
        event_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        name = weekly_events[idx]
        emoji = event_emojis[name]

        dt = datetime.combine(event_date, time(0,0))
        delta = dt - now

        if i == 0 and event_start <= now < event_end:
            status = "🟢 LIVE NOW"
        else:
            status = f"⏳ {delta.days}d {delta.seconds//3600}h"

        msg += f"{numbers[i]} {emoji} **{name}** — <t:{int(dt.timestamp())}:F>\n{status}\n\n"

    await inter.response.send_message(msg)


# ------------------------------------------------
# KVK EVENTS
# ------------------------------------------------
@bot.tree.command(name="kvkevent", description="Show next 4 custom events.")
async def kvkevent(inter):
    now = datetime.utcnow()
    events = load_custom_events()
    events_sorted = sorted(events, key=lambda e: datetime.fromisoformat(e["datetime"]))

    upcoming = []
    for ev in events_sorted:
        dt = datetime.fromisoformat(ev["datetime"])
        if dt > now:
            upcoming.append(ev)
        if len(upcoming) == 4:
            break

    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    msg = "📅 **Upcoming Events**\n\n"
    ids = ["1️⃣","2️⃣","3️⃣","4️⃣"]

    for i, ev in enumerate(upcoming):
        dt = datetime.fromisoformat(ev["datetime"])
        delta = dt - now
        msg += (
            f"{ids[i]} **{ev['name']}** — <t:{int(dt.timestamp())}:F>\n"
            f"⏳ {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m\n\n"
        )

    await inter.response.send_message(msg)


# ------------------------------------------------
# ADD EVENT
# ------------------------------------------------
class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(label="Event Name")
    datetime_input = TextInput(label="Datetime (UTC)", placeholder="DD-MM-YYYY HH:MM or 1d 2h")
    reminder = TextInput(label="Reminder (minutes or 'no')", placeholder="10")

    async def on_submit(self, inter):
        try:
            dt = parse_datetime(self.datetime_input.value)
            rem = 0 if self.reminder.value.lower() == "no" else int(self.reminder.value)

            new_ev = {
                "name": self.name.value,
                "datetime": dt.isoformat(),
                "reminder": rem,
            }

            events = load_custom_events()
            events.append(new_ev)
            save_custom_events(events)

            await inter.response.send_message(
                f"✅ Added: **{new_ev['name']}** (<t:{int(dt.timestamp())}:F>)",
                ephemeral=True
            )
        except Exception as e:
            await inter.response.send_message(f"❌ {e}", ephemeral=True)

@bot.tree.command(name="addevent", description="Add a custom event.")
async def addevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)
    await inter.response.send_modal(AddEventModal())


# ------------------------------------------------
# EDIT EVENT
# ------------------------------------------------
active_flows = {}

@bot.tree.command(name="editevent", description="Edit a custom event.")
async def editevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    events = load_custom_events()
    if not events:
        return await inter.response.send_message("No events found.", ephemeral=True)

    class SelectEvent(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                ) for i, e in enumerate(events)
            ]
            super().__init__(placeholder="Choose event", options=opts)

        async def callback(self, i2):
            idx = int(self.values[0])
            active_flows[inter.user.id] = {"idx": idx, "field": ""}

            class EditMenu(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self, btn, i3):
                    active_flows[inter.user.id]["field"] = "name"
                    await i3.response.send_message("Enter new name:", ephemeral=True)

                @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.secondary)
                async def edit_dt(self, btn, i3):
                    active_flows[inter.user.id]["field"] = "datetime"
                    await i3.response.send_message("Enter new datetime:", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_rm(self, btn, i3):
                    active_flows[inter.user.id]["field"] = "reminder"
                    await i3.response.send_message("Enter new reminder:", ephemeral=True)

            await i2.response.send_message("Choose field:", view=EditMenu(), ephemeral=True)

    await inter.response.send_message(
        "Choose an event to edit:",
        view=View().add_item(SelectEvent()),
        ephemeral=True
    )


# ON_MESSAGE — handles edit flows
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    if msg.author.id not in active_flows:
        return

    flow = active_flows[msg.author.id]
    idx = flow["idx"]
    field = flow["field"]

    events = load_custom_events()
    if not (0 <= idx < len(events)):
        del active_flows[msg.author.id]
        return

    if field == "datetime":
        events[idx]["datetime"] = parse_datetime(msg.content).isoformat()
    elif field == "reminder":
        events[idx]["reminder"] = 0 if msg.content.lower() == "no" else int(msg.content)
    else:
        events[idx]["name"] = msg.content

    save_custom_events(events)
    await msg.channel.send("✅ Event updated.")
    del active_flows[msg.author.id]


# ------------------------------------------------
# REMOVE EVENT
# ------------------------------------------------
@bot.tree.command(name="removeevent", description="Delete a custom event.")
async def removeevent(inter):
    if not has_admin(inter):
        return await inter.response.send_message("❌ No permission.", ephemeral=True)

    events = load_custom_events()
    if not events:
        return await inter.response.send_message("No events found.", ephemeral=True)

    class SelectRemove(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                ) for i, e in enumerate(events)
            ]
            super().__init__(placeholder="Choose event to delete", options=opts)

        async def callback(self, i2):
            idx = int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(self, btn, i3):
                    evs = load_custom_events()
                    if 0 <= idx < len(evs):
                        ev = evs.pop(idx)
                        save_custom_events(evs)
                        await i3.response.send_message(f"🗑 Deleted **{ev['name']}**")
                    else:
                        await i3.response.send_message("Error.")
                
                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(self, btn, i3):
                    await i3.response.send_message("Cancelled.", ephemeral=True)

            await i2.response.send_message("Confirm deletion:", view=Confirm(), ephemeral=True)

    await inter.response.send_message(
        "Select event to delete:",
        view=View().add_item(SelectRemove()),
        ephemeral=True
    )


# ------------------------------------------------
# RUN THE BOT
# ------------------------------------------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
bot.run(TOKEN)
