# ============================================================
# FLASK KEEPALIVE (STARTS IMMEDIATELY – KOYEB SAFE)
# ============================================================

from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "OK", 200

@app.route("/health")
def health():
    log_info("[HEALTH CHECK] ping received")
    return "healthy", 200


def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# ============================================================
# DISCORD + SYSTEM IMPORTS
# ============================================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import sqlite3
import pytz
from datetime import datetime, timedelta, date, time
from discord.ui import View, Select, Button, Modal, TextInput
import io
import zipfile
import asyncio
import aiohttp

# ============================================================
# LOGGING SYSTEM
# ============================================================

import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# GLOBAL CONFIG
# ============================================================

MY_TIMEZONE = "UTC"
channel_id = 1328658110897983549
update_channel_id = 1332676174995918859
OWNER_ID = 1084884048884797490
ROLE_ID = 1413532222396301322
BACKUP_CHANNEL_ID = 1444604637377204295
ABYSS_ROLE_ID = 1413532222396301322
EVENT_ANNOUNCEMENT_ROLE_ID = 1412464184746053693
ABYSS_CONFIG_FILE = "abyss_config.json"
DB = "/data/events.db"
DB_PROGRESS = "/data/season_progress.db"  # Separate database for seasonal data

# ============================================================
# CALL OF STATS ACCOUNT IDS & CONSTANTS
# ============================================================

REKZ_ACCOUNT_ID = "16322115"
FALLBACK_DAYS = 6  # Days to fallback when data is empty

# Discord ID -> Call of Stats Account ID mapping
# For members who may not have numeric roles in server
DISCORD_TO_ACCOUNT_ID = {
    1244330800019804180: "7979635",  # Havi
}

# ============================================================
# USERNAME LOOKUP (Map Discord usernames to Discord IDs)
# ============================================================
# Hardcoded mapping - add your members here
# Username: Discord ID
USERNAME_TO_DISCORD_ID = {
    "rekz": 1084884048884797490,
    "truvix": 797778630025019402,
    "azrael": 663715561951461376,
    "drakken": 401088806432014347,
    "gato": 937458459115413565,
    "truffles": 1285424051761713155,
    "havi": 1244330800019804180,
}


# ============================================================
# CACHE SETTINGS
# ============================================================

CACHE_EXPIRY_HOURS = 72  # 3 days - cache validity period

# ============================================================
# LOGGING SETUP (Simple alternative to print)
# ============================================================

import logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def log_info(message):
    """Log info message"""
    logger.info(message)

def log_error(message):
    """Log error message"""
    logger.error(message)

def log_debug(message):
    """Log debug message"""
    logger.debug(message)
    
BACKUP_DIR = "backups"
MAX_BACKUPS = 10
os.makedirs(BACKUP_DIR, exist_ok=True)

# ============================================================
# REQUIRED HELPERS (FIXES ALL CRASHES)
# ============================================================

def has_admin(inter):
    if inter.user.id == OWNER_ID:
        return True
    return any(r.permissions.administrator for r in inter.user.roles)

def parse_datetime(input_str):
    input_str = input_str.strip()
    now = datetime.utcnow()

    # Case 1: full date + HH:MM
    try:
        return datetime.strptime(input_str, "%d-%m-%Y %H:%M")
    except Exception as e:
        pass

    # Case 2: full date + HHutc
    if "-" in input_str and "utc" in input_str:
        date_part, time_part = input_str.split()
        base_date = datetime.strptime(date_part, "%d-%m-%Y")
        hour = int(time_part.replace("utc", ""))
        return base_date.replace(
            hour=hour, minute=0, second=0, microsecond=0
        )

    # Relative parsing
    d = h = m = 0
    for part in input_str.lower().split():
        if part.endswith("d"):
            d = int(part[:-1])
        elif part.endswith("h"):
            h = int(part[:-1])
        elif part.endswith("m"):
            m = int(part[:-1])
        elif part.endswith("utc"):
            hour = int(part.replace("utc", ""))
            return now.replace(
                hour=hour, minute=0, second=0, microsecond=0
            )

    return now + timedelta(days=d, hours=h, minutes=m)


def day_name(i):
    return ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i]

def pretty_days(days):
    return ", ".join(day_name(d) for d in sorted(days))

def pretty_hours(hours):
    return ", ".join(f"{h:02}:00" for h in sorted(hours))


async def dm_abyss_role(guild: discord.Guild, embed: discord.Embed):
    """
    Send a DM to all members with the Abyss reminder role.
    
    Args:
        guild: Discord guild/server
        embed: Discord embed to send
    
    Returns:
        None (logs success/errors)
    """
    role = guild.get_role(ABYSS_ROLE_ID)
    if not role:
        log_info(f"[ABYSS] Role not found in guild {guild.id}")
        return

    count = 0
    async for member in guild.fetch_members(limit=None):
        if role in member.roles:
            try:
                dm = await member.create_dm()
                await dm.send(embed=embed)
                count += 1
                # Rate limiting - wait 0.5 seconds between DMs to prevent hitting rate limits
                await asyncio.sleep(0.5)
            except discord.Forbidden:
                continue
            except Exception as e:
                log_info(f"[ABYSS] DM error: {e}")
    
    log_info(f"[ABYSS] Sent DM to {count} members with role {ABYSS_ROLE_ID}")



# ============================================================
# BACKUP SYSTEM
# ============================================================

def cleanup_old_backups():
    """
    Remove old backup files, keeping only the MAX_BACKUPS most recent.
    
    Returns:
        None
    """
    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
        reverse=True
    )
    for f in files[MAX_BACKUPS:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
            log_info(f"Deleted old backup: {f}")
        except Exception as e:
            log_error(f"Failed to delete backup {f}: {e}")

async def upload_backup(path):
    """
    Upload a backup file to the backup channel.
    
    Args:
        path: Path to the backup zip file
    
    Returns:
        None
    """
    try:
        ch = bot.get_channel(BACKUP_CHANNEL_ID)
        if ch:
            await ch.send("📦 **Backup created**", file=discord.File(path))
    except Exception as e:
        log_error(f"[UPLOAD BACKUP] Error: {e}")

def make_backup():
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BACKUP_DIR, f"backup_{ts}.zip")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB):
            z.write(DB)
        if os.path.exists(ABYSS_CONFIG_FILE):
            z.write(ABYSS_CONFIG_FILE)

    cleanup_old_backups()

    if bot.loop.is_running():
        bot.loop.create_task(upload_backup(path))

def silent_backup():
    try:
        make_backup()
    except Exception as e:
        pass

def get_all_lords_from_guild(guild):
    """Get all numeric roles (account IDs) from the guild"""
    lords = []
    
    # Scan ALL roles in the server
    for role in guild.roles:
        if role.name.isdigit() and role.name != "@everyone":
            lords.append({
                "name": role.name,
                "account_id": role.name,
                "role": role
            })
    
    return lords

# ============================================================
# CALLOFSTATS CACHE SYSTEM
# ============================================================

_stats_cache = {}
CACHE_EXPIRY_HOURS = 72  # 3 days
CACHE_DURATION = 600  # 10 minutes - for in-memory cache of fetched stats

async def fetch_highest_power(account_id):
    """
    Fetch the HIGHEST POWER from the normal profile page (no date range)
    Uses the authenticated Call of Stats session
    Returns the highest power value as int, or None if not found
    """
    import re
    
    try:
        # Use the authenticated session instead of creating a new one
        session = await get_callofstats_session()
        url = f"https://callofstats.com/lord/{account_id}"
        
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                log_info(f"[HIGHEST POWER] Failed to fetch {url}: {response.status}")
                return None
            
            html = await response.text()
            
            # Try multiple patterns
            patterns = [
                r'Highest Power</span>.*?<div class="value">([0-9,]+)</div>',
                r'<span class="subtle">Highest Power</span>.*?<div class="value">([0-9,]+)</div>',
                r'Highest Power.*?([0-9,]+)',
            ]
            
            for i, pattern in enumerate(patterns):
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    power_str = match.group(1).replace(",", "")
                    try:
                        highest_power = int(power_str)
                        log_info(f"[HIGHEST POWER] {account_id} = {highest_power:,} (pattern {i})")
                        return highest_power
                    except Exception as e:
                        log_info(f"[HIGHEST POWER] Failed to parse: {e}")
            
            # Debug: show section around "Highest Power"
            idx = html.find("Highest Power")
            if idx != -1:
                debug_html = html[max(0, idx-200):min(len(html), idx+400)]
                log_info(f"[HIGHEST POWER DEBUG] HTML around 'Highest Power':\n{debug_html}")
            else:
                log_info(f"[HIGHEST POWER] 'Highest Power' not found in HTML at all")
                # Show first 3000 chars
                log_info(f"[HIGHEST POWER DEBUG] First 3000 chars:\n{html[:3000]}")
            
            return None
    
    except Exception as e:
        log_info(f"[HIGHEST POWER ERROR] {account_id}: {e}")
        import traceback
        traceback.print_exc()
        return None
    """
    Fetch the CURRENT highest power for a lord (no date range)
    Returns the power number as int
    """
    import re
    
    try:
        url = f"https://callofstats.com/lord/{account_id}"
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30, connect=10, sock_read=10)) as session:
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    log_info(f"[CURRENT POWER] Failed to fetch {url}: {response.status}")
                    return None
                
                html = await response.text()
                
                # Look for <h2>150,000,000</h2> pattern (current highest power)
                power_match = re.search(r'<h2[^>]*>([0-9,]+)</h2>', html)
                if power_match:
                    power_str = power_match.group(1).replace(",", "")
                    power = int(power_str)
                    log_info(f"[CURRENT POWER] {account_id} = {power}")
                    return power
                
                log_info(f"[CURRENT POWER] Could not parse power for {account_id}")
                return None
    except Exception as e:
        log_info(f"[CURRENT POWER ERROR] {account_id}: {e}")
        return None


async def fetch_current_t_kills(account_id):
    """
    Fetch the CURRENT T5-T1 kill totals for a lord (no date range)
    Uses the authenticated Call of Stats session
    Returns dict: {"t5": 123456, "t4": 234567, ...} or empty dict if not found
    """
    import re
    
    try:
        # Use the authenticated session instead of creating a new one
        session = await get_callofstats_session()
        url = f"https://callofstats.com/lord/{account_id}"
        
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                log_info(f"[CURRENT T-KILLS] Failed to fetch {url}: {response.status}")
                return {}
            
            html = await response.text()
            
            t_kills = {}
            
            # Look for T5 Kills pattern - very flexible
            for tier in ["T5", "T4", "T3", "T2", "T1"]:
                # Try multiple patterns
                patterns = [
                    f'{tier} Kills</span>.*?<div class="value">([0-9,]+)</div>',
                    f'<span class="subtle">{tier} Kills</span>.*?<div class="value">([0-9,]+)</div>',
                    f'{tier} Kills.*?([0-9,]+)',
                ]
                
                match = None
                for pattern in patterns:
                    match = re.search(pattern, html, re.DOTALL)
                    if match:
                        break
                
                if match:
                    kills_str = match.group(1).replace(",", "")
                    try:
                        t_kills[tier.lower()] = int(kills_str)
                        log_info(f"[CURRENT T-KILLS] Parsed {tier}: {kills_str}")
                    except Exception as e:
                        log_info(f"[CURRENT T-KILLS] Failed to parse {tier}: {e}")
                else:
                    log_info(f"[CURRENT T-KILLS] Pattern not found for {tier}")
                    # Debug
                    idx = html.find(f"{tier} Kills")
                    if idx != -1:
                        debug_html = html[max(0, idx-100):min(len(html), idx+300)]
                        log_info(f"[CURRENT T-KILLS DEBUG {tier}]:\n{debug_html}")
            
            if t_kills:
                log_info(f"[CURRENT T-KILLS] {account_id} = {t_kills}")
                return t_kills
            else:
                log_info(f"[CURRENT T-KILLS] Could not parse any T-kills for {account_id}")
                return {}
    except Exception as e:
        log_info(f"[CURRENT T-KILLS ERROR] {account_id}: {e}")
        import traceback
        traceback.print_exc()
        return {}


async def fetch_latest_data_date(account_id):
    """
    Extract the latest data date from Call of Stats profile
    Reads from data-current-date attribute in linkacct-data div
    Returns date string in format "DD/MM/YYYY" or None if not found
    """
    import re
    from datetime import datetime
    
    try:
        session = await get_callofstats_session()
        url = f"https://callofstats.com/lord/{account_id}"
        
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                log_info(f"[LATEST DATA DATE] Failed to fetch {url}: {response.status}")
                return None
            
            html = await response.text()
            
            # Extract from data-current-date attribute in linkacct-data div
            # Format in HTML: data-current-date="2026-03-25" (YYYY-MM-DD)
            pattern = r'data-current-date="(\d{4}-\d{2}-\d{2})"'
            match = re.search(pattern, html)
            
            if match:
                date_str = match.group(1)  # Returns YYYY-MM-DD format
                # Convert YYYY-MM-DD to DD/MM/YYYY for consistency
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = dt.strftime("%d/%m/%Y")
                log_info(f"[LATEST DATA DATE] {account_id} = {formatted_date}")
                return formatted_date
            
            log_info(f"[LATEST DATA DATE] Could not find date for {account_id}")
            return None
    except Exception as e:
        log_info(f"[LATEST DATA DATE ERROR] {account_id}: {e}")
        return None


async def fetch_stats_with_fallback(account_id, start_date, end_date):
    """
    Fetch stats and automatically fallback to earlier dates if data is empty.
    Returns (stats, actual_end_date_used)
    """
    from datetime import timedelta
    
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    # Try up to FALLBACK_DAYS back
    for days_back in range(FALLBACK_DAYS):
        current_end = (end_dt - timedelta(days=days_back)).isoformat()
        log_info(f"[FALLBACK] Trying date: {current_end}")
        
        stats = await fetch_stats_for_account(account_id, start_date, current_end, skip_cache=True)
        
        if not stats:
            log_info(f"[FALLBACK] No stats returned for {current_end}, trying earlier")
            continue
        
        # Check if any data exists (not all zeros/None)
        has_data = False
        for key in ["power_gain", "merits", "kills_gain", "deads_gain", "healed_gain", 
                    "t5_gain", "t4_gain", "t3_gain", "t2_gain", "t1_gain",
                    "gold_spent", "wood_spent", "ore_spent", "mana_spent",
                    "gold_gathered", "wood_gathered", "ore_gathered", "mana_gathered"]:
            val = stats.get(key)
            if val and val != "+0" and val != "0":
                has_data = True
                break
        
        if has_data:
            log_info(f"[FALLBACK] Found data for {current_end}")
            return stats, current_end
        else:
            log_info(f"[FALLBACK] All zeros for {current_end}, trying earlier")
    
    # Return the original stats even if empty (for last resort)
    return stats, end_date


def get_cached_stats(account_id, start_date, end_date):
    """Get stats from cache if valid (not expired)"""
    cache_key = f"{account_id}_{start_date}_{end_date}"
    if cache_key in _stats_cache:
        cached = _stats_cache[cache_key]
        age_hours = (datetime.utcnow() - cached["timestamp"]).total_seconds() / 3600
        if age_hours < CACHE_EXPIRY_HOURS:
            log_info(f"[CACHE HIT] {account_id} (age: {int(age_hours)}h)")
            return cached["stats"]
        else:
            del _stats_cache[cache_key]
    return None


def set_cached_stats(account_id, start_date, end_date, stats):
    """Store stats in cache with timestamp"""
    cache_key = f"{account_id}_{start_date}_{end_date}"
    _stats_cache[cache_key] = {"timestamp": datetime.utcnow(), "stats": stats}
    log_info(f"[CACHE SET] {account_id}")

# ============================================================
# SQLITE DATABASE
# ============================================================

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
    c.execute("""
        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS lords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lord_name TEXT NOT NULL,
            account_id TEXT NOT NULL UNIQUE
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS callofstats_update (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latest_data_date TEXT NOT NULL,
            last_checked TEXT NOT NULL,
            notified INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()

def init_db_progress():
    """Initialize separate database for season progress tracking"""
    conn = sqlite3.connect(DB_PROGRESS)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS season_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL,
            account_id TEXT NOT NULL,
            data_date TEXT NOT NULL,
            lord_name TEXT NOT NULL,
            power_gain TEXT,
            merits TEXT,
            kills_gain TEXT,
            deads_gain TEXT,
            healed_gain TEXT,
            t5_gain TEXT,
            t4_gain TEXT,
            t3_gain TEXT,
            t2_gain TEXT,
            t1_gain TEXT,
            gold_spent TEXT,
            wood_spent TEXT,
            ore_spent TEXT,
            mana_spent TEXT,
            gold_gathered TEXT,
            wood_gathered TEXT,
            ore_gathered TEXT,
            mana_gathered TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(season_id, account_id, data_date)
        );
    """)
    conn.commit()
    conn.close()

def migrate_db(conn):
    """Handle database schema migrations for backwards compatibility"""
    try:
        pass  # No migrations needed - using separate databases now
    except Exception as e:
        log_error(f"[DB MIGRATION] Error: {e}")

def db_add_event(name, dt, reminder):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO events (name, datetime, reminder) VALUES (?, ?, ?)",
        (name, dt, reminder)
    )
    log_info(f"[DB ADD EVENT] writing to: {DB}")
    conn.commit()
    conn.close()
    silent_backup()

def db_get_events():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "SELECT id, name, datetime, reminder FROM events ORDER BY datetime ASC"
    )
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
    silent_backup()

def db_delete_event(event_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()
    silent_backup()

init_db()
init_db_progress()

# ============================================================
# SEASON TRACKER DATABASE FUNCTIONS
# ============================================================

def db_add_season(season_name, start_date):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    created_at = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO seasons (season_name, start_date, created_at) VALUES (?, ?, ?)",
        (season_name, start_date, created_at)
    )
    conn.commit()
    conn.close()
    silent_backup()

def db_get_current_season():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, season_name, start_date, created_at FROM seasons ORDER BY created_at DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def db_get_season_by_name(season_name):
    """Get season by name (case-insensitive)"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, season_name, start_date, created_at FROM seasons WHERE LOWER(season_name) = LOWER(?) LIMIT 1", (season_name,))
    row = c.fetchone()
    conn.close()
    return row

def db_get_all_seasons():
    """Get all seasons ordered by creation date"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, season_name, start_date, created_at FROM seasons ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def db_add_lord(lord_name, account_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO lords (lord_name, account_id) VALUES (?, ?)",
        (lord_name, account_id)
    )
    conn.commit()
    conn.close()
    silent_backup()

def db_get_all_lords():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, lord_name, account_id FROM lords ORDER BY lord_name ASC")
    rows = c.fetchall()
    conn.close()
    return rows

# ============================================================
# CALL OF STATS UPDATE TRACKING
# ============================================================

def db_get_last_known_data_date():
    """Get the last known Call of Stats data date"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT latest_data_date FROM callofstats_update ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def db_update_data_date(new_date):
    """Update the latest data date and reset notified flag"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    # Check if there's an existing record
    c.execute("SELECT id FROM callofstats_update LIMIT 1")
    if c.fetchone():
        c.execute("UPDATE callofstats_update SET latest_data_date=?, last_checked=?, notified=0", (new_date, now))
    else:
        c.execute("INSERT INTO callofstats_update (latest_data_date, last_checked, notified) VALUES (?, ?, 0)", (new_date, now))
    
    conn.commit()
    conn.close()

def db_mark_update_notified():
    """Mark that we've sent the notification"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE callofstats_update SET notified=1 WHERE id=(SELECT id FROM callofstats_update ORDER BY id DESC LIMIT 1)")
    conn.commit()
    conn.close()

def db_is_update_notified():
    """Check if we've already notified about this update"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT notified FROM callofstats_update ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def db_snapshot_exists(season_id, account_id, data_date):
    """Check if a snapshot already exists for a given date"""
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        c.execute(
            "SELECT id FROM season_progress WHERE season_id=? AND account_id=? AND data_date=?",
            (season_id, account_id, data_date)
        )
        row = c.fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        log_error(f"[DB CHECK] Error checking snapshot: {e}")
        return False

def is_stats_empty(stats):
    """Check if stats are empty/all zeros"""
    if not stats:
        return True
    
    # Check if key stat fields are empty or zero
    key_fields = ["power_gain", "merits", "kills_gain", "lord_name"]
    
    for field in key_fields:
        value = stats.get(field, "")
        if value and value != "+0" and value != "0" and value != "Unknown":
            return False
    
    return True

def db_save_season_progress(season_id, account_id, lord_name, stats, data_date=None):
    """Save a member's progress for a specific date in a season"""
    try:
        if not data_date:
            data_date = date.today().isoformat()
        
        conn = sqlite3.connect(DB_PROGRESS)
        try:
            c = conn.cursor()
            now = datetime.utcnow().isoformat()
            
            c.execute("""
                INSERT OR REPLACE INTO season_progress 
                (season_id, account_id, data_date, lord_name, power_gain, merits, kills_gain, deads_gain, healed_gain,
                 t5_gain, t4_gain, t3_gain, t2_gain, t1_gain,
                 gold_spent, wood_spent, ore_spent, mana_spent,
                 gold_gathered, wood_gathered, ore_gathered, mana_gathered, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                season_id, account_id, data_date, lord_name,
                stats.get("power_gain"), stats.get("merits"), stats.get("kills_gain"), 
                stats.get("deads_gain"), stats.get("healed_gain"),
                stats.get("t5_gain"), stats.get("t4_gain"), stats.get("t3_gain"), 
                stats.get("t2_gain"), stats.get("t1_gain"),
                stats.get("gold_spent"), stats.get("wood_spent"), stats.get("ore_spent"), 
                stats.get("mana_spent"),
                stats.get("gold_gathered"), stats.get("wood_gathered"), stats.get("ore_gathered"), 
                stats.get("mana_gathered"), now
            ))
            conn.commit()
            log_info(f"[DB SAVE] {lord_name} ({account_id}) for {data_date}")
            return True
        finally:
            conn.close()
    except Exception as e:
        log_error(f"[DB SAVE PROGRESS] Error: {e}")
        return False

def db_get_season_progress(season_id, account_id, data_date=None):
    """Get a member's progress for a specific date in a season (defaults to today)"""
    try:
        if not data_date:
            data_date = date.today().isoformat()
        
        conn = sqlite3.connect(DB_PROGRESS)
        try:
            c = conn.cursor()
            c.execute("""
                SELECT power_gain, merits, kills_gain, deads_gain, healed_gain,
                       t5_gain, t4_gain, t3_gain, t2_gain, t1_gain,
                       gold_spent, wood_spent, ore_spent, mana_spent,
                       gold_gathered, wood_gathered, ore_gathered, mana_gathered, lord_name, data_date
                FROM season_progress
                WHERE season_id=? AND account_id=? AND data_date=?
            """, (season_id, account_id, data_date))
            row = c.fetchone()
            
            if not row:
                log_info(f"[DB QUERY] No data: season={season_id}, account={account_id}, date={data_date}")
                return None
            
            # Convert to stats dict format
            stats = {
                "power_gain": row[0],
                "merits": row[1],
                "kills_gain": row[2],
                "deads_gain": row[3],
                "healed_gain": row[4],
                "t5_gain": row[5],
                "t4_gain": row[6],
                "t3_gain": row[7],
                "t2_gain": row[8],
                "t1_gain": row[9],
                "gold_spent": row[10],
                "wood_spent": row[11],
                "ore_spent": row[12],
                "mana_spent": row[13],
                "gold_gathered": row[14],
                "wood_gathered": row[15],
                "ore_gathered": row[16],
                "mana_gathered": row[17],
                "lord_name": row[18],
                "data_date": row[19]
            }
            log_info(f"[DB HIT] {row[18]} ({account_id}) for {data_date}")
            return stats
        finally:
            conn.close()
    except Exception as e:
        log_error(f"[DB GET PROGRESS] Error: {e}")
        return None

def db_get_latest_season_progress(season_id, account_id):
    """Get the latest (most recent date) progress for a member in a season"""
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        try:
            c = conn.cursor()
            c.execute("""
                SELECT power_gain, merits, kills_gain, deads_gain, healed_gain,
                       t5_gain, t4_gain, t3_gain, t2_gain, t1_gain,
                       gold_spent, wood_spent, ore_spent, mana_spent,
                       gold_gathered, wood_gathered, ore_gathered, mana_gathered, lord_name, data_date
                FROM season_progress
                WHERE season_id=? AND account_id=?
                ORDER BY data_date DESC
                LIMIT 1
            """, (season_id, account_id))
            row = c.fetchone()
            
            if not row:
                return None
            
            # Convert to stats dict format
            stats = {
                "power_gain": row[0],
                "merits": row[1],
                "kills_gain": row[2],
                "deads_gain": row[3],
                "healed_gain": row[4],
                "t5_gain": row[5],
                "t4_gain": row[6],
                "t3_gain": row[7],
                "t2_gain": row[8],
                "t1_gain": row[9],
                "gold_spent": row[10],
                "wood_spent": row[11],
                "ore_spent": row[12],
                "mana_spent": row[13],
                "gold_gathered": row[14],
                "wood_gathered": row[15],
                "ore_gathered": row[16],
                "mana_gathered": row[17],
                "lord_name": row[18],
                "data_date": row[19]
            }
            return stats
        finally:
            conn.close()
    except Exception as e:
        log_error(f"[DB GET LATEST PROGRESS] Error: {e}")
        return None

def db_get_lord(account_id):
    try:
        conn = sqlite3.connect(DB)
        try:
            c = conn.cursor()
            c.execute("SELECT id, lord_name, account_id FROM lords WHERE account_id=?", (account_id,))
            row = c.fetchone()
            return row
        finally:
            conn.close()
    except Exception as e:
        log_error(f"[DB GET LORD] Error: {e}")
        return None

# ============================================================
# CALLOFSTATS LOGIN & STATS FETCHING
# ============================================================

# Global session cache
_callofstats_session = None
_session_login_time = None

async def get_callofstats_session():
    """Get or create cached authenticated session"""
    global _callofstats_session, _session_login_time
    
    username = os.getenv("CALLOFSTATS_USERNAME")
    password = os.getenv("CALLOFSTATS_PASSWORD")
    
    if not username or not password:
        log_info("[CALLOFSTATS] Missing credentials in env variables")
        return None
    
    # Reuse session if it exists and is less than 30 minutes old
    if _callofstats_session and _session_login_time:
        age = (datetime.utcnow() - _session_login_time).total_seconds()
        if age < 1800:  # 30 minutes
            log_info(f"[CALLOFSTATS] Reusing cached session (age: {int(age)}s)")
            return _callofstats_session
        else:
            log_info("[CALLOFSTATS] Session expired, creating new one")
            await _callofstats_session.close()
            _callofstats_session = None
    
    # Create new session and login
    try:
        # Create session with timeout
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=10)
        session = aiohttp.ClientSession(timeout=timeout)
        
        log_info("[CALLOFSTATS] Logging in...")
        async with session.post(
            "https://callofstats.com/login",
            data={"username": username, "password": password},
            allow_redirects=True
        ) as resp:
            if resp.status != 200:
                log_info(f"[CALLOFSTATS] Login failed: {resp.status}")
                await session.close()
                return None
            log_info("[CALLOFSTATS] Login successful (session cached)")
        
        _callofstats_session = session
        _session_login_time = datetime.utcnow()
        return session
    except asyncio.TimeoutError:
        log_info("[CALLOFSTATS] Login timed out (30 seconds)")
        return None
    except Exception as e:
        log_info(f"[CALLOFSTATS] Login error: {e}")
        return None

async def fetch_stats(start_date, end_date):
    """Fetch player stats from callofstats"""
    account_id = os.getenv("CALLOFSTATS_ACCOUNT_ID")
    if not account_id:
        log_info("[CALLOFSTATS] Missing CALLOFSTATS_ACCOUNT_ID")
        return None
    
    return await fetch_stats_for_account(account_id, start_date, end_date)

async def fetch_stats_for_account(account_id, start_date, end_date, skip_cache=False):
    """Fetch player stats from callofstats for a specific account (with caching)"""
    global _stats_cache
    
    if not account_id:
        log_info("[CALLOFSTATS] Missing account_id")
        return None
    
    # Check cache first (unless skip_cache=True)
    cache_key = f"{account_id}_{start_date}_{end_date}"
    if not skip_cache and cache_key in _stats_cache:
        cached = _stats_cache[cache_key]
        age = (datetime.utcnow() - cached["timestamp"]).total_seconds()
        if age < CACHE_DURATION:
            log_info(f"[CACHE HIT] Account {account_id} (age: {int(age)}s)")
            return cached["stats"]
        else:
            log_info(f"[CACHE EXPIRED] Account {account_id}, fetching fresh data")
            del _stats_cache[cache_key]
    elif skip_cache:
        log_info(f"[SKIP CACHE] Fetching fresh data for {account_id}")
    
    try:
        # Get cached session (reuses login)
        session = await get_callofstats_session()
        if not session:
            return None
        
        # Format dates properly
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            start_date_formatted = start_dt.strftime("%Y-%m-%d")
            end_date_formatted = end_dt.strftime("%Y-%m-%d")
        except Exception as e:
            start_date_formatted = start_date
            end_date_formatted = end_date
        
        url = f"https://callofstats.com/lord/{account_id}?start_date={start_date_formatted}&end_date={end_date_formatted}"
        log_info(f"[CALLOFSTATS] Fetching: {url}")
        
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status == 200:
                html = await resp.text()
                log_info(f"[CALLOFSTATS] Fetch successful ({len(html)} bytes)")
                stats = parse_stats(html)
                
                # Cache the result (use consistent dict format)
                _stats_cache[cache_key] = {"timestamp": datetime.utcnow(), "stats": stats}
                return stats
            else:
                log_info(f"[CALLOFSTATS] Fetch failed: {resp.status}")
                return None
    except asyncio.TimeoutError:
        log_info("[CALLOFSTATS] Request timed out (30 seconds)")
        return None
    except Exception as e:
        log_info(f"[CALLOFSTATS] Fetch error: {e}")
        return None

def parse_stats(html):
    """Parse stats from HTML using proper HTML parsing"""
    import re
    
    stats = {
        "lord_name": None,
        "power": None,
        "power_gain": None,
        "merits": None,
        "merits_pct": None,
        "kills_gain": None,
        "deads_gain": None,
        "healed_gain": None,
        "t5_gain": None,
        "t4_gain": None,
        "t3_gain": None,
        "t2_gain": None,
        "t1_gain": None,
        "gold_spent": None,
        "wood_spent": None,
        "ore_spent": None,
        "mana_spent": None,
        "rss_spent_total": None,
        "gold_gathered": None,
        "wood_gathered": None,
        "ore_gathered": None,
        "mana_gathered": None,
        "rss_gathered_total": None
    }
    
    try:
        def find_stat_value(label_name):
            """Find value for a stat by its label using HTML structure"""
            # Look for: <span class="subtle">LABEL</span> ... <div class="value">VALUE</div>
            pattern = f'<span class="subtle">{re.escape(label_name)}</span>\\s*<div class="value">([^<]+)</div>'
            match = re.search(pattern, html)
            if match:
                return match.group(1).strip()
            return None
        
        # Extract lord name - look for <h1 class="higher-value">NAME</h1>
        name_match = re.search(r'<h1 class="higher-value">([^<]+)</h1>', html)
        if name_match:
            stats["lord_name"] = name_match.group(1).strip()
        
        # Power stats
        stats["power_gain"] = find_stat_value("Highest Power")
        
        # Merits
        stats["merits"] = find_stat_value("Merits")
        stats["merits_pct"] = find_stat_value("Merit to Power Ratio")
        
        # War stats
        stats["kills_gain"] = find_stat_value("Units Killed")
        stats["deads_gain"] = find_stat_value("Units Dead")
        stats["healed_gain"] = find_stat_value("Units Healed")
        
        # Tiered Kills
        stats["t5_gain"] = find_stat_value("T5 Kills")
        stats["t4_gain"] = find_stat_value("T4 Kills")
        stats["t3_gain"] = find_stat_value("T3 Kills")
        stats["t2_gain"] = find_stat_value("T2 Kills")
        stats["t1_gain"] = find_stat_value("T1 Kills")
        
        # Resources Gathered
        stats["gold_gathered"] = find_stat_value("Gold Gathered")
        stats["wood_gathered"] = find_stat_value("Wood Gathered")
        stats["ore_gathered"] = find_stat_value("Ore Gathered")
        stats["mana_gathered"] = find_stat_value("Mana Gathered")
        
        # Resources Spent
        stats["gold_spent"] = find_stat_value("Gold Spent")
        stats["wood_spent"] = find_stat_value("Wood Spent")
        stats["ore_spent"] = find_stat_value("Ore Spent")
        stats["mana_spent"] = find_stat_value("Mana Spent")
        
        found_count = len([v for v in stats.values() if v])
        log_info(f"[PARSE] Successfully parsed stats: {found_count} fields found")
        log_info(f"[PARSE] Lord name: {stats['lord_name']}")
        return stats
    except Exception as e:
        log_info(f"[PARSE STATS] Error: {e}")
        return None

# ============================================================
# DEFAULT ABYSS CONFIG
# ============================================================

DEFAULT_ABYSS = {
    "days": [1, 4, 6],
    "hours": [0, 4, 8, 12, 16, 20],
    "reminder_hours": [0, 4, 8, 12, 16, 20],
    "round2": True
}

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
# DISCORD BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.active_edit = None

# ============================================================
# BACKUP SLASH COMMANDS (OWNER ONLY)
# ============================================================

@bot.tree.command(name="backup", description="List recent backups")
async def backup(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
        reverse=True
    )

    if not files:
        return await inter.response.send_message("📦 No backups found.", ephemeral=True)

    msg = "**📦 Recent Backups:**\n" + "\n".join(
        f"- `{f}`" for f in files[:MAX_BACKUPS]
    )
    await inter.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="forcebackup", description="Create a backup now")
async def forcebackup(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    make_backup()
    await inter.response.send_message("✅ Backup created.", ephemeral=True)

@bot.tree.command(name="restorebackup", description="Restore a backup")
async def restorebackup(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
        reverse=True
    )

    if not files:
        return await inter.response.send_message("❌ No backups found.", ephemeral=True)

    await inter.response.defer(ephemeral=True)  # ✅ CRITICAL

    select = Select(
        placeholder="Select a backup to restore",
        options=[discord.SelectOption(label=f, value=f) for f in files]
    )

    async def cb(i):
        await i.response.defer(ephemeral=True)

        path = os.path.join(BACKUP_DIR, select.values[0])

        with zipfile.ZipFile(path, "r") as z:
            z.extractall(".")

        await i.followup.send(
            f"♻️ Restored `{select.values[0]}`. Restarting bot...",
            ephemeral=True
        )

        await asyncio.sleep(2)
       # auto-restart on Koyeb

    select.callback = cb
    view = View(timeout=60)
    view.add_item(select)

    await inter.followup.send("Choose a backup to restore:", view=view, ephemeral=True)

# ============================================================
# ON READY
# ============================================================


async def force_refresh_all_stats():
    """
    Force-fetch and cache all members' stats for current season.
    Called when Call of Stats update is detected.
    Saves progress to database for future !oldprogress queries.
    """
    try:
        season = db_get_current_season()
        if not season:
            log_info("[CACHE REFRESH] No active season")
            return
        
        season_id, season_name, start_date, created_at = season
        today = date.today().isoformat()
        
        guild = bot.get_guild(bot.guilds[0].id) if bot.guilds else None
        if not guild:
            log_info("[CACHE REFRESH] No guild found")
            return
        
        lords = get_all_lords_from_guild(guild)
        accounts_to_refresh = []
        
        # Add lords from guild roles
        for lord in lords:
            accounts_to_refresh.append(lord["account_id"])
        
        # Add mapped accounts (like Havi)
        for discord_id, account_id in DISCORD_TO_ACCOUNT_ID.items():
            accounts_to_refresh.append(account_id)
        
        log_info(f"[CACHE REFRESH] Starting bulk refresh for {len(accounts_to_refresh)} members")
        
        # Fetch and cache stats for each member
        count = 0
        for account_id in accounts_to_refresh:
            try:
                # Fetch today's stats (will fallback if needed)
                stats_today, actual_date_today = await fetch_stats_with_fallback(account_id, start_date, today)
                
                if stats_today:
                    # Cache today's stats (in-memory)
                    set_cached_stats(account_id, start_date, today, stats_today)
                    log_info(f"[FORCEFETCH] Cached today {account_id} for {today}")
                    
                    # SAVE to database with actual date (handles missed dates like 24/03)
                    db_save_season_progress(season_id, account_id, stats_today.get("lord_name", account_id), stats_today, actual_date_today)
                    log_info(f"[FORCEFETCH] Saved today {account_id} for {actual_date_today}")
                    
                    # Also cache the day before for comparisons
                    day_before = (datetime.strptime(actual_date_today, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
                    stats_yesterday, actual_date_yesterday = await fetch_stats_with_fallback(account_id, start_date, day_before)
                    
                    if stats_yesterday:
                        set_cached_stats(account_id, start_date, day_before, stats_yesterday)
                        log_info(f"[FORCEFETCH] Cached yesterday {account_id} for {day_before} (actual: {actual_date_yesterday})")
                        
                        # Also save yesterday to database
                        db_save_season_progress(season_id, account_id, stats_yesterday.get("lord_name", account_id), stats_yesterday, actual_date_yesterday)
                        log_info(f"[FORCEFETCH] Saved yesterday {account_id} for {actual_date_yesterday}")
                    else:
                        log_info(f"[FORCEFETCH] ⚠️ No yesterday data for {account_id} (tried {day_before})")
                    
                    count += 1
            except Exception as e:
                log_error(f"[CACHE REFRESH] Error for {account_id}: {e}")
                continue
        
        log_info(f"[CACHE REFRESH] Complete! Cached & saved {count}/{len(accounts_to_refresh)} members to database")
    except Exception as e:
        log_error(f"[CACHE REFRESH ERROR] {e}")


@tasks.loop(minutes=1)
async def check_callofstats_update():
    """
    Check every 5 minutes if new Call of Stats data is available
    Only notify if the date changed AND actual data exists for new date
    """
    try:
        # Always check Rekz's profile for latest data
        account_id = REKZ_ACCOUNT_ID
        
        # Fetch latest data date from website
        latest_date = await fetch_latest_data_date(account_id)
        if not latest_date:
            log_info(f"[CALLOFSTATS UPDATE] Could not fetch latest date")
            return
        
        # Get last known date
        last_known = db_get_last_known_data_date()
        
        # If date changed, verify actual data exists before notifying
        if last_known != latest_date:
            log_info(f"[CALLOFSTATS UPDATE] Date changed {last_known} -> {latest_date}, verifying data exists...")
            
            # Try to fetch stats for the new date to verify it exists
            # Convert DD/MM/YYYY to YYYY-MM-DD for the query
            from datetime import datetime
            try:
                date_obj = datetime.strptime(latest_date, "%d/%m/%Y")
                new_date_iso = date_obj.strftime("%Y-%m-%d")
                
                # Fetch season start date
                season = db_get_current_season()
                if not season:
                    log_info(f"[CALLOFSTATS UPDATE] No active season")
                    return
                season_id, season_name, start_date, created_at = season
                
                # Try to fetch stats for the new date
                test_stats = await fetch_stats_for_account(account_id, start_date, new_date_iso, skip_cache=True)
                
                # Verify we got valid data (not empty/unknown)
                if not test_stats or test_stats.get("lord_name") == "Unknown":
                    log_info(f"[CALLOFSTATS UPDATE] No actual data for {new_date_iso} yet (stats missing), skipping notification")
                    return
                
                # STRICT verification: check MULTIPLE stats to confirm NEW data is ready
                # Not just one stat - need at least 2+ stats with real values
                real_stat_count = 0
                for stat_key in ["power_gain", "merits", "kills_gain", "deads_gain", "healed_gain"]:
                    stat_val = test_stats.get(stat_key, "0")
                    try:
                        num_val = int(str(stat_val).replace("+", "").replace(",", "") or 0)
                        if num_val > 0:
                            real_stat_count += 1
                            log_info(f"[CALLOFSTATS UPDATE] Verified stat: {stat_key}={num_val}")
                    except:
                        pass
                
                # Require AT LEAST 2 stats with real values (not just 1)
                # This prevents false positives from cached/placeholder data
                if real_stat_count < 2:
                    log_info(f"[CALLOFSTATS UPDATE] ⚠️ Only {real_stat_count} stat(s) with data for {new_date_iso} - data not ready yet, skipping notification")
                    return
                
                log_info(f"[CALLOFSTATS UPDATE] ✅ Verified {real_stat_count} stats for {new_date_iso} - data is real!")
                
            except Exception as e:
                log_info(f"[CALLOFSTATS UPDATE] Error verifying data: {e}")
                return
            
            # Update database
            db_update_data_date(latest_date)
            
            # IMMEDIATELY refresh cache with new data
            log_info(f"[CALLOFSTATS UPDATE] Triggering cache refresh...")
            await force_refresh_all_stats()
            
            # Send notification
            try:
                guild = bot.get_guild(bot.guilds[0].id) if bot.guilds else None
                if guild:
                    update_channel = guild.get_channel(BACKUP_CHANNEL_ID)
                    if update_channel:
                        embed = discord.Embed(
                            title="🔄 Call of Stats Update",
                            description=f"<@{OWNER_ID}> New data for **{latest_date}** cached and ready!",
                            color=0x00FF00
                        )
                        embed.set_footer(text="Cache refreshed ✅")
                        await update_channel.send(embed=embed)
                        
                        # Also mark as notified
                        db_mark_update_notified()
                        log_info(f"[CALLOFSTATS UPDATE] Notification sent to channel {BACKUP_CHANNEL_ID}")
            except Exception as e:
                log_info(f"[CALLOFSTATS UPDATE CHANNEL ERROR] {e}")
    except Exception as e:
        log_info(f"[CALLOFSTATS UPDATE ERROR] {e}")
        import traceback
        traceback.print_exc()

@tasks.loop(minutes=5)
async def self_ping():
    try:
        url = os.getenv("KOYEB_PUBLIC_URL")
        if not url:
            return

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                pass
    except Exception as e:
        log_info("[Self Ping Error]", e)

def preload_cache_from_db():
    """Load all recent season data from database into cache on bot startup"""
    try:
        season = db_get_current_season()
        if not season:
            log_info("[PRELOAD] No active season")
            return
        
        season_id, season_name, start_date, created_at = season
        
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        
        # Get all unique account_ids and dates in the current season
        c.execute("""
            SELECT DISTINCT account_id, data_date
            FROM season_progress
            WHERE season_id = ?
            ORDER BY data_date DESC
            LIMIT 200
        """, (season_id,))
        
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            log_info("[PRELOAD] No data found in database")
            return
        
        # Load each into cache
        count = 0
        for account_id, data_date in rows:
            stats = db_get_season_progress(season_id, account_id, data_date)
            if stats:
                set_cached_stats(account_id, start_date, data_date, stats)
                count += 1
        
        log_info(f"[PRELOAD] Loaded {count} entries into cache from database")
    except Exception as e:
        log_error(f"[PRELOAD ERROR] {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Set bot status/activity
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="Abyss events ⚔️"
    )
    await bot.change_presence(activity=activity)

    # Sync commands once
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Command sync failed: {e}")
    
    # Pre-load cache from database on startup (so commands work immediately)
    preload_cache_from_db()

    # ✅ START SELF-PING (CRITICAL)
    if not self_ping.is_running():
        self_ping.start()

    # ✅ CHECK CALLOFSTATS UPDATES
    if not check_callofstats_update.is_running():
        check_callofstats_update.start()

    # ✅ SAFE LOOP STARTS
    if not abyss_reminder_loop.is_running():
        abyss_reminder_loop.start()

    if not custom_event_loop.is_running():
        custom_event_loop.start()

    ch = bot.get_channel(update_channel_id)
    if ch:
        await ch.send("🤖 Bot restarted successfully.")


# ============================================================
# HELP COMMAND
# ============================================================

@bot.tree.command(name="help", description="Show all available commands")
async def help_cmd(inter):
    embed = discord.Embed(
        title="📖 Bot Commands",
        description="All available commands for Abyss management and season tracking",
        color=0x3498db
    )
    
    embed.add_field(
        name="📊 Season Stats Commands (use ! prefix)",
        value="`!progress [user]` - Full season stats (e.g., !progress or !progress rekz)\n`!oldprogress [user]` - View past season stats\n`!q [user]` - Quick one-liner stats\n`!compare lord1 lord2` - Compare two players\n`!gains [season] [user]` - View gains (e.g., !gains | !gains sos1 | !gains rekz | !gains sos1 rekz)\n`!topmana [season]` - Top mana gathered (e.g., !topmana or !topmana sos1)\n`!topdeaths [season]` - Most deaths (e.g., !topdeaths sos2)\n`!topmerits [season]` - Highest merits (e.g., !topmerits sos1)\n`!rss [season]` - Top resource spenders (e.g., !rss or !rss sos1)\n`!active` - Active vs inactive members",
        inline=False
    )
    
    embed.add_field(
        name="📈 Advanced Gains (with Autocomplete)",
        value="`/gain start_date end_date [user]` - View gains with date autocomplete! (e.g., `/gain 2025-12-01 2026-03-31 rekz`)",
        inline=False
    )
    
    embed.add_field(
        name="📚 Historical Data Commands",
        value="`!seasonhistory` - View all seasons with dates (name, start → end)\n`!datahistory` - Show oldest/newest saved dates\n\n**Note:** All commands above support `[season]` parameter to view specific season data!",
        inline=False
    )
    
    embed.add_field(
        name="👤 Role Management",
        value="`/addrole` - Get Abyss reminders\n`/removerole` - Stop Abyss reminders",
        inline=False
    )
    
    embed.add_field(
        name="📅 Events",
        value="`/weeklyevent` - Show current weekly events\n`/kvkevent` - Show custom events",
        inline=False
    )
    
    if inter.user.id == OWNER_ID:
        embed.add_field(
            name="⚙️ Admin Commands (Owner Only)",
            value="`/newseason` - Start a new season\n`/addevent` - Add custom event\n`/editevent` - Edit event\n`/removeevent` - Delete event\n`/abyssconfig` - Configure Abyss settings\n`/testdm` - Test DM system\n`/backup` - List database backups\n`/forcebackup` - Create backup now\n`!forcefetch` - Fetch latest stats immediately\n`!loadhistory` - Load season data from season start\n`!loadhistory all` - Load all Call of Stats data (auto-detects oldest date)\n`!datahistory` - Show oldest/newest data range in database\n`!cleanupempty` - Scan and delete empty/zero-data snapshots",
            inline=False
        )
    
    embed.set_footer(text="Use / to see all slash commands | Use ! for text commands")
    await inter.response.send_message(embed=embed, ephemeral=True)


# Autocomplete for dates
async def date_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete dates from database"""
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        c.execute("SELECT DISTINCT data_date FROM season_progress ORDER BY data_date DESC")
        all_dates = [row[0] for row in c.fetchall()]
        conn.close()
        
        # Filter dates that start with current input
        filtered = [d for d in all_dates if d.startswith(current.lower())] if current else all_dates[:25]
        
        # Return top 25 matches
        return [
            app_commands.Choice(name=date, value=date)
            for date in filtered[:25]
        ]
    except Exception as e:
        log_error(f"[AUTOCOMPLETE] Error: {e}")
        return []


# ============================================================
# SEASON TRACKING COMMANDS
# ============================================================

class NewSeasonModal(Modal, title="📅 New Season"):
    season_name = TextInput(
        label="Season Name",
        placeholder="e.g., S053, Season 5, Spring 2026"
    )
    start_date = TextInput(
        label="Start Date (YYYY-MM-DD)",
        placeholder="2025-12-01"
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Validate date format
            start_dt = datetime.strptime(self.start_date.value.strip(), "%Y-%m-%d")
            
            # Store season
            db_add_season(self.season_name.value.strip(), self.start_date.value.strip())
            
            await interaction.followup.send(
                f"✅ **Season Started!**\n"
                f"**Name:** {self.season_name.value}\n"
                f"**Start Date:** {self.start_date.value}\n\n"
                f"Use `!progress` to check your season stats!",
                ephemeral=True
            )
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid date format. Use YYYY-MM-DD (e.g., 2025-12-01)",
                ephemeral=True
            )
        except Exception as e:
            log_info(f"[NEW SEASON ERROR] {e}")
            await interaction.followup.send(
                "❌ Failed to create season.",
                ephemeral=True
            )

@bot.tree.command(name="newseason", description="Start a new season and track progress")
async def newseason(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    await inter.response.send_modal(NewSeasonModal())


@bot.command(name="progress")
async def progress(ctx, user_input: str = None, season_input: str = None):
    """
    Check season progress. 
    Usage: 
      !progress               (your progress, current season)
      !progress truvix        (truvix's progress, current season)
      !progress truvix sos1   (truvix's progress in sos1 season)
      !progress 16322115 sos2 (account 16322115's progress in sos2)
    """
    # Determine which season to use
    if season_input:
        # Look up specific season by name
        try:
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("SELECT id, season_name, start_date, created_at FROM seasons WHERE LOWER(season_name) = LOWER(?)", (season_input,))
            season = c.fetchone()
            conn.close()
            
            if not season:
                return await ctx.send(f"❌ Season '{season_input}' not found. Use `!seasonhistory` to see all seasons.")
        except Exception as e:
            return await ctx.send(f"❌ Error looking up season: {e}")
    else:
        # Use current season
        season = db_get_current_season()
        
        if not season:
            return await ctx.send("❌ No season active. Use `/newseason` to start one.")
    
    account_id = None
    
    # If no input provided, find from user's numeric role
    if not user_input:
        for role in ctx.author.roles:
            if role.name.isdigit():
                account_id = role.name
                break
        
        if not account_id:
            return await ctx.send("❌ You don't have a numeric role with your account ID.\nAsk the owner to give you a role with your account ID number (e.g., role name: `16322115`).\n\nOr use: `!progress truvix` or `!progress 16322115`")
    
    # If input is numeric, use as account ID
    elif user_input.isdigit():
        account_id = user_input
    
    # If input is text, check username lookup
    else:
        username_lower = user_input.lower()
        found_discord_id = None
        
        # Check if username exists in mapping
        for username, discord_id in USERNAME_TO_DISCORD_ID.items():
            if username.lower() == username_lower:
                found_discord_id = discord_id
                break
        
        if not found_discord_id:
            return await ctx.send(f"❌ Username '{user_input}' not found. Available usernames: {', '.join(USERNAME_TO_DISCORD_ID.keys())}")
        
        # Get the member from guild and find their numeric role
        try:
            member = ctx.guild.get_member(found_discord_id)
            if not member:
                return await ctx.send(f"❌ User '{user_input}' is not in this server.")
            
            for role in member.roles:
                if role.name.isdigit():
                    account_id = role.name
                    break
            
            if not account_id:
                return await ctx.send(f"❌ User '{user_input}' doesn't have a numeric role with their account ID.")
        except Exception as e:
            log_info(f"[PROGRESS USERNAME ERROR] {e}")
            return await ctx.send(f"❌ Error looking up user '{user_input}'")
    
    season_id, season_name, start_date, created_at = season
    
    msg = await ctx.send(f"📊 Fetching stats for account {account_id} in season {season_name}...")
    
    today = date.today().isoformat()
    
    try:
        # FIRST: Try database for today
        stats = db_get_season_progress(season_id, account_id, today)
        
        # If not today, try yesterday
        if not stats:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            stats = db_get_season_progress(season_id, account_id, yesterday)
        
        # FALLBACK: Check cache
        if not stats:
            stats = get_cached_stats(account_id, start_date, today)
        
        # FALLBACK 2: Fetch from API (for unlisted people)
        if not stats:
            log_info(f"[PROGRESS] {account_id} not in DB, fetching from API")
            stats, end_date_used = await fetch_stats_with_fallback(account_id, start_date, today)
        else:
            end_date_used = stats.get("data_date", today)
        
        if not stats:
            return await msg.edit(content="❌ Failed to fetch stats. Call of Stats may not have released data yet.")
        
        # Get highest power from normal profile (only if not in database)
        highest_power = await fetch_highest_power(account_id)
        
        # Get current T-kills from normal profile (only if not in database)
        current_t_kills = await fetch_current_t_kills(account_id)
        
        # Calculate merit to power ratio using highest power and merits
        if stats.get("merits") and highest_power:
            try:
                merits_str = stats["merits"].replace("+", "").replace(",", "")
                merits_val = int(merits_str) if merits_str.isdigit() else 0
                
                # Calculate ratio: (Merits / Highest Power) × 100
                if highest_power > 0:
                    ratio = (merits_val / highest_power) * 100
                    stats["merits_pct"] = f"{ratio:.1f}%"
                else:
                    stats["merits_pct"] = "0%"
            except Exception as e:
                stats["merits_pct"] = "0%"
        else:
            stats["merits_pct"] = "0%"
        
        # Debug: log what we parsed
        log_info(f"[PROGRESS] Parsed stats: {stats}")
        log_info(f"[PROGRESS] Highest power: {highest_power}")
        log_info(f"[PROGRESS] Merit ratio: {stats.get('merits_pct')}")
        log_info(f"[PROGRESS] Current T-kills: {current_t_kills}")
        
        # Get rankings for all stats
        power_rank = await get_rankings_for_stat(ctx, "power_gain", start_date, end_date_used)
        merits_rank = await get_rankings_for_stat(ctx, "merits", start_date, end_date_used)
        kills_rank = await get_rankings_for_stat(ctx, "kills_gain", start_date, end_date_used)
        deads_rank = await get_rankings_for_stat(ctx, "deads_gain", start_date, end_date_used)
        healed_rank = await get_rankings_for_stat(ctx, "healed_gain", start_date, end_date_used)
        
        # Calculate power_gain
        power_gain = 0
        if stats["power_gain"]:
            power_gain_str = stats["power_gain"].replace("+", "")
            try:
                power_gain = int(power_gain_str.replace(",", ""))
            except Exception as e:
                power_gain = 0
        
        # Build ranking strings
        power_rank_str = f" (#{power_rank[account_id][0]})" if account_id in power_rank else ""
        merits_rank_str = f" (#{merits_rank[account_id][0]})" if account_id in merits_rank else ""
        kills_rank_str = f" (#{kills_rank[account_id][0]})" if account_id in kills_rank else ""
        deads_rank_str = f" (#{deads_rank[account_id][0]})" if account_id in deads_rank else ""
        healed_rank_str = f" (#{healed_rank[account_id][0]})" if account_id in healed_rank else ""
        
        
        # Calculate totals for RSS
        total_spent = 0
        total_gathered = 0
        
        for key in ["gold_spent", "wood_spent", "ore_spent", "mana_spent"]:
            val_str = stats.get(key, "+0").replace(",", "").replace("+", "")
            try:
                total_spent += abs(int(val_str)) if val_str.lstrip("-").isdigit() else 0
            except Exception as e:
                pass
        
        for key in ["gold_gathered", "wood_gathered", "ore_gathered", "mana_gathered"]:
            val_str = stats.get(key, "+0").replace(",", "").replace("+", "")
            try:
                total_gathered += abs(int(val_str)) if val_str.lstrip("-").isdigit() else 0
            except Exception as e:
                pass
        
        # Build text output - MATCH REFERENCE FORMAT
        lord_name = stats.get("lord_name", "Unknown")
        output = f"```✅ Progress Report for {lord_name} for season {season_name}\n"
        output += f"\n"  # Line break before Power
        
        # Power - with highest power + season gain on ONE line
        if highest_power or power_gain:
            output += f"⚡ Power "
            if highest_power and power_gain:
                output += f"{highest_power:,} (+{power_gain:,}){power_rank_str}\n"
            elif highest_power:
                output += f"{highest_power:,}{power_rank_str}\n"
            elif power_gain:
                output += f"{power_gain}{power_rank_str}\n"
        
        # Merits - with ranking on ONE line
        if stats.get("merits"):
            merits_display = f"{stats['merits']}"
            if stats.get("merits_pct"):
                merits_display += f" ({stats['merits_pct']})"
            output += f"🏅 Merits {merits_display}{merits_rank_str}\n"
        
        output += f"\n"
        
        # Kills - one line
        if stats.get("kills_gain"):
            output += f"⚔️ Kills {stats['kills_gain']}{kills_rank_str}\n"
        
        # Deaths - one line
        if stats.get("deads_gain"):
            output += f"💀 Deaths {stats['deads_gain']}{deads_rank_str}\n"
        
        # Healed - one line
        if stats.get("healed_gain"):
            output += f"❤️ Healed {stats['healed_gain']}{healed_rank_str}\n"
        
        output += f"\n"
        
        # Kill Breakdown - show current total + season gain
        output += f"⚔️ Kill Breakdown\n"
        
        # Calculate total kills (current + gains)
        total_t_current = 0
        total_t_gain = 0
        
        if stats.get("t5_gain"):
            t5_current = current_t_kills.get("t5")
            t5_gain_clean = stats['t5_gain'].replace("+", "").replace(",", "")
            t5_gain_val = abs(int(t5_gain_clean)) if t5_gain_clean.lstrip("-").isdigit() else 0
            if t5_current:
                output += f"T5: {t5_current:,} (+{t5_gain_val:,})\n"
                total_t_current += t5_current
            else:
                output += f"T5: +{t5_gain_val:,}\n"
            total_t_gain += t5_gain_val
        
        if stats.get("t4_gain"):
            t4_current = current_t_kills.get("t4")
            t4_gain_clean = stats['t4_gain'].replace("+", "").replace(",", "")
            t4_gain_val = abs(int(t4_gain_clean)) if t4_gain_clean.lstrip("-").isdigit() else 0
            if t4_current:
                output += f"T4: {t4_current:,} (+{t4_gain_val:,})\n"
                total_t_current += t4_current
            else:
                output += f"T4: +{t4_gain_val:,}\n"
            total_t_gain += t4_gain_val
        
        if stats.get("t3_gain"):
            t3_current = current_t_kills.get("t3")
            t3_gain_clean = stats['t3_gain'].replace("+", "").replace(",", "")
            t3_gain_val = abs(int(t3_gain_clean)) if t3_gain_clean.lstrip("-").isdigit() else 0
            if t3_current:
                output += f"T3: {t3_current:,} (+{t3_gain_val:,})\n"
                total_t_current += t3_current
            else:
                output += f"T3: +{t3_gain_val:,}\n"
            total_t_gain += t3_gain_val
        
        if stats.get("t2_gain"):
            t2_current = current_t_kills.get("t2")
            t2_gain_clean = stats['t2_gain'].replace("+", "").replace(",", "")
            t2_gain_val = abs(int(t2_gain_clean)) if t2_gain_clean.lstrip("-").isdigit() else 0
            if t2_current:
                output += f"T2: {t2_current:,} (+{t2_gain_val:,})\n"
                total_t_current += t2_current
            else:
                output += f"T2: +{t2_gain_val:,}\n"
            total_t_gain += t2_gain_val
        
        if stats.get("t1_gain"):
            t1_current = current_t_kills.get("t1")
            t1_gain_clean = stats['t1_gain'].replace("+", "").replace(",", "")
            t1_gain_val = abs(int(t1_gain_clean)) if t1_gain_clean.lstrip("-").isdigit() else 0
            if t1_current:
                output += f"T1: {t1_current:,} (+{t1_gain_val:,})\n"
                total_t_current += t1_current
            else:
                output += f"T1: +{t1_gain_val:,}\n"
            total_t_gain += t1_gain_val
        
        # Add total T-kills
        if total_t_current > 0:
            output += f"Total: {total_t_current:,} (+{total_t_gain:,})\n"
        elif total_t_gain > 0:
            output += f"Total: +{total_t_gain:,}\n"
        
        output += f"\n"
        
        # RSS Spent - each resource on own line with absolute values
        output += f"💰 RSS Spent\n"
        if stats.get("gold_spent"):
            gold_clean = stats['gold_spent'].replace(",", "").replace("+", "")
            gold_val = abs(int(gold_clean)) if gold_clean.lstrip("-").isdigit() else 0
            output += f"🪙 Gold: -{gold_val:,}\n"
        if stats.get("wood_spent"):
            wood_clean = stats['wood_spent'].replace(",", "").replace("+", "")
            wood_val = abs(int(wood_clean)) if wood_clean.lstrip("-").isdigit() else 0
            output += f"🪵 Wood: -{wood_val:,}\n"
        if stats.get("ore_spent"):
            ore_clean = stats['ore_spent'].replace(",", "").replace("+", "")
            ore_val = abs(int(ore_clean)) if ore_clean.lstrip("-").isdigit() else 0
            output += f"⛏️ Ore: -{ore_val:,}\n"
        if stats.get("mana_spent"):
            mana_clean = stats['mana_spent'].replace(",", "").replace("+", "")
            mana_val = abs(int(mana_clean)) if mana_clean.lstrip("-").isdigit() else 0
            output += f"💧 Mana: -{mana_val:,}\n"
        output += f"Total: -{total_spent:,}\n"
        output += f"\n"
        
        # RSS Gathered - each resource on own line
        output += f"👨‍🌾 RSS Gathered\n"
        if stats.get("gold_gathered"):
            output += f"🪙 Gold: {stats['gold_gathered']}\n"
        if stats.get("wood_gathered"):
            output += f"🪵 Wood: {stats['wood_gathered']}\n"
        if stats.get("ore_gathered"):
            output += f"⛏️ Ore: {stats['ore_gathered']}\n"
        if stats.get("mana_gathered"):
            output += f"💧 Mana: {stats['mana_gathered']}\n"
        output += f"Total: {total_gathered:,}\n"
        output += f"\n"
        
        # Timespan
        output += f"📅 Timespan: {start_date} → {end_date_used}```"
        
        await msg.edit(content=output)
        
    except Exception as e:
        log_info(f"[PROGRESS ERROR] {e}")
        await msg.edit(content=f"❌ Error: {str(e)}")




@bot.tree.command(name="addlord", description="[DEPRECATED] Use numeric roles instead")
async def addlord_deprecated(inter: discord.Interaction):
    """Deprecated - use numeric roles instead"""
    await inter.response.send_message(
        "❌ `/addlord` is deprecated!\n\n"
        "Instead, create a Discord role with your account ID as the name (e.g., `16322115`)\n"
        "The bot will auto-detect all numeric roles!\n\n"
        "Use `/forcefetch` to fetch everyone's stats.",
        ephemeral=True
    )


@bot.command(name="oldprogress")
async def oldprogress(ctx, user_input: str = None):
    """View progress from past seasons. Shows season selector."""
    
    # Get all seasons
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, season_name, start_date FROM seasons ORDER BY created_at DESC")
    seasons = c.fetchall()
    conn.close()
    
    if not seasons:
        return await ctx.send("❌ No seasons found.")
    
    if len(seasons) == 1:
        return await ctx.send("❌ Only one season exists. Use `!progress` for current season.")
    
    # Get account ID
    account_id = None
    
    if not user_input:
        for role in ctx.author.roles:
            if role.name.isdigit():
                account_id = role.name
                break
        if not account_id:
            return await ctx.send("❌ You don't have a numeric role. Ask the owner to give you one.")
    elif user_input.isdigit():
        account_id = user_input
    else:
        username_lower = user_input.lower()
        for username, discord_id in USERNAME_TO_DISCORD_ID.items():
            if username.lower() == username_lower:
                try:
                    member = ctx.guild.get_member(discord_id)
                    if member:
                        for role in member.roles:
                            if role.name.isdigit():
                                account_id = role.name
                                break
                except Exception as e:
                    pass
                break
        if not account_id:
            return await ctx.send(f"❌ Could not find account ID for '{user_input}'")
    
    if not account_id:
        return await ctx.send("❌ Could not determine account ID.")
    
    # Create select menu with seasons (excluding current season)
    class SeasonSelect(discord.ui.Select):
        def __init__(self, seasons, account_id, ctx):
            self.seasons = seasons
            self.account_id = account_id
            self.ctx = ctx
            
            options = []
            for i, (season_id, season_name, start_date) in enumerate(seasons[:-1]):  # Exclude current (latest)
                options.append(discord.SelectOption(label=season_name, value=str(season_id)))
            
            if not options:
                options.append(discord.SelectOption(label="No past seasons", value="none"))
            
            super().__init__(placeholder="Choose a season...", options=options, min_values=1, max_values=1)
        
        async def callback(self, interaction: discord.Interaction):
            if self.values[0] == "none":
                await interaction.response.defer()
                return
            
            season_id = int(self.values[0])
            
            # Find season
            season = None
            for s in self.seasons:
                if s[0] == season_id:
                    season = s
                    break
            
            if not season:
                await interaction.response.send_message("❌ Season not found.", ephemeral=True)
                return
            
            season_id, season_name, start_date = season
            
            # Find next season's start date to know end date
            end_date = None
            for s in self.seasons:
                if s[0] != season_id:
                    # If this season is older, find next newer season
                    conn = sqlite3.connect(DB)
                    c = conn.cursor()
                    c.execute("SELECT start_date FROM seasons WHERE id=? LIMIT 1", (season_id,))
                    season_start = c.fetchone()
                    c.execute("SELECT start_date FROM seasons WHERE start_date > ? ORDER BY start_date ASC LIMIT 1", (season_start[0] if season_start else "2000-01-01",))
                    next_season = c.fetchone()
                    conn.close()
                    
                    if next_season:
                        end_date = next_season[0]
                    break
            
            # If no next season, use today
            if not end_date:
                end_date = date.today().isoformat()
            
            await interaction.response.defer()
            
            # Get latest stats from database for past season (no API calls, no dates needed)
            stats = db_get_latest_season_progress(season_id, self.account_id)
            
            if not stats:
                await interaction.followup.send(f"❌ No data found in database for this season.\n**Note:** Data is only saved for members in our tracking list. If you're a new member, ask the owner to add you!")
                return
            
            if stats.get("lord_name") == "Unknown":
                await interaction.followup.send("❌ Failed to fetch stats for this season.")
                return
            
            # Get highest power and T-kills
            power = await fetch_highest_power(self.account_id)
            t_kills = await fetch_current_t_kills(self.account_id)
            
            # Build output
            lord_name = stats.get("lord_name", "Unknown")
            output = f"```✅ Progress Report for {lord_name} for season {season_name}\n\n"
            
            # Power
            if power:
                power_gain = 0
                if stats.get("power_gain"):
                    try:
                        pg_str = stats.get("power_gain", "+0").replace("+", "").replace(",", "")
                        power_gain = int(pg_str)
                    except Exception as e:
                        power_gain = 0
                
                output += f"⚡ Power {power:,} (+{power_gain:,})\n\n"
            
            # Merits
            merits = stats.get("merits", "+0")
            merits_pct = stats.get("merits_pct", "0%")
            output += f"🏅 Merits {merits} ({merits_pct})\n\n"
            
            # Deaths, Healed, Kills
            deaths = stats.get("deads_gain", "+0")
            healed = stats.get("healed_gain", "+0")
            kills = stats.get("kills_gain", "+0")
            total_t = sum(t_kills.values()) if t_kills else 0
            
            output += f"💀 Deaths\n{deaths}\n\n"
            output += f"❤️ Healed\n{healed}\n\n"
            output += f"⚔️ Kills\n{total_t:,} ({kills})\n\n"
            
            # T-Tier
            t5 = t_kills.get("t5", 0)
            t4 = t_kills.get("t4", 0)
            t3 = t_kills.get("t3", 0)
            t2 = t_kills.get("t2", 0)
            t1 = t_kills.get("t1", 0)
            
            output += f"T5 Kills: {t5:,}\n"
            output += f"T4 Kills: {t4:,}\n"
            output += f"T3 Kills: {t3:,}\n"
            output += f"T2 Kills: {t2:,}\n"
            output += f"T1 Kills: {t1:,}\n\n"
            
            # Mana
            mana = stats.get("mana_gathered", "+0")
            output += f"💧 Mana Gathered\n{mana}\n"
            output += f"```"
            
            await interaction.followup.send(output)
    
    class SeasonView(discord.ui.View):
        def __init__(self, seasons, account_id, ctx):
            super().__init__()
            self.add_item(SeasonSelect(seasons, account_id, ctx))
    
    view = SeasonView(seasons, account_id, ctx)
    await ctx.send("Choose a season to view progress:", view=view)


@bot.command(name="forcefetch")
async def forcefetch(ctx):
    """Force fetch stats for all members with numeric roles (Owner only)"""
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Owner only.")
    
    season = db_get_current_season()
    if not season:
        return await ctx.send("❌ No season active. Use `/newseason` to start one.")
    
    season_id, season_name, start_date, created_at = season
    today = date.today().isoformat()
    
    # Get all lords from server members
    lords = get_all_lords_from_guild(ctx.guild)
    if not lords:
        return await ctx.send("❌ No members with numeric roles found.")
    
    await ctx.send(f"⏳ Fetching stats for {len(lords)} members from season {season_name}...")
    
    fetched = 0
    failed = 0
    
    for lord in lords:
        try:
            account_id = lord["account_id"]
            name = lord["name"]
            
            stats = await fetch_stats_for_account(account_id, start_date, today)
            if stats:
                fetched += 1
                log_info(f"[FORCEFETCH] ✅ {name} ({account_id})")
            else:
                failed += 1
                log_info(f"[FORCEFETCH] ❌ {name} ({account_id})")
        except Exception as e:
            failed += 1
            log_info(f"[FORCEFETCH] ERROR {name}: {e}")
    
    embed = discord.Embed(
        title="📊 Force Fetch Complete",
        description=f"Season: {season_name}",
        color=0x2ecc71
    )
    embed.add_field(name="✅ Fetched", value=str(fetched), inline=True)
    embed.add_field(name="❌ Failed", value=str(failed), inline=True)
    embed.add_field(name="💾 Cache", value=f"All data cached for 3 days", inline=False)
    embed.set_footer(text=f"Fetched: {start_date} → {today}")
    
    await ctx.send(embed=embed)


@bot.command(name="loadhistory")
async def loadhistory(ctx, mode: str = None):
    """
    [OWNER ONLY]
    Load ALL historical data - DAILY SNAPSHOTS.
    
    Usage:
      !loadhistory        (loads from season start to today)
      !loadhistory all    (finds oldest Call of Stats data and loads EVERYTHING to today!)
    
    With 'all': Automatically detects oldest available date for each member.
    Perfect for !gains to work with ALL available historical dates.
    """
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Owner only.")
    
    season = db_get_current_season()
    if not season:
        return await ctx.send("❌ No season active.")
    
    season_id, season_name, season_start_date, created_at = season
    today = date.today()
    
    # Get all members to fetch for
    lords = get_all_lords_from_guild(ctx.guild)
    for discord_id, account_id in DISCORD_TO_ACCOUNT_ID.items():
        if not any(l["account_id"] == account_id for l in lords):
            lords.append({"account_id": account_id, "name": f"Account {account_id}"})
    
    # Determine start date
    if mode and mode.lower() == "all":
        msg = await ctx.send(f"🔍 Scanning Call of Stats starting from Dec 1, 2025...\nThis may take 2-3 minutes...")
        
        # Just start from December 1, 2025
        start = date(2025, 12, 1)
        date_range_text = f"{start.isoformat()} → {today.isoformat()} (ALL available data!)"
        load_mode = "all"
        
    else:
        start = datetime.strptime(season_start_date, "%Y-%m-%d").date()
        date_range_text = f"{season_start_date} → {today.isoformat()} (season data)"
        load_mode = "season"
        msg = await ctx.send(f"⏳ Loading historical data...\n📅 {date_range_text}")
    
    total_days = (today - start).days + 1
    
    await msg.edit(content=f"⏳ Loading historical data...\n📅 {date_range_text}\n👥 {len(lords)} members × {total_days} days = {total_days * len(lords)} snapshots\nThis may take 5-30 minutes depending on data size...")
    
    # Fetch data for each day - fetch EACH DAY INDIVIDUALLY
    current_date = start
    saved_count = 0
    skipped_count = 0
    day_num = 0
    failed_count = 0
    
    while current_date <= today:
        day_num += 1
        date_str = current_date.isoformat()
        
        for lord in lords:
            try:
                account_id = lord["account_id"]
                name = lord.get("name", account_id)
                
                # CHECK: Does this snapshot already exist?
                if db_snapshot_exists(season_id, account_id, date_str):
                    # Already saved, skip it!
                    skipped_count += 1
                    continue
                
                # Fetch for THIS DAY ONLY (date_str to date_str)
                stats, actual_date = await fetch_stats_with_fallback(account_id, date_str, date_str)
                
                # CHECK: Is the data empty/all zeros? If so, DON'T save it
                if is_stats_empty(stats):
                    # Empty data, skip but don't delete anything
                    log_info(f"[LOADHISTORY] Skipping empty data for {account_id} on {date_str}")
                    skipped_count += 1
                    continue
                
                if stats:
                    # Save to database with the correct date
                    db_save_season_progress(season_id, account_id, stats.get("lord_name", name), stats, actual_date)
                    saved_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                log_error(f"[LOADHISTORY] Error for {account_id} on {date_str}: {e}")
                failed_count += 1
                continue
        
        # Update progress message every 5 days or on last day
        if day_num % 5 == 0 or current_date == today:
            progress = (day_num / total_days) * 100
            try:
                await msg.edit(content=f"⏳ Loading historical data...\n📅 {date_range_text}\nDay {day_num}/{total_days} ({progress:.0f}%)\n✅ Saved {saved_count} | ⏭️ Skipped {skipped_count}")
            except:
                pass
        
        current_date += timedelta(days=1)
    
    # Create result embed
    embed = discord.Embed(
        title="📚 Historical Data Load Complete",
        description=f"Season: {season_name}",
        color=0x2ecc71
    )
    embed.add_field(name="📅 Date Range", value=date_range_text, inline=False)
    embed.add_field(name="🎯 Load Mode", value="ALL Available Data" if load_mode == "all" else "Season Data", inline=True)
    embed.add_field(name="👥 Members Tracked", value=str(len(lords)), inline=True)
    embed.add_field(name="📊 Snapshots Saved", value=str(saved_count), inline=True)
    embed.add_field(name="⏭️ Snapshots Skipped", value=str(skipped_count), inline=True)
    embed.add_field(name="📈 Total Days Covered", value=str(total_days), inline=True)
    embed.add_field(name="✅ Status", value="Complete database created!\n\n🎯 You can now use `!gains` with dates from this entire range!", inline=False)
    embed.set_footer(text="!gains is now fully powered with all available historical data")
    
    await ctx.send(embed=embed)
    log_info(f"[LOADHISTORY] Complete! Mode={load_mode}, Saved {saved_count}, Skipped {skipped_count} from {start.isoformat()} to {today.isoformat()}")


@bot.command(name="seasonhistory")
async def seasonhistory(ctx):
    """
    Show all seasons with their start date and end date (or current day if active).
    """
    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id, season_name, start_date, created_at FROM seasons ORDER BY created_at ASC")
        seasons = c.fetchall()
        conn.close()
        
        if not seasons:
            return await ctx.send("❌ No seasons found in database.")
        
        current_season = db_get_current_season()
        current_season_id = current_season[0] if current_season else None
        today = date.today().isoformat()
        
        # Build output
        output = "```📅 SEASON HISTORY\n\n"
        
        for season_id, season_name, start_date, created_at in seasons:
            is_current = (season_id == current_season_id)
            
            if is_current:
                # Current season: show start date → today
                end_display = today
                status = "🔴 ACTIVE"
            else:
                # Past season: try to find end date (last day with data)
                conn = sqlite3.connect(DB_PROGRESS)
                c = conn.cursor()
                c.execute(
                    "SELECT MAX(data_date) FROM season_progress WHERE season_id = ?",
                    (season_id,)
                )
                row = c.fetchone()
                conn.close()
                end_display = row[0] if row and row[0] else "Unknown"
                status = "✅ ENDED"
            
            output += f"{status} {season_name}\n"
            output += f"   📍 {start_date} → {end_display}\n\n"
        
        output += "```"
        await ctx.send(output)
        
    except Exception as e:
        log_error(f"[SEASONHISTORY ERROR] {e}")
        await ctx.send(f"❌ Error: {str(e)}")




@bot.command(name="datahistory")
async def datahistory(ctx):
    """
    [OWNER ONLY]
    Show the oldest and newest data saved in database.
    Useful to know the date range for !gains with specific dates.
    """
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Owner only.")
    
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        
        # Get oldest and newest dates
        c.execute("SELECT MIN(data_date), MAX(data_date), COUNT(*) FROM season_progress")
        row = c.fetchone()
        conn.close()
        
        oldest_date, newest_date, total_snapshots = row if row else (None, None, 0)
        
        if not oldest_date:
            return await ctx.send("❌ No data found in database.")
        
        # Create result embed
        embed = discord.Embed(
            title="📊 Database History",
            description="Complete data range saved",
            color=0x3498db
        )
        embed.add_field(name="📅 Oldest Data", value=f"`{oldest_date}`", inline=True)
        embed.add_field(name="📅 Newest Data", value=f"`{newest_date}`", inline=True)
        embed.add_field(name="📦 Total Snapshots", value=str(total_snapshots), inline=True)
        embed.add_field(
            name="📝 Usage Example",
            value=f"`!gains {oldest_date} {newest_date}`\nor\n`!gains {oldest_date} {newest_date} rekz`",
            inline=False
        )
        embed.set_footer(text="You can use any date within this range with !gains command")
        
        await ctx.send(embed=embed)
        log_info(f"[DATAHISTORY] {oldest_date} → {newest_date} ({total_snapshots} snapshots)")
        
    except Exception as e:
        log_error(f"[DATAHISTORY ERROR] {e}")
        await ctx.send(f"❌ Error: {str(e)}")


@bot.command(name="cleanupempty")
async def cleanupempty(ctx):
    """
    [OWNER ONLY]
    Scan database and delete any snapshots with no lord_name (truly empty data).
    Useful for removing bad/corrupted snapshots.
    """
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Owner only.")
    
    msg = await ctx.send("🔍 Scanning database for empty data...")
    
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        
        # Get ALL snapshots with lord_name
        c.execute("SELECT id, season_id, account_id, data_date, lord_name FROM season_progress")
        rows = c.fetchall()
        conn.close()
        
        deleted_count = 0
        total_checked = len(rows)
        
        log_info(f"[CLEANUP] Scanning {total_checked} snapshots for empty data...")
        
        for row_id, season_id, account_id, data_date, lord_name in rows:
            # Check if lord_name is empty (means no real data)
            is_empty = not lord_name or lord_name.strip() == ""
            
            # If empty, delete it
            if is_empty:
                try:
                    conn = sqlite3.connect(DB_PROGRESS)
                    c = conn.cursor()
                    c.execute("DELETE FROM season_progress WHERE id = ?", (row_id,))
                    conn.commit()
                    conn.close()
                    deleted_count += 1
                    log_info(f"[CLEANUP] Deleted empty snapshot: {account_id} on {data_date}")
                except Exception as e:
                    log_error(f"[CLEANUP] Error deleting row {row_id}: {e}")
        
        # Create result embed
        embed = discord.Embed(
            title="🧹 Database Cleanup Complete",
            description="Removed snapshots with no lord data",
            color=0x2ecc71
        )
        embed.add_field(name="📊 Total Snapshots Scanned", value=str(total_checked), inline=True)
        embed.add_field(name="🗑️ Invalid Snapshots Deleted", value=str(deleted_count), inline=True)
        embed.add_field(name="✅ Valid Snapshots Kept", value=str(total_checked - deleted_count), inline=True)
        embed.add_field(name="Status", value="Database cleaned! Ready to use.", inline=False)
        embed.set_footer(text="You can now run !loadhistory all safely")
        
        await msg.edit(content="", embed=embed)
        log_info(f"[CLEANUP] Complete! Deleted {deleted_count}/{total_checked} invalid snapshots")
        
    except Exception as e:
        log_error(f"[CLEANUP ERROR] {e}")
        await msg.edit(content=f"❌ Error during cleanup: {str(e)}")


class GainsDateSelector(discord.ui.View):
    """Interactive selector for gains date range"""
    
    def __init__(self, available_dates, account_id, season_id, start_date, ctx):
        super().__init__(timeout=120)
        self.available_dates = available_dates
        self.account_id = account_id
        self.season_id = season_id
        self.start_date = start_date
        self.ctx = ctx
        
        self.selected_start = None
        self.selected_end = None
        
        # Discord limit: dropdowns can only have 25 options max
        # If more than 25 dates, show the most recent 25
        limited_dates = available_dates[-25:] if len(available_dates) > 25 else available_dates
        
        # Populate start date dropdown
        start_select = Select(
            placeholder="📅 Pick Start Date (recent 25)",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=d, value=d) for d in limited_dates]
        )
        start_select.callback = self.on_start_select
        self.add_item(start_select)
        
        # Populate end date dropdown
        end_select = Select(
            placeholder="📅 Pick End Date (recent 25)",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=d, value=d) for d in limited_dates]
        )
        end_select.callback = self.on_end_select
        self.add_item(end_select)
    
    async def on_start_select(self, interaction: discord.Interaction):
        self.selected_start = interaction.data["values"][0]
        await interaction.response.defer()
    
    async def on_end_select(self, interaction: discord.Interaction):
        self.selected_end = interaction.data["values"][0]
        await interaction.response.defer()
    
    @discord.ui.button(label="📊 Show Gains", style=discord.ButtonStyle.green)
    async def show_gains(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_start or not self.selected_end:
            return await interaction.response.send_message("❌ Please select both dates", ephemeral=True)
        
        if self.selected_start > self.selected_end:
            return await interaction.response.send_message("❌ Start date must be before end date", ephemeral=True)
        
        await interaction.response.defer()
        
        # Get stats for both dates
        stats_start = db_get_season_progress(self.season_id, self.account_id, self.selected_start)
        stats_end = db_get_season_progress(self.season_id, self.account_id, self.selected_end)
        
        if not stats_start:
            stats_start = get_cached_stats(self.account_id, self.start_date, self.selected_start)
        if not stats_end:
            stats_end = get_cached_stats(self.account_id, self.start_date, self.selected_end)
        
        if not stats_start or not stats_end:
            return await interaction.followup.send("❌ Missing data for selected dates")
        
        # Helper to parse stats
        def parse_stat(s):
            if not s:
                return 0
            return int(str(s).replace("+", "").replace(",", "") or 0)
        
        # Calculate gains
        power_gain = parse_stat(stats_end.get("power_gain", "0")) - parse_stat(stats_start.get("power_gain", "0"))
        merits_gain = parse_stat(stats_end.get("merits", "0")) - parse_stat(stats_start.get("merits", "0"))
        kills_gain = parse_stat(stats_end.get("kills_gain", "0")) - parse_stat(stats_start.get("kills_gain", "0"))
        deaths_gain = parse_stat(stats_end.get("deads_gain", "0")) - parse_stat(stats_start.get("deads_gain", "0"))
        mana_gain = parse_stat(stats_end.get("mana_gathered", "0")) - parse_stat(stats_start.get("mana_gathered", "0"))
        mana_spent = abs(parse_stat(stats_end.get("mana_spent", "0")))
        gold_spent = abs(parse_stat(stats_end.get("gold_spent", "0")))
        wood_spent = abs(parse_stat(stats_end.get("wood_spent", "0")))
        ore_spent = abs(parse_stat(stats_end.get("ore_spent", "0")))
        
        # Debug logging
        log_info(f"[GAINS DEBUG] Start date {self.selected_start}: power_gain={stats_start.get('power_gain')}")
        log_info(f"[GAINS DEBUG] End date {self.selected_end}: power_gain={stats_end.get('power_gain')}")
        log_info(f"[GAINS DEBUG] Calculated power_gain: {power_gain}")
        
        lord_name = stats_end.get("lord_name", self.account_id)
        
        # Create columnar display
        day_count = (datetime.strptime(self.selected_end, "%Y-%m-%d").date() - 
                     datetime.strptime(self.selected_start, "%Y-%m-%d").date()).days + 1
        
        embed = discord.Embed(
            title=f"📊 Gains Report",
            description=f"**{lord_name}** • {day_count} days ({self.selected_start} → {self.selected_end})",
            color=0x9b59b6
        )
        
        # Row 1: Power, Merits, Kills
        embed.add_field(name="⚔️ Power Gain", value=f"```{power_gain:,}```", inline=True)
        embed.add_field(name="🏆 Merits Gain", value=f"```{merits_gain:,}```", inline=True)
        embed.add_field(name="💀 Kills Gain", value=f"```{kills_gain:,}```", inline=True)
        
        # Row 2: Deaths, Mana Gained, Mana Spent
        embed.add_field(name="☠️ Deaths Gain", value=f"```{deaths_gain:,}```", inline=True)
        embed.add_field(name="💧 Mana Gained", value=f"```{mana_gain:,}```", inline=True)
        embed.add_field(name="💧 Mana Spent", value=f"```{mana_spent:,}```", inline=True)
        
        # Row 3: Resources Spent
        embed.add_field(name="💰 Gold Spent", value=f"```{gold_spent:,}```", inline=True)
        embed.add_field(name="🪵 Wood Spent", value=f"```{wood_spent:,}```", inline=True)
        embed.add_field(name="⛏️ Ore Spent", value=f"```{ore_spent:,}```", inline=True)
        
        await interaction.followup.send(embed=embed)


@bot.command(name="gains")
async def gains(ctx, param1: str = None, param2: str = None):
    """
    Interactive GUI to view gains.
    
    Usage: 
      !gains rekz (current season for rekz)
      !gains rekz sos1 (Season 1 data for rekz)
    """
    
    # Identify user and season from parameters
    season = None
    user_input = None
    
    # Check if param1 is a season name first
    if param1:
        test_season = db_get_season_by_name(param1)
        if test_season:
            season = test_season
            user_input = param2  # If season found, param2 is the user
        else:
            # param1 might be a user, check param2 for season
            if param2:
                test_season = db_get_season_by_name(param2)
                if test_season:
                    season = test_season
                    user_input = param1  # param1 is the user
            else:
                # No season found, just a user specified - use current season
                user_input = param1
                season = db_get_current_season()
    else:
        # No params - use current user and current season
        user_input = None
        season = db_get_current_season()
    
    # Get account ID
    account_id = await get_account_id_from_input(ctx, user_input)
    if not account_id:
        return await ctx.send("❌ Could not find account ID.")
    
    # Get available dates for the season
    try:
        if not season:
            return await ctx.send("❌ No active season found.")
        
        season_id, season_name, start_date, created_at = season
        
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        
        # Show specific season data only
        c.execute(
            "SELECT DISTINCT data_date FROM season_progress WHERE season_id=? AND account_id=? ORDER BY data_date ASC",
            (season_id, account_id)
        )
        
        dates = [row[0] for row in c.fetchall()]
        conn.close()
        
        if not dates:
            return await ctx.send(f"❌ No saved data found for this account in {season_name}. Run `!loadhistory` first.")
        
        # Show selector
        embed = discord.Embed(
            title="📊 Gains Calculator",
            description=f"Season: **{season_name}**\nSelect start and end dates to see your gains.\n\n**Available dates:** {len(dates)} days of data\n📅 {start_date} → {created_at.split()[0]}",
            color=0x3498db
        )
        embed.add_field(name="ℹ️", value="Both dropdowns must be selected before clicking **Show Gains**", inline=False)
        
        view = GainsDateSelector(dates, account_id, season_id, start_date, ctx)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        log_error(f"[GAINS] Error: {e}")
        await ctx.send("❌ Error loading data. Try again later.")


@bot.command(name="topmana")
async def topmana(ctx, season_name: str = None):
    """Leaderboard for mana gathered. Usage: !topmana (current) or !topmana sos1 (specific season)"""
    
    # Get season
    if season_name:
        season = db_get_season_by_name(season_name)
        if not season:
            all_seasons = db_get_all_seasons()
            season_list = ", ".join([s[1] for s in all_seasons]) if all_seasons else "None"
            return await ctx.send(f"❌ Season '{season_name}' not found.\n\nAvailable seasons: {season_list}")
    else:
        season = db_get_current_season()
        if not season:
            return await ctx.send("❌ No season active. Use `/newseason` to start one.")
    
    season_id, season_name_display, start_date, created_at = season
    today = date.today().isoformat()
    
    lords = get_all_lords_from_guild(ctx.guild)
    if not lords:
        return await ctx.send("❌ No members with numeric roles found. Create roles with account IDs as names (e.g., `16322115`).")
    
    await ctx.send(f"⏳ Fetching leaderboard data for {len(lords)} lords...")
    
    # Fetch all lords in parallel with fallback
    fetch_tasks = [
        fetch_stats_with_fallback(lord["account_id"], start_date, today)
        for lord in lords
    ]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    
    leaderboard = []
    actual_end_date = today
    
    for lord, result in zip(lords, results):
        try:
            # Show all lords, even without data
            lord_name = "Unknown"
            mana_str = "+0"
            mana_num = 0
            
            if result and not isinstance(result, Exception):
                stats, end_date_used = result
                actual_end_date = end_date_used
                
                if stats:
                    lord_name = stats.get("lord_name", lord["name"])
                    
                    # Get mana_gathered if it exists (use abs() to handle negative values)
                    if stats.get("mana_gathered"):
                        mana_str = stats["mana_gathered"]
                        mana_clean = mana_str.replace(",", "").replace("+", "")
                        mana_num = abs(int(mana_clean)) if mana_clean.lstrip("-").isdigit() else 0
                    else:
                        log_info(f"[TOPMANA DEBUG] {lord['account_id']} - mana_gathered is None")
                else:
                    log_info(f"[TOPMANA ERROR] {lord['account_id']} - stats is None")
                    lord_name = lord["name"]
            else:
                log_info(f"[TOPMANA ERROR] {lord['account_id']} - result failed: {result}")
                lord_name = lord["name"]
            
            leaderboard.append({
                "name": lord_name,
                "mana": mana_num,
                "mana_str": mana_str
            })
        except Exception as e:
            log_info(f"[TOPMANA ERROR] {lord['account_id']}: {e}")
            leaderboard.append({
                "name": lord["name"],
                "mana": 0,
                "mana_str": "+0"
            })
    
    # Sort by mana descending
    leaderboard.sort(key=lambda x: x["mana"], reverse=True)
    
    # Build text output - compact
    output = f"```🏆 Top Mana Gathered - {season_name_display}\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, lord in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f"{i+1}."
        output += f"{medal} {lord['name']}: {lord['mana_str']}\n"
    
    output += f"📅 {start_date} → {actual_end_date}```"
    await ctx.send(output)


@bot.command(name="topdeaths")
async def topdeaths(ctx, season_name: str = None):
    """Leaderboard for most deaths. Usage: !topdeaths (current) or !topdeaths sos1 (specific season)"""
    
    # Get season
    if season_name:
        season = db_get_season_by_name(season_name)
        if not season:
            all_seasons = db_get_all_seasons()
            season_list = ", ".join([s[1] for s in all_seasons]) if all_seasons else "None"
            return await ctx.send(f"❌ Season '{season_name}' not found.\n\nAvailable seasons: {season_list}")
    else:
        season = db_get_current_season()
        if not season:
            return await ctx.send("❌ No season active. Use `/newseason` to start one.")
    
    season_id, season_name_display, start_date, created_at = season
    today = date.today().isoformat()
    
    lords = get_all_lords_from_guild(ctx.guild)
    if not lords:
        return await ctx.send("❌ No members with numeric roles found. Create roles with account IDs as names (e.g., `16322115`).")
    
    await ctx.send(f"⏳ Fetching leaderboard data for {len(lords)} lords...")
    
    # Fetch all lords in parallel with fallback
    fetch_tasks = [
        fetch_stats_with_fallback(lord["account_id"], start_date, today)
        for lord in lords
    ]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    
    leaderboard = []
    actual_end_date = today
    
    for lord, result in zip(lords, results):
        try:
            # Show all lords, even without data
            lord_name = "Unknown"
            deaths_str = "+0"
            deaths_num = 0
            
            if result and not isinstance(result, Exception):
                stats, end_date_used = result
                actual_end_date = end_date_used
                
                if stats:
                    lord_name = stats.get("lord_name", lord["name"])
                    
                    # Get deads_gain if it exists (use abs() to handle negative values)
                    if stats.get("deads_gain"):
                        deaths_str = stats["deads_gain"]
                        deaths_clean = deaths_str.replace(",", "").replace("+", "")
                        deaths_num = abs(int(deaths_clean)) if deaths_clean.lstrip("-").isdigit() else 0
                    else:
                        log_info(f"[TOPDEATHS DEBUG] {lord['account_id']} - deads_gain is None")
                else:
                    log_info(f"[TOPDEATHS ERROR] {lord['account_id']} - stats is None")
                    lord_name = lord["name"]
            else:
                log_info(f"[TOPDEATHS ERROR] {lord['account_id']} - result failed: {result}")
                lord_name = lord["name"]
            
            leaderboard.append({
                "name": lord_name,
                "deaths": deaths_num,
                "deaths_str": deaths_str
            })
        except Exception as e:
            log_info(f"[TOPDEATHS ERROR] {lord['account_id']}: {e}")
            leaderboard.append({
                "name": lord["name"],
                "deaths": 0,
                "deaths_str": "+0"
            })
    
    # Sort by deaths descending
    leaderboard.sort(key=lambda x: x["deaths"], reverse=True)
    
    # Build text output - compact
    output = f"```💀 Most Deaths - {season_name_display}\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, lord in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f"{i+1}."
        output += f"{medal} {lord['name']}: {lord['deaths_str']}\n"
    
    output += f"📅 {start_date} → {actual_end_date}```"
    await ctx.send(output)


@bot.command(name="topmerits")
async def topmerits(ctx, season_name: str = None):
    """Leaderboard for highest merits. Usage: !topmerits (current) or !topmerits sos1 (specific season)"""
    
    # Get season
    if season_name:
        season = db_get_season_by_name(season_name)
        if not season:
            all_seasons = db_get_all_seasons()
            season_list = ", ".join([s[1] for s in all_seasons]) if all_seasons else "None"
            return await ctx.send(f"❌ Season '{season_name}' not found.\n\nAvailable seasons: {season_list}")
    else:
        season = db_get_current_season()
        if not season:
            return await ctx.send("❌ No season active. Use `/newseason` to start one.")
    
    season_id, season_name_display, start_date, created_at = season
    today = date.today().isoformat()
    
    lords = get_all_lords_from_guild(ctx.guild)
    if not lords:
        return await ctx.send("❌ No members with numeric roles found.")
    
    await ctx.send(f"⏳ Fetching leaderboard data for {len(lords)} lords...")
    
    fetch_tasks = [fetch_stats_with_fallback(lord["account_id"], start_date, today) for lord in lords]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    
    leaderboard = []
    actual_end_date = today
    
    for lord, result in zip(lords, results):
        try:
            lord_name = "Unknown"
            merits_str = "+0"
            merits_num = 0
            
            if result and not isinstance(result, Exception):
                stats, end_date_used = result
                actual_end_date = end_date_used
                if stats:
                    lord_name = stats.get("lord_name", lord["name"])
                    if stats.get("merits"):
                        merits_str = stats["merits"]
                        merits_clean = merits_str.replace(",", "").replace("+", "")
                        merits_num = abs(int(merits_clean)) if merits_clean.lstrip("-").isdigit() else 0
            
            leaderboard.append({"name": lord_name, "merits": merits_num, "merits_str": merits_str})
        except Exception as e:
            log_info(f"[TOPMERITS ERROR] {lord.get('account_id')}: {e}")
            leaderboard.append({"name": lord["name"], "merits": 0, "merits_str": "+0"})
    
    leaderboard.sort(key=lambda x: x["merits"], reverse=True)
    
    output = f"```🏅 Top Merits - {season_name_display}\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, lord in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f"{i+1}."
        output += f"{medal} {lord['name']}: {lord['merits_str']}\n"
    output += f"📅 {start_date} → {actual_end_date}```"
    await ctx.send(output)


@bot.command(name="rss")
async def rss_leaderboard(ctx, season_name: str = None):
    """Top resource spenders. Usage: !rss (current) or !rss sos1 (specific season)"""
    
    # Get season
    if season_name:
        season = db_get_season_by_name(season_name)
        if not season:
            all_seasons = db_get_all_seasons()
            season_list = ", ".join([s[1] for s in all_seasons]) if all_seasons else "None"
            return await ctx.send(f"❌ Season '{season_name}' not found.\n\nAvailable seasons: {season_list}")
    else:
        season = db_get_current_season()
        if not season:
            return await ctx.send("❌ No season active. Use `/newseason` to start one.")
    
    season_id, season_name_display, start_date, created_at = season
    today = date.today().isoformat()
    
    lords = get_all_lords_from_guild(ctx.guild)
    if not lords:
        return await ctx.send("❌ No members with numeric roles found.")
    
    await ctx.send(f"⏳ Fetching leaderboard data for {len(lords)} lords...")
    
    fetch_tasks = [fetch_stats_with_fallback(lord["account_id"], start_date, today) for lord in lords]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    
    leaderboard = []
    actual_end_date = today
    
    for lord, result in zip(lords, results):
        try:
            lord_name = "Unknown"
            total_rss = 0
            
            if result and not isinstance(result, Exception):
                stats, end_date_used = result
                actual_end_date = end_date_used
                if stats:
                    lord_name = stats.get("lord_name", lord["name"])
                    
                    # Sum all resources spent (use abs() to handle negative values from API)
                    for key in ["gold_spent", "wood_spent", "ore_spent", "mana_spent"]:
                        val_str = stats.get(key, "+0").replace(",", "").replace("+", "")
                        try:
                            val = int(val_str) if val_str.lstrip("-").isdigit() else 0
                            total_rss += abs(val)  # Use absolute value
                        except Exception as e:
                            pass
            
            leaderboard.append({"name": lord_name, "rss": total_rss})
        except Exception as e:
            log_info(f"[RSS ERROR] {lord.get('account_id')}: {e}")
            leaderboard.append({"name": lord["name"], "rss": 0})
    
    leaderboard.sort(key=lambda x: x["rss"], reverse=True)
    
    output = f"```💰 Top Resource Spenders - {season_name}\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, lord in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f"{i+1}."
        output += f"{medal} {lord['name']}: {lord['rss']:,}\n"
    output += f"📅 {start_date} → {actual_end_date}```"
    await ctx.send(output)


async def get_rankings_for_stat(ctx, stat_key, start_date, end_date):
    """
    Get all lords ranked by a specific stat - uses database for current season.
    Returns dict: {account_id: (rank, total)} where rank is 1-indexed
    """
    season = db_get_current_season()
    if not season:
        return {}
    
    season_id, season_name, _, _ = season
    
    try:
        # Get all members from guild + mapped accounts
        lords = get_all_lords_from_guild(ctx.guild)
        checked_accounts = set()
        
        for lord in lords:
            checked_accounts.add(lord["account_id"])
        
        for discord_id, account_id in DISCORD_TO_ACCOUNT_ID.items():
            checked_accounts.add(account_id)
        
        # Valid stat keys to prevent SQL injection
        valid_stats = ["power_gain", "merits", "kills_gain", "deads_gain", "healed_gain",
                      "t5_gain", "t4_gain", "t3_gain", "t2_gain", "t1_gain",
                      "gold_spent", "wood_spent", "ore_spent", "mana_spent",
                      "gold_gathered", "wood_gathered", "ore_gathered", "mana_gathered"]
        
        if stat_key not in valid_stats:
            return {}
        
        # Get stats from database for all members (use latest data per account)
        stats_list = []
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        
        for account_id in checked_accounts:
            # Get LATEST row for this account (most recent date = most recent cumulative data)
            # Build query safely - stat_key is validated above
            query = f"SELECT {stat_key} FROM season_progress WHERE season_id=? AND account_id=? ORDER BY data_date DESC LIMIT 1"
            try:
                c.execute(query, (season_id, account_id))
                
                row = c.fetchone()
                if row and row[0]:
                    val_str = str(row[0]).replace(",", "").replace("+", "")
                    try:
                        val = int(val_str) if val_str.lstrip("-").isdigit() else 0
                        stats_list.append({"account_id": account_id, "value": val})
                    except:
                        pass
            except Exception as e:
                log_error(f"[RANKINGS] Error querying {account_id}: {e}")
                continue
        
        conn.close()
        
        # Sort by value descending
        stats_list.sort(key=lambda x: x["value"], reverse=True)
        
        # Create rank dict
        rankings = {}
        for i, item in enumerate(stats_list):
            rankings[item["account_id"]] = (i + 1, len(stats_list))
        
        return rankings
    except Exception as e:
        log_error(f"[RANKINGS ERROR] {e}")
        return {}


async def get_account_id_from_input(ctx, user_input):
    """Helper function to resolve username or account ID to account ID"""
    # If no input, use author's own account ID from role
    if not user_input:
        for role in ctx.author.roles:
            if role.name.isdigit():
                return role.name
        return None
    
    # If numeric, use as account ID
    if user_input.isdigit():
        return user_input
    
    # Check for mention (e.g. <@12345>)
    if user_input.startswith("<@") and user_input.endswith(">"):
        user_id_str = user_input[2:-1].replace("!", "")
        if user_id_str.isdigit():
            user_id = int(user_id_str)
            try:
                member = ctx.guild.get_member(user_id)
                if member:
                    for role in member.roles:
                        if role.name.isdigit():
                            return role.name
            except Exception as e:
                pass
        return None
    
    # Check username lookup
    username_lower = user_input.lower()
    found_discord_id = None
    
    for username, discord_id in USERNAME_TO_DISCORD_ID.items():
        if username.lower() == username_lower:
            found_discord_id = discord_id
            break
    
    if not found_discord_id:
        return None
    
    # Get the member from guild and find their numeric role
    try:
        member = ctx.guild.get_member(found_discord_id)
        if not member:
            return None
        
        for role in member.roles:
            if role.name.isdigit():
                return role.name
        return None
    except Exception as e:
        return None


@bot.command(name="compare")
async def compare(ctx, user1: str = None, user2: str = None):
    """Compare two lords side by side. Usage: !compare truvix rekz (or !compare 16322115 12345678)"""
    if not user1 or not user2:
        return await ctx.send("❌ Usage: `!compare truvix rekz` or `!compare 16322115 12345678`")
    
    season = db_get_current_season()
    if not season:
        return await ctx.send("❌ No season active. Use `/newseason` to start one.")
    
    season_id, season_name, start_date, created_at = season
    today = date.today().isoformat()
    
    msg = await ctx.send(f"⏳ Comparing {user1} vs {user2}...")
    
    try:
        # Resolve both users
        account_id1 = await get_account_id_from_input(ctx, user1)
        account_id2 = await get_account_id_from_input(ctx, user2)
        
        if not account_id1:
            return await msg.edit(content=f"❌ Could not find '{user1}'")
        if not account_id2:
            return await msg.edit(content=f"❌ Could not find '{user2}'")
        
        # FIRST: Try database for today
        stats1 = db_get_season_progress(season_id, account_id1, today)
        stats2 = db_get_season_progress(season_id, account_id2, today)
        
        # If not today, try yesterday
        if not stats1:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            stats1 = db_get_season_progress(season_id, account_id1, yesterday)
        if not stats2:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            stats2 = db_get_season_progress(season_id, account_id2, yesterday)
        
        # FALLBACK: If not in database, try cache
        if not stats1:
            stats1 = get_cached_stats(account_id1, start_date, today)
        if not stats2:
            stats2 = get_cached_stats(account_id2, start_date, today)
        
        # FALLBACK 2: If still missing, fetch from API (for unlisted people)
        if not stats1:
            stats1, _ = await fetch_stats_with_fallback(account_id1, start_date, today)
        if not stats2:
            stats2, _ = await fetch_stats_with_fallback(account_id2, start_date, today)
        
        if not stats1 or not stats2:
            return await msg.edit(content="❌ Failed to fetch stats")
        
        # Get highest power and T-kills for both (only if not in database)
        power1 = await fetch_highest_power(account_id1)
        power2 = await fetch_highest_power(account_id2)
        t_kills1 = await fetch_current_t_kills(account_id1)
        t_kills2 = await fetch_current_t_kills(account_id2)
        
        # Get lord names
        name1 = stats1.get("lord_name", "Unknown")
        name2 = stats2.get("lord_name", "Unknown")
        
        # Build comparison as CODE BLOCK (ORIGINAL FORMAT)
        name1 = stats1.get("lord_name", "Unknown")
        name2 = stats2.get("lord_name", "Unknown")
        
        output = f"```⚔️ {name1} vs {name2}\n\n"
        
        # Power - side by side with gain
        if power1 and power2:
            output += f"⚡ Power\n"
            
            # Get power gain from seasonal stats
            power_gain1 = 0
            power_gain2 = 0
            
            if stats1.get("power_gain"):
                try:
                    pg1_str = stats1.get("power_gain", "+0").replace("+", "").replace(",", "")
                    power_gain1 = int(pg1_str)
                except Exception as e:
                    power_gain1 = 0
            
            if stats2.get("power_gain"):
                try:
                    pg2_str = stats2.get("power_gain", "+0").replace("+", "").replace(",", "")
                    power_gain2 = int(pg2_str)
                except Exception as e:
                    power_gain2 = 0
            
            output += f"{name1}: {power1:,} (+{power_gain1:,})\n"
            output += f"{name2}: {power2:,} (+{power_gain2:,})\n"
            output += f"\n"
        
        # Merits - side by side
        m1 = stats1.get("merits", "+0")
        m2 = stats2.get("merits", "+0")
        mp1 = stats1.get("merits_pct", "0%")
        mp2 = stats2.get("merits_pct", "0%")
        output += f"🏅 Merits\n"
        output += f"{name1}: {m1} ({mp1})\n"
        output += f"{name2}: {m2} ({mp2})\n"
        output += f"\n"
        
        # Kills + Total T-kills combined
        k1 = stats1.get("kills_gain", "+0")
        k2 = stats2.get("kills_gain", "+0")
        d1 = stats1.get("deads_gain", "+0")
        d2 = stats2.get("deads_gain", "+0")
        h1 = stats1.get("healed_gain", "+0")
        h2 = stats2.get("healed_gain", "+0")
        
        # Calculate total T-kills
        total_t1 = sum(t_kills1.values()) if t_kills1 else 0
        total_t2 = sum(t_kills2.values()) if t_kills2 else 0
        
        output += f"💀 Deaths\n"
        output += f"{name1}: {d1}\n"
        output += f"{name2}: {d2}\n"
        output += f"\n"
        
        output += f"❤️ Healed\n"
        output += f"{name1}: {h1}\n"
        output += f"{name2}: {h2}\n"
        output += f"\n"
        
        output += f"⚔️ Kills\n"
        output += f"{name1}: {total_t1:,} ({k1})\n"
        output += f"{name2}: {total_t2:,} ({k2})\n"
        output += f"\n"
        
        # T-Tier Breakdown
        output += f"T5 Kills\n"
        t5_1 = t_kills1.get("t5", 0)
        t5_2 = t_kills2.get("t5", 0)
        output += f"{name1}: {t5_1:,}\n"
        output += f"{name2}: {t5_2:,}\n"
        output += f"\n"
        
        output += f"T4 Kills\n"
        t4_1 = t_kills1.get("t4", 0)
        t4_2 = t_kills2.get("t4", 0)
        output += f"{name1}: {t4_1:,}\n"
        output += f"{name2}: {t4_2:,}\n"
        output += f"\n"
        
        output += f"T3 Kills\n"
        t3_1 = t_kills1.get("t3", 0)
        t3_2 = t_kills2.get("t3", 0)
        output += f"{name1}: {t3_1:,}\n"
        output += f"{name2}: {t3_2:,}\n"
        output += f"\n"
        
        output += f"T2 Kills\n"
        t2_1 = t_kills1.get("t2", 0)
        t2_2 = t_kills2.get("t2", 0)
        output += f"{name1}: {t2_1:,}\n"
        output += f"{name2}: {t2_2:,}\n"
        output += f"\n"
        
        output += f"T1 Kills\n"
        t1_1 = t_kills1.get("t1", 0)
        t1_2 = t_kills2.get("t1", 0)
        output += f"{name1}: {t1_1:,}\n"
        output += f"{name2}: {t1_2:,}\n"
        output += f"\n"
        
        # Mana Gathered
        mg1 = stats1.get("mana_gathered", "+0")
        mg2 = stats2.get("mana_gathered", "+0")
        output += f"💧 Mana Gathered\n"
        output += f"{name1}: {mg1}\n"
        output += f"{name2}: {mg2}\n"
        output += f"\n"
        
        # RSS Spent
        output += f"💰 RSS Spent\n"
        gs1 = stats1.get("gold_spent", "+0")
        gs2 = stats2.get("gold_spent", "+0")
        ws1 = stats1.get("wood_spent", "+0")
        ws2 = stats2.get("wood_spent", "+0")
        os1 = stats1.get("ore_spent", "+0")
        os2 = stats2.get("ore_spent", "+0")
        ms1 = stats1.get("mana_spent", "+0")
        ms2 = stats2.get("mana_spent", "+0")
        
        # Parse with absolute values
        gs1_val = abs(int(gs1.replace(",", "").replace("+", ""))) if gs1.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        gs2_val = abs(int(gs2.replace(",", "").replace("+", ""))) if gs2.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        ws1_val = abs(int(ws1.replace(",", "").replace("+", ""))) if ws1.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        ws2_val = abs(int(ws2.replace(",", "").replace("+", ""))) if ws2.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        os1_val = abs(int(os1.replace(",", "").replace("+", ""))) if os1.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        os2_val = abs(int(os2.replace(",", "").replace("+", ""))) if os2.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        ms1_val = abs(int(ms1.replace(",", "").replace("+", ""))) if ms1.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        ms2_val = abs(int(ms2.replace(",", "").replace("+", ""))) if ms2.replace(",", "").replace("+", "").lstrip("-").isdigit() else 0
        
        output += f"  Gold: {name1} -{gs1_val:,} | {name2} -{gs2_val:,}\n"
        output += f"  Wood: {name1} -{ws1_val:,} | {name2} -{ws2_val:,}\n"
        output += f"  Ore: {name1} -{os1_val:,} | {name2} -{os2_val:,}\n"
        output += f"  Mana: {name1} -{ms1_val:,} | {name2} -{ms2_val:,}\n"
        output += f"\n"
        
        # RSS Gathered
        output += f"📦 RSS Gathered\n"
        gg1 = stats1.get("gold_gathered", "+0")
        gg2 = stats2.get("gold_gathered", "+0")
        wg1 = stats1.get("wood_gathered", "+0")
        wg2 = stats2.get("wood_gathered", "+0")
        og1 = stats1.get("ore_gathered", "+0")
        og2 = stats2.get("ore_gathered", "+0")
        mg1_g = stats1.get("mana_gathered", "+0")
        mg2_g = stats2.get("mana_gathered", "+0")
        
        output += f"  Gold: {name1} {gg1} | {name2} {gg2}\n"
        output += f"  Wood: {name1} {wg1} | {name2} {wg2}\n"
        output += f"  Ore: {name1} {og1} | {name2} {og2}\n"
        output += f"  Mana: {name1} {mg1_g} | {name2} {mg2_g}\n"
        
        output += f"```"
        
        await msg.edit(content=output)
    except Exception as e:
        log_info(f"[COMPARE ERROR] {e}")
        import traceback
        traceback.print_exc()
        await msg.edit(content=f"❌ Error: {str(e)}")


# ============================================================
# QUICK COMMANDS
# ============================================================

@bot.command(name="q")
async def quick_stats(ctx, user_input: str = None):
    """Quick one-liner stats. Usage: !q (your stats) or !q truvix"""
    season = db_get_current_season()
    if not season:
        return await ctx.send("❌ No season active.")
    
    season_id, season_name, start_date, created_at = season
    today = date.today().isoformat()
    
    # Get account ID
    account_id = await get_account_id_from_input(ctx, user_input)
    if not account_id:
        return await ctx.send("❌ Could not find account ID.")
    
    try:
        # FIRST: Try database for today
        stats = db_get_season_progress(season_id, account_id, today)
        
        # If not today, try yesterday
        if not stats:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            stats = db_get_season_progress(season_id, account_id, yesterday)
        
        # FALLBACK: Check cache
        if not stats:
            stats = get_cached_stats(account_id, start_date, today)
        
        # FALLBACK 2: Fetch from API (for unlisted people)
        if not stats:
            stats, _ = await fetch_stats_with_fallback(account_id, start_date, today)
        
        if not stats or stats.get("lord_name") == "Unknown":
            return await ctx.send("❌ Failed to fetch stats.")
        
        # Get power and rankings
        power = await fetch_highest_power(account_id)
        power_rank = await get_rankings_for_stat(ctx, "power_gain", start_date, today)
        merits_rank = await get_rankings_for_stat(ctx, "merits", start_date, today)
        kills_rank = await get_rankings_for_stat(ctx, "kills_gain", start_date, today)
        
        # Calculate merit to power ratio using highest power and merits
        if stats.get("merits") and power:
            try:
                merits_str = stats["merits"].replace("+", "").replace(",", "")
                merits_val = int(merits_str) if merits_str.isdigit() else 0
                
                # Calculate ratio: (Merits / Highest Power) × 100
                if power > 0:
                    ratio = (merits_val / power) * 100
                    stats["merits_pct"] = f"{ratio:.1f}%"
                else:
                    stats["merits_pct"] = "0%"
            except Exception as e:
                stats["merits_pct"] = "0%"
        else:
            stats["merits_pct"] = "0%"
        
        # Extract data with absolute values
        lord_name = stats.get("lord_name", "Unknown")
        merits = stats.get("merits", "+0")
        merits_pct = stats.get("merits_pct", "0%")
        kills = stats.get("kills_gain", "+0")
        deaths = stats.get("deads_gain", "+0")
        healed = stats.get("healed_gain", "+0")
        
        # Parse mana_spent with absolute value
        mana_spent_str = stats.get("mana_spent", "+0")
        mana_clean = mana_spent_str.replace(",", "").replace("+", "")
        mana_spent_val = abs(int(mana_clean)) if mana_clean.lstrip("-").isdigit() else 0
        mana_spent = f"-{mana_spent_val:,}"
        
        # Get ranking positions as strings
        power_rank_str = f"(#{power_rank[account_id][0]})" if account_id in power_rank else ""
        merits_rank_str = f"(#{merits_rank[account_id][0]})" if account_id in merits_rank else ""
        kills_rank_str = f"(#{kills_rank[account_id][0]})" if account_id in kills_rank else ""
        
        # Format one-liner
        output = f"**{lord_name}** | "
        
        if power:
            power_gain_str = stats.get("power_gain", "+0")
            output += f"⚡ {power:,} {power_gain_str} {power_rank_str} | "
        
        if merits and merits != "+0":
            output += f"🏅 {merits} ({merits_pct}) {merits_rank_str} | "
        
        output += f"⚔️ {kills} {kills_rank_str} | "
        output += f"💀 {deaths} | "
        output += f"❤️ {healed} | "
        output += f"💧 {mana_spent}"
        
        await ctx.send(output)
    except Exception as e:
        log_error(f"Quick stats error: {e}")
        await ctx.send("❌ Error fetching stats.")


@bot.command(name="active")
async def active_members(ctx):
    """Show who's active (last 24h) vs inactive with days count - uses cached data"""
    season = db_get_current_season()
    if not season:
        return await ctx.send("❌ No season active.")
    
    season_id, season_name, start_date, created_at = season
    today = date.today().isoformat()
    
    try:
        guild = ctx.guild
        lords = get_all_lords_from_guild(guild)
        
        # Create set to track which account IDs we've already checked (prevent duplicates)
        checked_accounts = set()
        accounts_to_check = []
        
        # Add lords from guild roles
        for lord in lords:
            account_id = lord["account_id"]
            if account_id not in checked_accounts:
                checked_accounts.add(account_id)
                accounts_to_check.append(account_id)
        
        # Add mapped accounts (like Havi who's not in server)
        for discord_id, account_id in DISCORD_TO_ACCOUNT_ID.items():
            if account_id not in checked_accounts:
                checked_accounts.add(account_id)
                accounts_to_check.append(account_id)
        
        if not accounts_to_check:
            return await ctx.send("❌ No members found.")
        
        active = []
        inactive = []
        
        for account_id in accounts_to_check:
            try:
                # PRIORITY 1: Try cache first (populated by forcefetch)
                stats_today = get_cached_stats(account_id, start_date, today)
                actual_today_date = today
                
                # PRIORITY 2: Try database if cache miss
                if not stats_today:
                    stats_today = db_get_season_progress(season_id, account_id, today)
                    if stats_today:
                        actual_today_date = stats_today.get("data_date", today)
                
                # PRIORITY 3: Try yesterday in cache
                if not stats_today:
                    yesterday = (date.today() - timedelta(days=1)).isoformat()
                    stats_today = get_cached_stats(account_id, start_date, yesterday)
                    if stats_today:
                        actual_today_date = yesterday
                
                # PRIORITY 4: Try yesterday in database
                if not stats_today:
                    yesterday = (date.today() - timedelta(days=1)).isoformat()
                    stats_today = db_get_season_progress(season_id, account_id, yesterday)
                    if stats_today:
                        actual_today_date = stats_today.get("data_date", yesterday)
                
                # If STILL no data, skip this account
                if not stats_today or not isinstance(stats_today, dict):
                    log_info(f"[ACTIVE] No stats for {account_id}, skipping")
                    continue
                
                # Now safe to get lord_name
                lord_name = stats_today.get("lord_name", account_id)
                if stats_today.get("data_date"):
                    actual_today_date = stats_today.get("data_date")
                
                log_info(f"[ACTIVE] Using {lord_name} data from {actual_today_date}")
                
                # Get stats from day before the actual date we got
                day_before = (datetime.strptime(actual_today_date, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
                
                # Try cache first for yesterday
                stats_yesterday = get_cached_stats(account_id, start_date, day_before)
                if stats_yesterday:
                    log_info(f"[ACTIVE] Found yesterday in CACHE for {account_id}: {day_before}")
                
                # Then try database for specific day
                if not stats_yesterday:
                    stats_yesterday = db_get_season_progress(season_id, account_id, day_before)
                    if stats_yesterday:
                        log_info(f"[ACTIVE] Found yesterday in DB for {account_id}: {day_before}")
                
                # If still not found, try to find LATEST data before today (handles skipped dates)
                if not stats_yesterday:
                    log_info(f"[ACTIVE] No yesterday data found, searching for earlier data before {actual_today_date}")
                    try:
                        conn = sqlite3.connect(DB_PROGRESS)
                        c = conn.cursor()
                        c.execute("""
                            SELECT power_gain, merits, kills_gain, deads_gain, healed_gain,
                                   t5_gain, t4_gain, t3_gain, t2_gain, t1_gain,
                                   gold_spent, wood_spent, ore_spent, mana_spent,
                                   gold_gathered, wood_gathered, ore_gathered, mana_gathered, lord_name, data_date
                            FROM season_progress
                            WHERE season_id=? AND account_id=? AND data_date < ?
                            ORDER BY data_date DESC
                            LIMIT 1
                        """, (season_id, account_id, actual_today_date))
                        row = c.fetchone()
                        conn.close()
                        
                        if row:
                            stats_yesterday = {
                                "power_gain": row[0],
                                "merits": row[1],
                                "kills_gain": row[2],
                                "deads_gain": row[3],
                                "healed_gain": row[4],
                                "t5_gain": row[5],
                                "t4_gain": row[6],
                                "t3_gain": row[7],
                                "t2_gain": row[8],
                                "t1_gain": row[9],
                                "gold_spent": row[10],
                                "wood_spent": row[11],
                                "ore_spent": row[12],
                                "mana_spent": row[13],
                                "gold_gathered": row[14],
                                "wood_gathered": row[15],
                                "ore_gathered": row[16],
                                "mana_gathered": row[17],
                                "lord_name": row[18],
                                "data_date": row[19]
                            }
                            log_info(f"[ACTIVE] Found earlier data for {account_id}: {row[19]}")
                        else:
                            log_info(f"[ACTIVE] ❌ No earlier data found for {account_id} before {actual_today_date}")
                    except Exception as e:
                        log_error(f"[ACTIVE] Error querying earlier dates: {e}")
                
                if not stats_yesterday or not isinstance(stats_yesterday, dict):
                    log_info(f"[ACTIVE] Marking {lord_name} as INACTIVE (no comparison data)")
                    inactive.append({"name": lord_name, "days": "?"})
                    continue
                
                # Extract stats safely
                def safe_parse(stat_str):
                    """Safely parse stat strings like '+12,345' to int"""
                    if not stat_str:
                        return 0
                    return int(str(stat_str).replace("+", "").replace(",", "") or 0)
                
                power_today = safe_parse(stats_today.get("power_gain", "0"))
                power_yesterday = safe_parse(stats_yesterday.get("power_gain", "0"))
                
                merits_today = safe_parse(stats_today.get("merits", "0"))
                merits_yesterday = safe_parse(stats_yesterday.get("merits", "0"))
                
                mana_today = safe_parse(stats_today.get("mana_gathered", "0"))
                mana_yesterday = safe_parse(stats_yesterday.get("mana_gathered", "0"))
                
                power_gain_24h = power_today - power_yesterday
                merits_gain_24h = merits_today - merits_yesterday
                mana_gain_24h = mana_today - mana_yesterday
                
                # Active if any gain
                if power_gain_24h > 0 or merits_gain_24h > 0 or mana_gain_24h > 0:
                    active.append({
                        "name": lord_name,
                        "power": power_gain_24h,
                        "merits": merits_gain_24h,
                        "mana": mana_gain_24h
                    })
                else:
                    inactive.append({"name": lord_name, "days": "?"})
            except Exception as e:
                log_error(f"Error checking activity for {account_id}: {e}")
                import traceback
                log_error(traceback.format_exc())
                continue
        
        # Sort active by power gain
        active.sort(key=lambda x: x["power"], reverse=True)
        
        # Create embed
        embed = discord.Embed(
            title="📊 Activity Report",
            description="Last 24 Hours",
            color=0x2ecc71 if active else 0x95a5a6
        )
        
        if active:
            # Build two columns: Member name | All stats combined
            member_col = ""
            stats_col = ""
            
            for member in active:
                member_col += f"{member['name']}\n"
                stats_col += f"⚔️ +{member['power']:,} | 🏆 +{member['merits']:,} | 💧 +{member['mana']:,}\n"
            
            embed.add_field(name="✅ Member", value=member_col or "None", inline=True)
            embed.add_field(name="📈 Stats (Power | Merits | Mana)", value=stats_col or "—", inline=True)
        else:
            embed.add_field(name="✅ Active Members", value="None", inline=False)
        
        if inactive:
            inactive_list = "\n".join([f"• {m['name']}" for m in inactive])
            embed.add_field(name=f"⏸️ Inactive ({len(inactive)})", value=inactive_list, inline=False)
        
        await ctx.send(embed=embed)
    except Exception as e:
        log_error(f"Active members error: {e}")
        await ctx.send("❌ Error checking activity.")


# ============================================================
# WEEKLY EVENTS
# ============================================================

weekly_events = ["Melee Wheel", "Melee Forge", "Range Wheel", "Range Forge"]
event_emojis = {
    "Range Forge": "🏹",
    "Melee Wheel": "⚔️",
    "Melee Forge": "🔨",
    "Range Wheel": "🎯"
}

start_date = date(2025, 9, 16)

@bot.tree.command(name="weeklyevent", description="Show current and upcoming weekly Abyss events")
async def weeklyevent(inter):
    today = date.today()
    sunday = start_date - timedelta(days=start_date.weekday() + 1)
    weeks = (today - sunday).days // 7

    this_tue = sunday + timedelta(weeks=weeks, days=2)
    now = datetime.utcnow()

    event_start = datetime.combine(this_tue, time(0, 0))
    event_end = event_start + timedelta(days=3)

    if now >= event_end:
        weeks += 1
        this_tue = sunday + timedelta(weeks=weeks, days=2)
        event_start = datetime.combine(this_tue, time(0, 0))
        event_end = event_start + timedelta(days=3)

    msg = "📅 **Weekly Abyss Events**\n\n"
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    for i in range(4):
        idx = (weeks + i) % 4
        nm = weekly_events[idx]
        emoji = event_emojis.get(nm, "📌")
        ev_date = sunday + timedelta(weeks=weeks + i, days=2)
        base_dt = datetime.combine(ev_date, time(0, 0))

        if i == 0 and event_start <= now < event_end:
            left = event_end - now
            st = f"🟢 LIVE NOW ({left.seconds // 3600}h {(left.seconds // 60) % 60}m left)"
        else:
            left = base_dt - now
            st = f"⏳ {left.days}d {left.seconds // 3600}h {(left.seconds // 60) % 60}m"

        msg += f"{nums[i]} {emoji} **{nm}** — <t:{int(base_dt.timestamp())}:F>\n{st}\n\n"

    await inter.response.send_message(msg)

# ============================================================
# KVK / CUSTOM EVENTS DISPLAY
# ============================================================
@bot.tree.command(name="checkdb", description="check DB")
async def dbdump(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message(
            "Owner only.", ephemeral=True
        )

    rows = db_get_events()
    if not rows:
        return await interaction.response.send_message(
            "DB is empty.", ephemeral=True
        )

    msg = "\n".join(str(r) for r in rows)
    await interaction.response.send_message(
        f"```{msg}```", ephemeral=True
    )


@bot.tree.command(name="kvkevent", description="Show upcoming custom scheduled events")
async def kvkevent(inter):
    now = datetime.utcnow()
    rows = db_get_events()

    upcoming = [r for r in rows if datetime.fromisoformat(r[2]) > now]
    if not upcoming:
        return await inter.response.send_message("📭 No upcoming events.", ephemeral=True)

    upcoming = upcoming[:4]
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    msg = "📅 **Upcoming Events**\n\n"

    for i, row in enumerate(upcoming):
        event_id, name, dt, rem = row
        dt_obj = datetime.fromisoformat(dt)
        left = dt_obj - now
        msg += (
            f"{nums[i]} **{name}** — <t:{int(dt_obj.timestamp())}:F>\n"
            f"Starts in {left.days}d {left.seconds // 3600}h {(left.seconds // 60) % 60}m\n\n"
        )

    await inter.response.send_message(msg, ephemeral=True)

# ============================================================
# ADD EVENT MODAL
# ============================================================
class AddEventModal(Modal, title="➕ Add Event"):
    name = TextInput(
        label="Event Name",
        placeholder="e.g. Pass 1 Opens"
    )
    dt_input = TextInput(
        label="Datetime (UTC)",
        placeholder="DD-MM-YYYY HH:MM | 1d 2h | 14utc"
    )
    reminder = TextInput(
        label="Reminder (minutes or 'no')",
        placeholder="15"
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            dt = parse_datetime(self.dt_input.value)

            # Round event time to minute precision
            dt = dt.replace(second=0, microsecond=0)

            # Validate event is in the future
            if dt <= datetime.utcnow():
                return await interaction.followup.send(
                    "❌ Event must be in the future!",
                    ephemeral=True
                )

            rem = (
                0
                if self.reminder.value.lower() == "no"
                else int(self.reminder.value)
            )

            db_add_event(
                self.name.value.strip(),
                dt.isoformat(),
                rem
            )

            await interaction.followup.send(
                f"✅ **Event Added**\n"
                f"**{self.name.value}**\n"
                f"<t:{int(dt.timestamp())}:F>",
                ephemeral=True
            )

        except Exception as e:
            log_info("[AddEvent Error]", e)
            await interaction.followup.send(
                "❌ Failed to add event.",
                ephemeral=True
            )

@bot.tree.command(name="addevent", description="Add a custom event")
async def addevent(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    await inter.response.send_modal(AddEventModal())


# ============================================================
# ADD / EDIT / REMOVE EVENT COMMANDS
# ============================================================

@bot.tree.command(name="testdm", description="Owner-only: test Abyss role DMs")
async def testdm(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message(
            "❌ Owner only.", ephemeral=True
        )

    embed = discord.Embed(
        title="🧪 Abyss DM Test",
        description="If you received this, Abyss DMs are working ✅",
        color=0x2ECC71
    )

    await interaction.response.send_message(
        "📨 Sending test DMs to Abyss role members…",
        ephemeral=True
    )

    await dm_abyss_role(interaction.guild, embed)



@bot.tree.command(name="editevent", description="Edit an existing event")
async def editevent(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    events = db_get_events()
    if not events:
        return await inter.response.send_message("❌ No events available.", ephemeral=True)

    options = [
        discord.SelectOption(
            label=f"{name} ({dt})",
            value=str(event_id)
        )
        for event_id, name, dt, rem in events
    ]

    select = Select(
        placeholder="Select an event to edit",
        options=options
    )

    async def select_callback(i: discord.Interaction):
        event_id = int(select.values[0])
        event = next(e for e in events if e[0] == event_id)

        _, old_name, old_dt, old_rem = event

        class EditEventModal(Modal, title="Edit Event"):
            name = TextInput(label="Event Name", default=old_name)
            datetime = TextInput(
                label="Date & Time (YYYY-MM-DD HH:MM)",
                default=old_dt.replace("T", " ")[:16]
            )
            reminder = TextInput(
                label="Reminder (hours before)",
                default=str(old_rem)
            )

            async def on_submit(self, modal_inter: discord.Interaction):
                try:
                    dt_str = self.datetime.value.strip()

                    # Parse and round to minute precision
                    dt_obj = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                    dt_obj = dt_obj.replace(second=0, microsecond=0)
                    dt_str = dt_obj.isoformat(timespec="minutes")

                    rem = int(self.reminder.value.strip())

                    db_update_event(
                        event_id,
                        name=self.name.value.strip(),
                        dt=dt_str,
                        reminder=rem
                    )

                    await modal_inter.response.send_message(
                        "✅ Event updated successfully.",
                        ephemeral=True
                    )

                except ValueError:
                    await modal_inter.response.send_message(
                        "❌ Invalid date or reminder format.\nUse `YYYY-MM-DD HH:MM`.",
                        ephemeral=True
                    )

                except Exception as e:
                    log_info("[EditEvent Error]", e)
                    await modal_inter.response.send_message(
                        "❌ Failed to update event.",
                        ephemeral=True
                    )


        await i.response.send_modal(EditEventModal())

    select.callback = select_callback
    view = View()
    view.add_item(select)

    await inter.response.send_message(
        "Select an event to edit:",
        view=view,
        ephemeral=True
    )


@bot.tree.command(name="addrole", description="Get the Abyss role")
async def addrole(interaction: discord.Interaction):
    role = interaction.guild.get_role(ABYSS_ROLE_ID)
    if not role:
        return await interaction.response.send_message(
            "❌ Abyss role not found.", ephemeral=True
        )

    if role in interaction.user.roles:
        return await interaction.response.send_message(
            "⚠️ You already have the Abyss role.", ephemeral=True
        )

    await interaction.user.add_roles(role)
    await interaction.response.send_message(
        "✅ Abyss role added! You will now receive Abyss reminders.",
        ephemeral=True
    )
@bot.tree.command(name="removerole", description="Remove the Abyss role")
async def removerole(interaction: discord.Interaction):
    role = interaction.guild.get_role(ABYSS_ROLE_ID)
    if not role:
        return await interaction.response.send_message(
            "❌ Abyss role not found.", ephemeral=True
        )

    if role not in interaction.user.roles:
        return await interaction.response.send_message(
            "⚠️ You don’t have the Abyss role.", ephemeral=True
        )

    await interaction.user.remove_roles(role)
    await interaction.response.send_message(
        "✅ Abyss role removed. You will no longer receive Abyss reminders.",
        ephemeral=True
    )

@bot.tree.command(name="removeevent", description="Remove an existing event")
async def removeevent(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    events = db_get_events()
    if not events:
        return await inter.response.send_message("❌ No events available.", ephemeral=True)

    options = [
        discord.SelectOption(
            label=f"{name} ({dt})",
            value=str(event_id)
        )
        for event_id, name, dt, rem in events
    ]

    select = Select(
        placeholder="Select an event to remove",
        options=options
    )

    async def select_callback(i: discord.Interaction):
        event_id = int(select.values[0])
        db_delete_event(event_id)
        await i.response.send_message(
            "🗑️ Event removed successfully.",
            ephemeral=True
        )

    select.callback = select_callback
    view = View()
    view.add_item(select)

    await inter.response.send_message(
        "Select an event to remove:",
        view=view,
        ephemeral=True
    )


# ============================================================
# ABYSS CONFIG COMMAND
# ============================================================
class AbyssConfigView(View):
    def __init__(self, days, hours, rem, round2):
        super().__init__(timeout=300)
        self.days = days
        self.hours = hours
        self.rem = rem
        self.round2 = round2

        self.day_sel = Select(
            placeholder="Select Abyss Days",
            min_values=1,
            max_values=7,
            options=[
                discord.SelectOption(
                    label=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i],
                    value=str(i),
                    default=(i in days)
                )
                for i in range(7)
            ]
        )
        self.day_sel.callback = self.cb_days
        self.add_item(self.day_sel)

        self.hour_sel = Select(
            placeholder="Select Abyss Hours",
            min_values=1,
            max_values=6,
            options=[
                discord.SelectOption(
                    label=f"{h:02}:00 UTC",
                    value=str(h),
                    default=(h in hours)
                )
                for h in [0,4,8,12,16,20]
            ]
        )
        self.hour_sel.callback = self.cb_hours
        self.add_item(self.hour_sel)

        self.rem_sel = Select(
            placeholder="Reminder Hours",
            min_values=0,
            max_values=len(hours),
            options=[
                discord.SelectOption(
                    label=f"{h:02}:00 UTC",
                    value=str(h),
                    default=(h in rem)
                )
                for h in hours
            ]
        )
        self.rem_sel.callback = self.cb_rem
        self.add_item(self.rem_sel)

        self.round_btn = Button(
            label=f"Round 2: {'ON' if round2 else 'OFF'}",
            style=discord.ButtonStyle.success if round2 else discord.ButtonStyle.danger
        )
        self.round_btn.callback = self.toggle_round2
        self.add_item(self.round_btn)

    async def cb_days(self, interaction):
        global ABYSS_DAYS
        self.days = [int(v) for v in self.day_sel.values]
        ABYSS_DAYS = self.days
        cfg["days"] = self.days
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message("Days updated ✔", ephemeral=True)

    async def cb_hours(self, interaction):
        global ABYSS_HOURS
        self.hours = [int(v) for v in self.hour_sel.values]
        ABYSS_HOURS = self.hours
        cfg["hours"] = self.hours
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message("Hours updated ✔", ephemeral=True)

    async def cb_rem(self, interaction):
        global REMINDER_HOURS
        self.rem = [int(v) for v in self.rem_sel.values]
        REMINDER_HOURS = self.rem
        cfg["reminder_hours"] = self.rem
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message("Reminder hours updated ✔", ephemeral=True)

    async def toggle_round2(self, interaction):
        global ROUND2_ENABLED
        self.round2 = not self.round2
        ROUND2_ENABLED = self.round2
        cfg["round2"] = self.round2
        save_json(ABYSS_CONFIG_FILE, cfg)
        await interaction.response.send_message(
            f"Round 2 {'enabled' if self.round2 else 'disabled'} ✔",
            ephemeral=True
        )



@bot.tree.command(name="abyssconfig", description="Configure Abyss days, hours, and reminders")
async def abyssconfig(inter):
    if inter.user.id != OWNER_ID:
        return await inter.response.send_message("❌ Owner only.", ephemeral=True)

    emb = discord.Embed(title="⚙️ Abyss Config", color=0x2ecc71)
    emb.add_field(name="Days", value=pretty_days(ABYSS_DAYS), inline=False)
    emb.add_field(name="Hours", value=pretty_hours(ABYSS_HOURS), inline=False)
    emb.add_field(name="Reminder Hours", value=pretty_hours(REMINDER_HOURS), inline=False)
    emb.add_field(
        name="Round 2",
        value="Enabled" if ROUND2_ENABLED else "Disabled",
        inline=False
    )

    view = AbyssConfigView(
        ABYSS_DAYS,
        ABYSS_HOURS,
        REMINDER_HOURS,
        ROUND2_ENABLED
    )

    await inter.response.send_message(
        embed=emb,
        view=view,
        ephemeral=True
    )


# ============================================================
# REMINDER LOOPS
# ============================================================

@tasks.loop(minutes=1)
async def abyss_reminder_loop():
    try:
        tz = pytz.timezone(MY_TIMEZONE)
        now = datetime.now(tz)

        if now.weekday() not in ABYSS_DAYS:
            return

        # Abyss start reminder
        if now.hour in REMINDER_HOURS and now.minute == 0:
            embed = discord.Embed(
                title="🕒 Abyss Reminder",
                description="Abyss starts in **15 minutes**!",
                color=0xE74C3C
            )
            ch = bot.get_channel(channel_id)
            if ch and ch.guild:
                await dm_abyss_role(ch.guild, embed)
            else:
                log_info("[ABYSS REMINDER] Warning: Channel not found or no guild")


        # Round 2 reminder
        if ROUND2_ENABLED and now.hour in REMINDER_HOURS and now.minute == 30:
            embed = discord.Embed(
                title="🕒 Abyss Reminder",
                description="Round 2 starts in **15 minutes**!",
                color=0xF1C40F
            )
            ch = bot.get_channel(channel_id)
            if ch and ch.guild:
                await dm_abyss_role(ch.guild, embed)
            else:
                log_info("[ABYSS REMINDER] Warning: Channel not found or no guild")
    except Exception as e:
        log_info(f"[ABYSS REMINDER ERROR] {type(e).__name__}: {e}")

sent_custom = set()

@tasks.loop(minutes=1)
async def custom_event_loop():
    try:
        now = datetime.utcnow().replace(second=0, microsecond=0)
        ch = bot.get_channel(channel_id)
        if not ch:
            return

        rows = db_get_events()
        for ev in rows:
            event_id, name, dt, rem = ev
            dt_obj = datetime.fromisoformat(dt)

            # Delete events 1 hour after they pass
            if now >= dt_obj + timedelta(hours=1):
                db_delete_event(event_id)
                continue

            # Reminder logic (robust, restart-safe)
            if rem > 0:
                rtime = (dt_obj - timedelta(minutes=rem)).replace(
                    second=0,
                    microsecond=0
                )

                if now >= rtime and event_id not in sent_custom:
                    await ch.send(
                        f"<@&{EVENT_ANNOUNCEMENT_ROLE_ID}> ⏰ Reminder: **{name}** in {rem} minutes! "
                        f"<t:{int(dt_obj.timestamp())}:F>"
                    )
                    sent_custom.add(event_id)

        # Prevent memory growth
        if len(sent_custom) > 300:
            sent_custom.clear()
    except Exception as e:
        log_info(f"[CUSTOM EVENT LOOP ERROR] {type(e).__name__}: {e}")


# ============================================================
# GAIN COMMAND - DATE RANGE WITH AUTOCOMPLETE
# ============================================================

async def get_available_dates_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete for available dates in database"""
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        c.execute("SELECT DISTINCT data_date FROM season_progress ORDER BY data_date DESC LIMIT 100")
        all_dates = [row[0] for row in c.fetchall()]
        conn.close()
        
        # Filter dates that match current input
        filtered = [d for d in all_dates if d.startswith(current)] if current else all_dates[:25]
        
        return [app_commands.Choice(name=d, value=d) for d in filtered[:25]]
    except:
        return []

@bot.tree.command(name="gain", description="View gains between specific dates with autocomplete")
@app_commands.describe(
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
    user="Member name (optional)"
)
@app_commands.autocomplete(start_date=get_available_dates_autocomplete)
@app_commands.autocomplete(end_date=get_available_dates_autocomplete)
async def gain(interaction: discord.Interaction, start_date: str, end_date: str, user: str = None):
    """View gains between specific dates with autocomplete"""
    await interaction.response.defer()
    
    try:
        # Get account ID
        account_id = await get_account_id_from_input(interaction, user)
        if not account_id:
            return await interaction.followup.send("❌ Could not find account ID.")
        
        # Query dates within range
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        c.execute(
            "SELECT DISTINCT data_date FROM season_progress WHERE account_id=? AND data_date BETWEEN ? AND ? ORDER BY data_date ASC",
            (account_id, start_date, end_date)
        )
        dates = [row[0] for row in c.fetchall()]
        c.execute("SELECT DISTINCT season_id FROM season_progress WHERE account_id=? ORDER BY season_id DESC LIMIT 1", (account_id,))
        season_row = c.fetchone()
        conn.close()
        
        if not dates:
            return await interaction.followup.send(f"❌ No data found between {start_date} and {end_date}")
        
        # Get season_id for gains calculation
        season_id = season_row[0] if season_row else None
        
        # Create embed
        embed = discord.Embed(
            title="📊 Gains Calculator",
            description=f"**Date Range:** {start_date} → {end_date}\nSelect start and end dates to see your gains.",
            color=0x3498db
        )
        embed.add_field(name="📅 Available dates", value=f"{len(dates)} days of data", inline=False)
        embed.add_field(name="ℹ️", value="Both dropdowns must be selected before clicking **Show Gains**", inline=False)
        
        # Show date selector
        view = GainsDateSelector(dates, account_id, season_id, dates[0], interaction)
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        log_error(f"[GAIN] Error: {e}")
        await interaction.followup.send("❌ Error loading data. Try again later.")


# ============================================================
# SAFE LOGIN (NO bot.run)
# ============================================================

async def safe_login():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        log_info("❌ Missing DISCORD_BOT_TOKEN")
        return

    while True:
        try:
            await bot.start(token)
            break

        except discord.HTTPException as e:
            if e.status == 429:
                # HARD COOLDOWN on rate limit
                log_info("⛔ Discord rate-limited login. Cooling down for 15 minutes.")
                await asyncio.sleep(900)  # 15 minutes
            else:
                log_info(f"[Login Error] {e}")
                await asyncio.sleep(60)

        except Exception as e:
            log_info(f"[Fatal Login Error] {e}")
            await asyncio.sleep(120)

if __name__ == "__main__":
    asyncio.run(safe_login())

    # KEEP PROCESS ALIVE (REQUIRED FOR KOYEB)
    import time
    while True:
        time.sleep(3600)
