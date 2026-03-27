#!/usr/bin/env python3
"""
DEBUG TOOL: Diagnose gains calculation issues
Helps identify why power_gain and merits show 0 or wrong values
"""

import sqlite3
import sys
from datetime import datetime, date

DB_PROGRESS = "/data/season_progress.db"

def parse_stat(s):
    """Mirror of the parse_stat function from bot.py"""
    if not s:
        return 0
    try:
        val_str = str(s).replace("+", "").replace(",", "")
        return int(val_str) if val_str.lstrip("-").isdigit() else 0
    except:
        return 0

def inspect_database():
    """Show database structure and sample data"""
    print("\n" + "="*60)
    print("DATABASE STRUCTURE INSPECTION")
    print("="*60)
    
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        
        # Check if table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='season_progress';")
        if not c.fetchone():
            print("❌ season_progress table does not exist!")
            return
        
        print("✅ season_progress table exists")
        
        # Get column info
        c.execute("PRAGMA table_info(season_progress);")
        columns = c.fetchall()
        print(f"\n📋 Columns ({len(columns)}):")
        for col_id, name, col_type, notnull, default, pk in columns:
            print(f"  {col_id:2d}. {name:20s} ({col_type})")
        
        # Count rows
        c.execute("SELECT COUNT(*) FROM season_progress;")
        row_count = c.fetchone()[0]
        print(f"\n📊 Total rows: {row_count}")
        
        # Show sample data
        if row_count > 0:
            print("\n📝 SAMPLE DATA (first 3 rows):")
            c.execute("""
                SELECT season_id, account_id, data_date, lord_name, 
                       power_gain, merits, kills_gain
                FROM season_progress 
                ORDER BY created_at DESC 
                LIMIT 3
            """)
            
            for row in c.fetchall():
                season_id, account_id, data_date, lord_name, power_gain, merits, kills_gain = row
                print(f"\n  Season {season_id} | Account {account_id} | Date {data_date}")
                print(f"    Lord: {lord_name}")
                print(f"    power_gain:   {repr(power_gain)}")
                print(f"    merits:       {repr(merits)}")
                print(f"    kills_gain:   {repr(kills_gain)}")
            
            # Group by account and date
            print("\n\n📈 DATA BY ACCOUNT & DATE:")
            c.execute("""
                SELECT account_id, data_date, COUNT(*) as count
                FROM season_progress
                GROUP BY account_id, data_date
                ORDER BY account_id, data_date DESC
                LIMIT 10
            """)
            
            for account_id, data_date, count in c.fetchall():
                print(f"  {account_id} | {data_date} | {count} record(s)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database error: {e}")

def test_parse_stat():
    """Test the parse_stat function with various inputs"""
    print("\n" + "="*60)
    print("PARSE_STAT FUNCTION TEST")
    print("="*60)
    
    test_cases = [
        ("1000", 1000, "Simple number"),
        ("+1000", 1000, "Plus prefix"),
        ("1,000", 1000, "With comma"),
        ("+1,000", 1000, "Plus and comma"),
        ("0", 0, "Zero"),
        ("+0", 0, "Plus zero"),
        (None, 0, "None value"),
        ("", 0, "Empty string"),
        ("-500", -500, "Negative"),
        ("abc", 0, "Invalid string"),
        ("+1,234,567", 1234567, "Large number with commas"),
    ]
    
    print("\nTest Results:")
    all_pass = True
    for input_val, expected, description in test_cases:
        result = parse_stat(input_val)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"{status} {description:30s} | Input: {repr(input_val):20s} | Expected: {expected:10} | Got: {result}")
    
    if all_pass:
        print("\n✅ All parse_stat tests passed!")
    else:
        print("\n❌ Some parse_stat tests failed!")

def simulate_gains_calculation(account_id=None, season_id=1):
    """Simulate a gains calculation with real database data"""
    print("\n" + "="*60)
    print("GAINS CALCULATION SIMULATION")
    print("="*60)
    
    try:
        conn = sqlite3.connect(DB_PROGRESS)
        c = conn.cursor()
        
        # Find an account if not specified
        if not account_id:
            c.execute("SELECT DISTINCT account_id FROM season_progress LIMIT 1;")
            row = c.fetchone()
            if row:
                account_id = row[0]
            else:
                print("❌ No data found in database")
                return
        
        print(f"\n🔍 Account ID: {account_id}")
        
        # Get all dates for this account
        c.execute("""
            SELECT DISTINCT data_date FROM season_progress 
            WHERE season_id=? AND account_id=? 
            ORDER BY data_date ASC
        """, (season_id, account_id))
        
        dates = [row[0] for row in c.fetchall()]
        print(f"📅 Available dates: {len(dates)}")
        
        if len(dates) < 2:
            print("❌ Need at least 2 dates for gains calculation")
            conn.close()
            return
        
        # Use first and last date
        start_date = dates[0]
        end_date = dates[-1]
        
        print(f"\n📊 Calculating gains from {start_date} to {end_date}")
        
        # Get start stats
        c.execute("""
            SELECT power_gain, merits, kills_gain, deads_gain, healed_gain
            FROM season_progress
            WHERE season_id=? AND account_id=? AND data_date=?
        """, (season_id, account_id, start_date))
        
        start_row = c.fetchone()
        if not start_row:
            print(f"❌ No data for start date {start_date}")
            return
        
        start_power, start_merits, start_kills, start_deaths, start_healed = start_row
        
        # Get end stats
        c.execute("""
            SELECT power_gain, merits, kills_gain, deads_gain, healed_gain
            FROM season_progress
            WHERE season_id=? AND account_id=? AND data_date=?
        """, (season_id, account_id, end_date))
        
        end_row = c.fetchone()
        if not end_row:
            print(f"❌ No data for end date {end_date}")
            return
        
        end_power, end_merits, end_kills, end_deaths, end_healed = end_row
        
        # Show raw values
        print(f"\n📍 START DATE: {start_date}")
        print(f"  power_gain (raw):  {repr(start_power)}")
        print(f"  merits (raw):      {repr(start_merits)}")
        print(f"  kills_gain (raw):  {repr(start_kills)}")
        
        print(f"\n📍 END DATE: {end_date}")
        print(f"  power_gain (raw):  {repr(end_power)}")
        print(f"  merits (raw):      {repr(end_merits)}")
        print(f"  kills_gain (raw):  {repr(end_kills)}")
        
        # Parse and calculate
        start_power_int = parse_stat(start_power)
        start_merits_int = parse_stat(start_merits)
        start_kills_int = parse_stat(start_kills)
        
        end_power_int = parse_stat(end_power)
        end_merits_int = parse_stat(end_merits)
        end_kills_int = parse_stat(end_kills)
        
        power_gain = end_power_int - start_power_int
        merits_gain = end_merits_int - start_merits_int
        kills_gain = end_kills_int - start_kills_int
        
        # Show parsed values
        print(f"\n🔢 PARSED VALUES:")
        print(f"  Start power:   {start_power_int:,}")
        print(f"  End power:     {end_power_int:,}")
        print(f"  Power gain:    {power_gain:,}")
        print()
        print(f"  Start merits:  {start_merits_int:,}")
        print(f"  End merits:    {end_merits_int:,}")
        print(f"  Merits gain:   {merits_gain:,}")
        print()
        print(f"  Start kills:   {start_kills_int:,}")
        print(f"  End kills:     {end_kills_int:,}")
        print(f"  Kills gain:    {kills_gain:,}")
        
        # Issue diagnosis
        print(f"\n🔍 DIAGNOSIS:")
        if power_gain == 0:
            if start_power_int == 0 and end_power_int == 0:
                print("  ⚠️ power_gain is 0 because both start and end are 0 or empty")
            elif start_power_int == end_power_int:
                print("  ⚠️ power_gain is 0 because start and end values are equal")
            else:
                print("  ❌ Unexpected: power_gain is 0 but values differ")
        else:
            print(f"  ✅ power_gain looks correct: {power_gain:,}")
        
        if merits_gain == 0:
            if start_merits_int == 0 and end_merits_int == 0:
                print("  ⚠️ merits_gain is 0 because both start and end are 0 or empty")
            elif start_merits_int == end_merits_int:
                print("  ⚠️ merits_gain is 0 because start and end values are equal")
            else:
                print("  ❌ Unexpected: merits_gain is 0 but values differ")
        else:
            print(f"  ✅ merits_gain looks correct: {merits_gain:,}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║        DISCORD BOT GAINS CALCULATION DEBUG TOOL            ║
╚════════════════════════════════════════════════════════════╝
""")
    
    # Run all diagnostics
    inspect_database()
    test_parse_stat()
    simulate_gains_calculation()
    
    print("\n" + "="*60)
    print("DEBUG COMPLETE")
    print("="*60)
    print("""
📋 NEXT STEPS:

1. If "power_gain showing 0" - check if:
   - Values are being saved to database with correct format
   - parse_stat() is handling the format correctly
   - Start and end dates have data

2. If "merits_gain showing wrong value" - check if:
   - The subtraction is calculating correctly
   - Values are stored as strings or integers
   - Date range selection is correct

3. Check bot logs for [GAINS DEBUG] entries to see raw values

4. Ensure !loadhistory command has been run to populate database
""")

if __name__ == "__main__":
    main()
