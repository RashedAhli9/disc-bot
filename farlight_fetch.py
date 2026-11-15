"""Download the "Realm Members" Excel from the official Farlight Game Tools site with a headless browser.

Credentials come from the caller (Railway variables) and are never logged. If any step fails, a screenshot and
the visible page text are saved so the owner can see what the page looked like.
"""
import os
import re
import tempfile

BASE = "https://cod-game-tools.farlightgames.com"
MANAGE_URL = f"{BASE}/manageTools?park_header=false&locale=en"
MEMBERS_URL = f"{BASE}/topn"
COMPARE_URL = f"{BASE}/compare"
STEP_TIMEOUT = 30_000


class FetchError(Exception):
    def __init__(self, message, screenshot=None, page_text=None):
        super().__init__(message)
        self.screenshot = screenshot
        self.page_text = page_text


async def _visible(locator, timeout=2500):
    try:
        await locator.first.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False


async def _login_frame(page, timeout_ms=STEP_TIMEOUT):
    """The sign-in popup may live in an iframe: return whichever frame (page or iframe) shows the email box."""
    waited = 0
    while waited <= timeout_ms:
        for frame in page.frames:
            try:
                box = frame.get_by_placeholder("Enter your email address")
                if await box.count() and await box.first.is_visible():
                    return frame
            except Exception:
                continue
        await page.wait_for_timeout(500)
        waited += 500
    return None


async def _login(page, email, password):
    frame = await _login_frame(page, 3000)
    if frame is None:
        # Not logged in and no popup yet: open it from the header
        await page.get_by_text("Log In", exact=False).first.click(timeout=STEP_TIMEOUT)
        frame = await _login_frame(page)
    if frame is None:
        frames = ", ".join(f.url[:60] for f in page.frames)
        raise FetchError(f"The sign-in form never appeared (frames: {frames})")
    # Make sure we are on the password tab (the other tab is the code login)
    tab = frame.get_by_text("Password Login", exact=True)
    if await _visible(tab, 1000):
        await tab.first.click()
    await frame.get_by_placeholder("Enter your email address").first.fill(email)
    await frame.get_by_placeholder("Enter Password").first.fill(password)

    # The agreement is a round tick next to the sentence: click just left of the text
    agree = frame.get_by_text(re.compile(r"I have read and agreed"))
    await agree.first.wait_for(state="visible", timeout=STEP_TIMEOUT)
    box = await agree.first.bounding_box()
    if box:
        await page.mouse.click(box["x"] - 14, box["y"] + min(10, box["height"] / 2))
    await frame.get_by_text("Login", exact=True).last.click(timeout=STEP_TIMEOUT)
    # Either the character card shows straight away, or a "Select Character" popup asks which lord to use
    await page.wait_for_function(
        "() => document.body.innerText.includes('Character ID') || document.body.innerText.includes('Select Character')",
        timeout=STEP_TIMEOUT)
    chooser = page.get_by_text("Select Character").first
    if await _visible(chooser, 1500):
        server = os.getenv("FARLIGHT_SERVER", "375").lstrip("#")
        await page.get_by_text(f"#{server}", exact=True).first.click(timeout=STEP_TIMEOUT)
        await page.get_by_text("Confirm", exact=True).filter(visible=True).last.click(timeout=STEP_TIMEOUT)
    await page.get_by_text("Character ID").first.wait_for(state="visible", timeout=STEP_TIMEOUT)


_FIND_KVK_SEASON_SERVERS_JS = """
() => {
  // Each season on the "Your Realm" tab is: title, In Progress/Finished, date range, a row of small
  // numbers (the server IDs in that KvK), then a "Realm Power Comparison and Analysis" button. Grab the
  // numbers in the first "In Progress" season block.
  const leaves = Array.from(document.querySelectorAll('*')).filter(e => e.children.length === 0);
  const start = leaves.findIndex(e => (e.textContent || '').trim() === 'In Progress');
  if (start === -1) return null;
  const servers = [];
  for (let i = start + 1; i < leaves.length; i++) {
    const t = (leaves[i].textContent || '').trim();
    if (/Realm Power Comparison/i.test(t)) break;
    if (/^In Progress$|^Finished$/.test(t)) break;  // next season block started
    if (/^\d{1,4}$/.test(t)) servers.push(parseInt(t, 10));
  }
  return servers.length ? servers : null;
}
"""


async def fetch_current_kvk_servers(page):
    """Best-effort: the server IDs in the account's currently in-progress KvK, from the "Your Realm" tab of
    the KvK Seasons page. Returns a list of ints, or None if the page didn't look as expected (never raises)."""
    try:
        await page.goto(COMPARE_URL, wait_until="networkidle", timeout=60_000)
        await page.get_by_text("In Progress", exact=True).first.wait_for(state="visible", timeout=15_000)
        servers = await page.evaluate(_FIND_KVK_SEASON_SERVERS_JS)
        return sorted(set(servers)) if servers else None
    except Exception:
        return None


_FIND_DAY_JS = """
([month, day]) => {
  // Walk the calendar in page order; month headers look like 2026/10, days are plain numbers.
  const all = Array.from(document.querySelectorAll('*')).filter(e => e.children.length === 0 && e.offsetParent !== null);
  let cur = null;
  for (const e of all) {
    const t = (e.textContent || '').trim();
    if (/^\\d{4}\\/\\d{2}$/.test(t)) { cur = t; continue; }
    if (cur === month && t === String(day)) {
      e.scrollIntoView({block: 'center'});
      const r = e.getBoundingClientRect();
      return {x: r.x + r.width / 2, y: r.y + r.height / 2};
    }
  }
  return null;
}
"""


async def _click_day(page, iso):
    y, m, d = iso.split("-")
    for _ in range(3):
        pos = await page.evaluate(_FIND_DAY_JS, [f"{y}/{m}", int(d)])
        if pos:
            await page.mouse.click(pos["x"], pos["y"])
            return
        await page.wait_for_timeout(500)
    raise FetchError(f"Couldn't find {iso} in the calendar")


async def _pick_range(page, start_iso, end_iso):
    field = page.get_by_text(re.compile(r"^\d{4}/\d{2}/\d{2}"))
    await field.first.wait_for(state="visible", timeout=STEP_TIMEOUT)
    await field.first.click()
    await page.get_by_text("Select Time").first.wait_for(state="visible", timeout=STEP_TIMEOUT)
    await _click_day(page, start_iso)
    await _click_day(page, end_iso)
    # Several popups carry a "Confirm" button and the hidden ones stay in the page: click the one that shows
    await page.get_by_text("Confirm", exact=True).filter(visible=True).last.click(timeout=STEP_TIMEOUT)
    await page.get_by_text(f"{start_iso.replace('-', '/')}~{end_iso.replace('-', '/')}").first.wait_for(
        state="visible", timeout=STEP_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=STEP_TIMEOUT)


_FIND_DOWNLOAD_JS = """
() => {
  // The download button is the right-most small clickable box on the "Member list" row.
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let label = null;
  while (walker.nextNode()) {
    if (/Member list/i.test(walker.currentNode.textContent || '')) { label = walker.currentNode.parentElement; break; }
  }
  if (!label) return null;
  const ly = label.getBoundingClientRect().y;
  let best = null;
  for (const e of document.querySelectorAll('*')) {
    const r = e.getBoundingClientRect();
    if (r.width < 20 || r.width > 90 || r.height < 20 || r.height > 70) continue;
    if (Math.abs(r.y + r.height / 2 - (ly + 10)) > 45) continue;
    if (!best || r.x > best.x) best = {x: r.x, y: r.y, w: r.width, h: r.height};
  }
  return best ? {x: best.x + best.w / 2, y: best.y + best.h / 2} : null;
}
"""


async def _download(page):
    # After the date range changes the list reloads (spinner, empty page): wait for the table, then the button
    await page.get_by_text("Character ID", exact=True).first.wait_for(state="visible", timeout=60_000)
    pos = None
    for _ in range(40):
        pos = await page.evaluate(_FIND_DOWNLOAD_JS)
        if pos:
            break
        await page.wait_for_timeout(500)
    if not pos:
        raise FetchError("Couldn't find the download button on the Realm Members page")
    async with page.expect_download(timeout=90_000) as dl_info:
        await page.mouse.click(pos["x"], pos["y"])
    download = await dl_info.value
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "export.xlsx")
        await download.save_as(path)
        with open(path, "rb") as f:
            return download.suggested_filename, f.read()


async def fetch_realm_members(email, password, start_iso, end_iso):
    """Returns (filename, xlsx_bytes, kvk_servers). kvk_servers is a sorted list of server IDs in the
    account's current KvK, or None if that page couldn't be read (never blocks the Excel download).
    Raises FetchError (with screenshot + page text when possible) if the Excel itself fails."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(viewport={"width": 1100, "height": 1100}, accept_downloads=True,
                                                locale="en-US")
            page = await context.new_page()
            step = "opening the site"
            try:
                await page.goto(MANAGE_URL, wait_until="networkidle", timeout=60_000)
                step = "logging in"
                await _login(page, email, password)
                kvk_servers = await fetch_current_kvk_servers(page)
                step = "opening Realm Members"
                await page.goto(MEMBERS_URL, wait_until="networkidle", timeout=60_000)
                if not await _visible(page.get_by_text("Member list", exact=False), 8000):
                    raise FetchError("The Realm Members page didn't show its member list")
                step = "choosing the date range"
                await _pick_range(page, start_iso, end_iso)
                step = "downloading the Excel"
                filename, data = await _download(page)
                return filename, data, kvk_servers
            except Exception as e:
                shot = text = None
                try:
                    shot = await page.screenshot(type="png")
                    text = (await page.inner_text("body"))[:1500]
                except Exception:
                    pass
                msg = e.args[0] if isinstance(e, FetchError) else f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
                raise FetchError(f"Failed while {step}: {msg}", shot, text) from None
        finally:
            await browser.close()
