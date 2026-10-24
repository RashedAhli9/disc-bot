"""Run: python3 tests/test_parsers.py   (also run by tools/check.py)
Synthetic samples, so no network or real data is needed. If Call of Stats changes its layout, update the
sample here to match the new layout and make the parser pass again BEFORE pushing."""
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PORT", "0")
os.environ.setdefault("DISCORD_BOT_TOKEN", "")

import openpyxl  # noqa: E402
import bot  # noqa: E402


def make_xlsx(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


NEW_HEADERS = ["Character ID", "Character Name", "Current Power", "Historical Highest Power", "Total Merits",
               "Gathering", "Infantry Merits", "Cavalry Merits", "Marksman Merits", "Magic Merits", "Other Merits",
               "T4 Deaths", "T5 Deaths", "T4 Severely Wounded", "T5 Severely Wounded", "Enemy Merits",
               "T4 Healed", "T5 Healed"]
OLD_HEADERS = ["Character ID", "Character Name", "Current Power", "Historical Highest Power", "Total Merits",
               "Gathering", "Infantry Merits", "Cavalry Merits", "Marksman Merits", "Magic Merits", "Other Merits",
               "Deaths (T4/T5)", "Healing (T4/T5)"]


class ServerExcel(unittest.TestCase):
    def test_new_format_sums_split_columns(self):
        data = make_xlsx(NEW_HEADERS, [[111, "Rekz", 198_000_000, 204_150_040, 7_396_977, 5, 430_386, 6_241_626, 1, 2, 3,
                                        10_000, 20_000, 1, 2, 99, 400_000, 1_299_795]])
        rows, err = bot.parse_server_excel(data)
        self.assertIsNone(err)
        r = rows[0]
        self.assertEqual(r["account_id"], "111")
        self.assertEqual(r["current_power"], 198_000_000)
        self.assertEqual(r["highest_power"], 204_150_040)
        self.assertEqual(r["deaths"], 30_000)           # T4 + T5
        self.assertEqual(r["healing"], 1_699_795)       # T4 + T5 healed
        self.assertEqual(r["t5_healed"], 1_299_795)
        self.assertEqual(r["infantry_merits"], 430_386)
        self.assertEqual(r["cavalry_merits"], 6_241_626)

    def test_old_combined_format(self):
        data = make_xlsx(OLD_HEADERS, [[222, "Gato", 1, 2, 3, 4, 5, 6, 7, 8, 9, 78_261, 1_699_795]])
        rows, err = bot.parse_server_excel(data)
        self.assertIsNone(err)
        self.assertEqual(rows[0]["deaths"], 78_261)
        self.assertEqual(rows[0]["healing"], 1_699_795)

    def test_text_numbers_and_blank_rows(self):
        data = make_xlsx(NEW_HEADERS, [[333, "Havi", "1,234", "+5,678", "9,000", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                                       [None] * 18])
        rows, err = bot.parse_server_excel(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["current_power"], 1234)
        self.assertEqual(rows[0]["highest_power"], 5678)

    def test_missing_required_columns_is_an_error(self):
        data = make_xlsx(["Foo", "Bar"], [[1, 2]])
        rows, err = bot.parse_server_excel(data)
        self.assertIsNone(rows)
        self.assertIn("required columns", err)

    def test_garbage_file_is_an_error_not_a_crash(self):
        rows, err = bot.parse_server_excel(b"not an excel file")
        self.assertIsNone(rows)
        self.assertTrue(err)


class Filenames(unittest.TestCase):
    def test_full_name(self):
        self.assertEqual(bot.parse_server_filename("698_2026-07-02_2026-07-13.xlsx"), (698, "2026-07-02", "2026-07-13"))

    def test_server_only(self):
        self.assertEqual(bot.parse_server_filename("698.xlsx"), (698, None, None))

    def test_no_number(self):
        self.assertEqual(bot.parse_server_filename("stats.xlsx"), (None, None, None))


class StatNumbers(unittest.TestCase):
    def test_parse_stat_str(self):
        self.assertEqual(bot._parse_stat_str("+1,234"), 1234)
        self.assertEqual(bot._parse_stat_str(None), 0)
        self.assertEqual(bot._parse_stat_str(55), 55)
        self.assertEqual(bot._parse_stat_str("junk"), 0)

    def test_deads_tiers(self):
        self.assertEqual(bot._parse_deads_tiers("100:1.5,150:3.5,200:5"), [(100.0, 1.5), (150.0, 3.5), (200.0, 5.0)])
        with self.assertRaises(Exception):
            bot._parse_deads_tiers("garbage")


PROFILE_HTML = """
<html><head><title>Lord Profile — Rekz | Call of Stats</title></head><body>
<h1 class="higher-value">
  Rekz
</h1><h2 class="higher-value">[MFD]</h2>
<span class="subtle">Highest Power</span>
<div class="value">+0</div>
<span class="subtle">Merits</span> <div class="value">+7,396,977</div>
<span class="subtle">Units Killed</span><div class="value">+16,312,673</div>
<span class="subtle">Units Dead</span><div class="value">+78,261</div>
</body></html>
"""


class ProfileHtml(unittest.TestCase):
    def test_core_fields(self):
        s = bot.parse_stats(PROFILE_HTML)
        self.assertEqual(s["lord_name"], "Rekz")
        self.assertEqual(s["alliance_tag"], "[MFD]")
        self.assertEqual(s["merits"], "+7,396,977")
        self.assertEqual(s["kills_gain"], "+16,312,673")
        self.assertEqual(s["deads_gain"], "+78,261")

    def test_name_falls_back_to_title(self):
        s = bot.parse_stats(PROFILE_HTML.replace('<h1 class="higher-value">\n  Rekz\n</h1>', ""))
        self.assertEqual(s["lord_name"], "Rekz")

    def test_empty_page_does_not_crash(self):
        s = bot.parse_stats("<html></html>")
        self.assertIsNone(s["merits"])


class Plumbing(unittest.TestCase):
    def test_db_connect_uses_wal(self):
        conn = bot.db_connect(bot.DB)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")

    def test_card_names_with_special_characters_render(self):
        import card_render
        png = card_render.render_leaderboard_card({
            "title": "t", "subtitle": "s", "accent": card_render.RED,
            "rows": [{"name": "꧁༒☬DRAKKEN☬༒꧂", "val": 5}, {"name": "龍王", "val": 3}, {"name": "​", "val": 1}]})
        self.assertGreater(len(png.read()), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=1)
