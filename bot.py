import discord
from discord.ext import commands, tasks
from discord import app_commands
import pytz
import os
import json
from datetime import date, datetime, timedelta, time
from discord.ui import View, Button, Select, Modal, TextInput

# ==============================
# CONFIGURATION
# ==============================
MY_TIMEZONE = "UTC"

channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490
GUILD_ID = 1328405638744641548

CUSTOM_FILE = "custom_events.json"
ABYSS_CONFIG_FILE = "abyss_config.json"

DEFAULT_ABYSS_DAYS = [1, 4, 6]
DEFAULT_ABYSS_HOURS = [0, 4, 8, 12, 16, 20]
DEFAULT_REMINDER_HOURS = DEFAULT_ABYSS_HOURS
DEFAULT_OFFSETS = [15]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

active_flows = {}
sent_reminders = set()

# ==============================
# LOAD / SAVE
# ==============================
def load_custom_events():
    if not os.path.exists(CUSTOM_FILE):
        return []
    return json.load(open(CUSTOM_FILE))

def save_custom_events(events):
    json.dump(events, open(CUSTOM_FILE, "w"), indent=2)

def load_abyss_config():
    if not os.path.exists(ABYSS_CONFIG_FILE):
        return {
            "days": DEFAULT_ABYSS_DAYS,
            "hours": DEFAULT_ABYSS_HOURS,
            "reminder_hours": DEFAULT_REMINDER_HOURS,
            "reminder_offsets": DEFAULT_OFFSETS,
        }
    return json.load(open(ABYSS_CONFIG_FILE))

def save_abyss_config(cfg):
    json.dump(cfg, open(ABYSS_CONFIG_FILE, "w"), indent=2)

cfg = load_abyss_config()
ABYSS_DAYS = cfg["days"]
ABYSS_HOURS = cfg["hours"]
REMINDER_HOURS = cfg["reminder_hours"]
REMINDER_OFFSETS = cfg["reminder_offsets"]

# ==============================
# HELPERS
# ==============================
def parse_datetime(txt: str):
    try:
        return datetime.strptime(txt, "%d-%m-%Y %H:%M")
    except:
        pass

    now = datetime.utcnow()
    d = h = m = 0
    for part in txt.split():
        if "d" in part:
            d = int(part.replace("d", ""))
        elif "h" in part:
            h = int(part.replace("h", ""))
        elif "m" in part:
            m = int(part.replace("m", ""))
    return now + timedelta(days=d, hours=h, minutes=m)

def has_admin(inter):
    return inter.user.id == OWNER_ID or any(r.name.lower() == "admin" for r in inter.user.roles)

async def log_action(txt):
    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send(txt)

# ==============================
# READY
# ==============================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} global commands")
    except Exception as e:
        print("Sync error:", e)

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Bot updated & online!")

    check_time.start()
    event_reminder.start()

# ==============================
# UPGRADED /abyssconfig
# ==============================
class OffsetModal(Modal, title="Set Reminder Offsets (minutes)"):
    offsets = TextInput(label="Offsets", placeholder="Example: 5, 10, 15, 60")

    def __init__(self, inter):
        super().__init__()
        self.inter = inter

    async def on_submit(self, inter2):
        global REMINDER_OFFSETS, cfg

        raw = self.offsets.value.replace(",", " ")
        nums = []

        for part in raw.split():
            if part.isdigit():
                nums.append(int(part))

        if not nums:
            await inter2.response.send_message("❌ Invalid offsets.", ephemeral=True)
            return

        REMINDER_OFFSETS = nums
        cfg["reminder_offsets"] = nums
        save_abyss_config(cfg)

        await inter2.response.send_message(
            f"✅ Offsets updated: {nums}", ephemeral=True
        )

class AbyssConfigView(View):
    def __init__(self, inter):
        super().__init__(timeout=300)
        self.inter = inter
        self.selected_days = set(ABYSS_DAYS)
        self.selected_hours = set(ABYSS_HOURS)
        self.selected_reminder_hours = set(REMINDER_HOURS)

        # DAY DROPDOWN
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_opts = [
            discord.SelectOption(label=day_names[i], value=str(i),
                                 default=(i in ABYSS_DAYS))
            for i in range(7)
        ]

        self.days_dropdown = Select(
            placeholder="Select Days",
            options=day_opts,
            min_values=0,
            max_values=7
        )
        self.days_dropdown.callback = self.update_days
        self.add_item(self.days_dropdown)

        # HOURS DROPDOWN
        hour_opts = [
            discord.SelectOption(
                label=f"{h:02d}:00",
                value=str(h),
                default=(h in ABYSS_HOURS)
            )
            for h in range(24)
        ]

        self.hours_dropdown = Select(
            placeholder="Select Abyss Hours",
            options=hour_opts,
            min_values=0,
            max_values=24
        )
        self.hours_dropdown.callback = self.update_hours
        self.add_item(self.hours_dropdown)

        # REMINDER HOURS
        rem_opts = [
            discord.SelectOption(
                label=f"{h:02d}:00",
                value=str(h),
                default=(h in REMINDER_HOURS)
            )
            for h in range(24)
        ]

        self.reminder_hours_dropdown = Select(
            placeholder="Select Reminder Hours",
            options=rem_opts,
            min_values=0,
            max_values=24
        )
        self.reminder_hours_dropdown.callback = self.update_reminder_hours
        self.add_item(self.reminder_hours_dropdown)

        # BUTTONS
        btn_offsets = Button(label="Set Offsets", style=discord.ButtonStyle.secondary)
        btn_offsets.callback = self.open_offset_modal
        self.add_item(btn_offsets)

        btn_save = Button(label="Save", style=discord.ButtonStyle.success)
        btn_save.callback = self.save_changes
        self.add_item(btn_save)

    async def update_days(self, inter):
        self.selected_days = {int(v) for v in self.days_dropdown.values}
        await inter.response.defer()

    async def update_hours(self, inter):
        self.selected_hours = {int(v) for v in self.hours_dropdown.values}
        await inter.response.defer()

    async def update_reminder_hours(self, inter):
        self.selected_reminder_hours = {int(v) for v in self.reminder_hours_dropdown.values}
        await inter.response.defer()

    async def open_offset_modal(self, inter):
        await inter.response.send_modal(OffsetModal(inter))

    async def save_changes(self, inter):
        global ABYSS_DAYS, ABYSS_HOURS, REMINDER_HOURS, cfg

        ABYSS_DAYS = sorted(list(self.selected_days))
        ABYSS_HOURS = sorted(list(self.selected_hours))
        REMINDER_HOURS = sorted(list(self.selected_reminder_hours))

        cfg["days"] = ABYSS_DAYS
        cfg["hours"] = ABYSS_HOURS
        cfg["reminder_hours"] = REMINDER_HOURS

        save_abyss_config(cfg)

        embed = discord.Embed(
            title="Abyss Config Updated",
            description=(
                f"**Days:** {ABYSS_DAYS}\n"
                f"**Hours:** {ABYSS_HOURS}\n"
                f"**Reminder Hours:** {REMINDER_HOURS}\n"
                f"**Offsets:** {REMINDER_OFFSETS}"
            ),
            color=0x2ecc71
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="abyssconfig", description="Configure Abyss schedule")
async def abyssconfig_cmd(inter):
    if inter.user.id != OWNER_ID:
        await inter.response.send_message("❌ Owner only.", ephemeral=True)
        return

    embed = discord.Embed(
        title="⚙ Abyss Configuration",
        description=(
            f"**Days:** {ABYSS_DAYS}\n"
            f"**Hours:** {ABYSS_HOURS}\n"
            f"**Reminder Hours:** {REMINDER_HOURS}\n"
            f"**Offsets:** {REMINDER_OFFSETS}"
        ),
        color=0x3498db
    )

    await inter.response.send_message(embed=embed, view=AbyssConfigView(inter), ephemeral=True)

# ==============================
# ABYSS SCHEDULE LOOP
# ==============================
@tasks.loop(minutes=1)
async def check_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)

    if now.weekday() not in ABYSS_DAYS:
        return

    if now.hour in ABYSS_HOURS and now.minute == 0:
        ch = bot.get_channel(channel_id)
        if ch:
            await ch.send("<@&1413532222396301322>, Abyss starts in 15 minutes!")

    if now.hour in ABYSS_HOURS and now.minute == 30:
        ch = bot.get_channel(channel_id)
        if ch:
            await ch.send("<@&1413532222396301322>, Round 2 starts in 15 minutes!")

# ==============================
# REMINDER LOOP (closest offset only)
# ==============================
@tasks.loop(minutes=1)
async def event_reminder():
    global sent_reminders
    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(channel_id)

    for hr in REMINDER_HOURS:
        for offset in REMINDER_OFFSETS:
            target = now + timedelta(minutes=offset)

            if target.hour == hr and target.minute == 0:
                key = (hr, offset)
                if key not in sent_reminders:
                    if ch:
                        await ch.send(
                            f"⏰ Abyss starts in {offset} minutes (at {hr:02d}:00 UTC)"
                        )
                    sent_reminders.add(key)

    if len(sent_reminders) > 200:
        sent_reminders = set(list(sent_reminders)[-100:])

# ==============================
# WEEKLY EVENT COMMAND
# ==============================
weekly_events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
start_date = date(2025, 9, 16)
event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯",
}

@bot.tree.command(name="weeklyevent", description="Check the next 4 weekly Abyss events")
async def weeklyevent(inter):
    today = date.today()
    start_sunday = start_date - timedelta(days=start_date.weekday() + 1)
    weeks_passed = (today - start_sunday).days // 7

    this_week_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
    now = datetime.utcnow()
    event_start = datetime.combine(this_week_tuesday, time(0, 0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks_passed += 1
        this_week_tuesday = start_sunday + timedelta(weeks=weeks_passed, days=2)
        event_start = datetime.combine(this_week_tuesday, time(0, 0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    ids = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i in range(4):
        idx = (weeks_passed + i) % len(weekly_events)
        event_date = start_sunday + timedelta(weeks=weeks_passed + i, days=2)
        name = weekly_events[idx]
        emoji = event_emojis.get(name, "📌")

        base_dt = datetime.combine(event_date, time(0, 0))

        if i == 0 and event_start <= now < event_end:
            delta = event_end - now
            status = f"🟢 LIVE NOW (ends in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m)"
        else:
            delta = base_dt - now
            status = f"⏳ Starts in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"

        msg += f"{ids[i]} {emoji} **{name}** — <t:{int(base_dt.timestamp())}:F>\n{status}\n\n"

    await inter.response.send_message(msg)

# ==============================
# KVK CUSTOM EVENTS
# ==============================
@bot.tree.command(name="kvkevent", description="Show next 4 upcoming custom events")
async def kvkevent(inter):
    now = datetime.utcnow()
    events = load_custom_events()

    sorted_events = sorted(events, key=lambda e: datetime.fromisoformat(e["datetime"]))

    upcoming = []
    for ev in sorted_events:
        dt = datetime.fromisoformat(ev["datetime"])
        if dt <= now < dt + timedelta(hours=1):
            upcoming.append((ev["name"], dt, "live"))
        elif dt > now:
            upcoming.append((ev["name"], dt, "upcoming"))
        if len(upcoming) == 4:
            break

    if not upcoming:
        await inter.response.send_message("📭 No upcoming events.", ephemeral=True)
        return

    msg = "📅 **Upcoming Events**\n\n"
    ids = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i, (name, dt, state) in enumerate(upcoming):
        if state == "live":
            remaining = (dt + timedelta(hours=1)) - now
            mins = max(1, remaining.seconds // 60)
            status = f"🟢 LIVE (ends in ~{mins}m)"
        else:
            delta = dt - now
            status = f"⏳ Starts in {delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"

        msg += f"{ids[i]} **{name}** — <t:{int(dt.timestamp())}:F>\n{status}\n\n"

    await inter.response.send_message(msg)

# ==============================
# ADD CUSTOM EVENT
# ==============================
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
                f"✅ Event added: **{new_ev['name']}** at <t:{int(dt.timestamp())}:F>",
                ephemeral=True,
            )
            await log_action(f"📝 Event Added by {inter.user.mention}")
        except Exception as e:
            await inter.response.send_message(f"❌ Failed: {e}", ephemeral=True)

@bot.tree.command(name="addevent", description="Add a custom event (admin only)")
async def addevent(inter):
    if not has_admin(inter):
        await inter.response.send_message("❌ No permission.", ephemeral=True)
        return
    await inter.response.send_modal(AddEventModal())

# ==============================
# EDIT EVENT
# ==============================
@bot.tree.command(name="editevent", description="Edit a custom event")
async def editevent(inter):
    if not has_admin(inter):
        await inter.response.send_message("❌ No permission.", ephemeral=True)
        return

    custom = load_custom_events()
    if not custom:
        await inter.response.send_message("No events found.", ephemeral=True)
        return

    class SelectEvent(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                )
                for i, e in enumerate(custom)
            ]
            super().__init__(placeholder="Choose event to edit", options=opts)

        async def callback(self, inter2):
            idx = int(self.values[0])
            active_flows[inter.user.id] = {"idx": idx}

            class EditButtons(View):
                @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary)
                async def edit_name(self, btn, i):
                    active_flows[inter.user.id]["field"] = "name"
                    await i.response.send_message("Enter new name:", ephemeral=True)

                @discord.ui.button(label="Edit Datetime", style=discord.ButtonStyle.secondary)
                async def edit_dt(self, btn, i):
                    active_flows[inter.user.id]["field"] = "datetime"
                    await i.response.send_message("Enter new datetime:", ephemeral=True)

                @discord.ui.button(label="Edit Reminder", style=discord.ButtonStyle.success)
                async def edit_rem(self, btn, i):
                    active_flows[inter.user.id]["field"] = "reminder"
                    await i.response.send_message("Enter new reminder:", ephemeral=True)

            await inter2.response.send_message("Choose field to edit:", view=EditButtons(), ephemeral=True)

    v = View()
    v.add_item(SelectEvent())
    await inter.response.send_message("Select event:", view=v, ephemeral=True)

# ==============================
# DELETE EVENT
# ==============================
@bot.tree.command(name="removeevent", description="Delete a custom event")
async def removeevent(inter):
    if not has_admin(inter):
        await inter.response.send_message("❌ No permission.", ephemeral=True)
        return

    custom = load_custom_events()
    if not custom:
        await inter.response.send_message("No events.", ephemeral=True)
        return

    class SelectRemove(Select):
        def __init__(self):
            opts = [
                discord.SelectOption(
                    label=e["name"],
                    description=datetime.fromisoformat(e["datetime"]).strftime("%d-%m %H:%M UTC"),
                    value=str(i)
                )
                for i, e in enumerate(custom)
            ]
            super().__init__(options=opts, placeholder="Select event")

        async def callback(self, inter2):
            idx = int(self.values[0])

            class Confirm(View):
                @discord.ui.button(label="YES", style=discord.ButtonStyle.danger)
                async def yes(self, b, i2):
                    evs = load_custom_events()
                    if 0 <= idx < len(evs):
                        ev = evs.pop(idx)
                        save_custom_events(evs)
                        await i2.response.send_message(f"🗑 Removed: {ev['name']}")
                        await log_action(f"🗑 Event removed by {inter.user.mention}")

                @discord.ui.button(label="NO", style=discord.ButtonStyle.secondary)
                async def no(self, b, i2):
                    await i2.response.send_message("Cancelled.", ephemeral=True)

            await inter2.response.send_message("Confirm deletion:", view=Confirm(), ephemeral=True)

    v = View()
    v.add_item(SelectRemove())
    await inter.response.send_message("Select event to remove:", view=v, ephemeral=True)

# ==============================
# EDIT FLOW HANDLER
# ==============================
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
    await log_action(f"✏️ Event edited by {msg.author.mention}")
    del active_flows[msg.author.id]

# ==============================
# CUSTOM EVENT REMINDER LOOP
# ==============================
@tasks.loop(minutes=1)
async def event_reminder():
    global sent_reminders
    now = datetime.utcnow().replace(second=0, microsecond=0)
    ch = bot.get_channel(channel_id)

    for hr in REMINDER_HOURS:
        for offset in REMINDER_OFFSETS:
            target = now + timedelta(minutes=offset)
            if target.hour == hr and target.minute == 0:
                key = (hr, offset)
                if key not in sent_reminders:
                    if ch:
                        await ch.send(
                            f"⏰ Abyss starts in {offset} minutes (at {hr:02d}:00 UTC)"
                        )
                    sent_reminders.add(key)

    if len(sent_reminders) > 200:
        sent_reminders = set(list(sent_reminders)[-100:])

# ==============================
# RUN
# ==============================
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
bot.run(TOKEN)
