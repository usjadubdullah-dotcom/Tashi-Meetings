"""
Discord Meeting Bot — Tashi Meetings
======================================
Team leads schedule meetings via !schedulemeeting command (DM or any channel).
Bot collects meeting details, notifies all assigned members via DM.
Sends a 1-hour reminder and a 5-minute reminder with a Google Meet link.

Deploy on: Railway / Render / any VPS (NOT Vercel)
"""

import discord
import os
import asyncio
import logging
import uuid
from discord.ext import commands
from datetime import datetime, timedelta
import pytz

# ═══════════════════════════════════════════════════════════════════════════════
#                            C O N F I G U R A T I O N
# ═══════════════════════════════════════════════════════════════════════════════

# ── Bot token (set as environment variable on Railway) ─────────────────────────
BOT_TOKEN = os.getenv("DISCORD_MEETING_BOT_TOKEN")

# ── Timezone ───────────────────────────────────────────────────────────────────
TIMEZONE = pytz.timezone("Asia/Karachi")

# ── Team Leads ─────────────────────────────────────────────────────────────────
TEAM_LEADS = {
    "tashi": {"display_name": "tashitechnologies", "user_id": 1434957366578643074},
    "asjad":  {"display_name": "ussjad",           "user_id": 1463220939151114460},
    "sarah":  {"display_name": "delta",            "user_id": 1301504724062699600},
}

# ── Members ────────────────────────────────────────────────────────────────────
MEMBER_CONFIG = {

    # ── Tashi's members ────────────────────────────────────────────────────────
    1463220939151114460: {"name": "Asjad",   "team_lead": "tashi"},
    1301504724062699600: {"name": "Sarah",   "team_lead": "tashi"},

    # ── Sarah's members ────────────────────────────────────────────────────────
    1462175465652490334: {"name": "Hannan",  "team_lead": "sarah"},
    1450779717916561468: {"name": "Ayan",    "team_lead": "sarah"},
    1221024470454632558: {"name": "Aaimlik", "team_lead": "sarah"},
    1478538357188460625: {"name": "Seroosh", "team_lead": "sarah"},

    # ── Asjad's members ────────────────────────────────────────────────────────
    1298681291633328188: {"name": "Amna",    "team_lead": "asjad"},
    907733451053105152:  {"name": "Kashif",  "team_lead": "asjad"},
}

# ═══════════════════════════════════════════════════════════════════════════════
#  END OF CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("MeetingBot")

# ── Bot setup ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Tracks leads currently going through the scheduling conversation
active_schedulers: set[int] = set()

# In-memory store of all scheduled meetings: { meeting_id: meeting_dict }
scheduled_meetings: dict[str, dict] = {}


# ═══════════════════════════════════════════════════════════════════════════════
#                              H E L P E R S
# ═══════════════════════════════════════════════════════════════════════════════

def get_lead_key_by_user_id(user_id: int) -> str:
    for key, cfg in TEAM_LEADS.items():
        if cfg["user_id"] == user_id:
            return key
    return ""

def is_team_lead(user_id: int) -> bool:
    return any(cfg["user_id"] == user_id for cfg in TEAM_LEADS.values())

def get_my_members(lead_user_id: int) -> list[int]:
    lead_key = get_lead_key_by_user_id(lead_user_id)
    return [uid for uid, cfg in MEMBER_CONFIG.items() if cfg["team_lead"] == lead_key]

def get_lead_display_name(lead_user_id: int) -> str:
    key = get_lead_key_by_user_id(lead_user_id)
    return TEAM_LEADS.get(key, {}).get("display_name", "Your Team Lead")

def generate_meet_link() -> str:
    """Generates a unique Google Meet-style link."""
    code = uuid.uuid4().hex[:10]
    formatted = f"{code[:3]}-{code[3:7]}-{code[7:]}"
    return f"https://meet.google.com/{formatted}"

def is_any_team_lead():
    """Command check: only configured team leads may use scheduling commands."""
    async def predicate(ctx: commands.Context) -> bool:
        if is_team_lead(ctx.author.id):
            return True
        await ctx.send("❌ You don't have permission to use this command.")
        return False
    return commands.check(predicate)


# ═══════════════════════════════════════════════════════════════════════════════
#                     M E E T I N G   S C H E D U L E R
# ═══════════════════════════════════════════════════════════════════════════════

async def ask(channel, question: str, author_id: int, timeout: int = 120) -> str | None:
    """
    Sends a question and waits for the lead's reply in the same channel.
    Returns the message content or None on timeout.
    """
    await channel.send(question)

    def check(m: discord.Message):
        return m.author.id == author_id and m.channel.id == channel.id

    try:
        msg = await bot.wait_for("message", check=check, timeout=timeout)
        return msg.content.strip()
    except asyncio.TimeoutError:
        await channel.send(
            "⏰ **No response received.** Scheduling session cancelled. "
            "Run `!schedulemeeting` again whenever you're ready."
        )
        return None


def parse_datetime(date_str: str, time_str: str) -> datetime | None:
    """
    Tries to parse a date + time string into a timezone-aware datetime.
    Accepts formats: DD/MM/YYYY or DD-MM-YYYY, and HH:MM (24h) or H:MM AM/PM.
    """
    date_str = date_str.strip()
    time_str = time_str.strip()

    date_formats = ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]
    time_formats = ["%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"]

    parsed_date = None
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt).date()
            break
        except ValueError:
            continue

    if not parsed_date:
        return None

    parsed_time = None
    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(time_str.upper(), fmt).time()
            break
        except ValueError:
            continue

    if not parsed_time:
        return None

    naive = datetime.combine(parsed_date, parsed_time)
    return TIMEZONE.localize(naive)


# ── Main scheduling conversation ───────────────────────────────────────────────

@bot.command(name="schedulemeeting")
@is_any_team_lead()
async def schedule_meeting(ctx: commands.Context):
    """
    Starts a conversational meeting scheduler in DM with the team lead.
    Collects: topic, date, time, optional agenda/notes.
    Then notifies all their members and schedules reminders.
    """
    lead = ctx.author

    if lead.id in active_schedulers:
        await ctx.send("⚠️ You already have an active scheduling session in your DMs. Please complete or cancel it first.")
        return

    active_schedulers.add(lead.id)

    # Always conduct the conversation in DM
    try:
        dm = await lead.create_dm()
    except discord.Forbidden:
        await ctx.send("❌ I couldn't open a DM with you. Please enable DMs and try again.")
        active_schedulers.discard(lead.id)
        return

    if ctx.guild:
        await ctx.send(f"✅ I've sent you a DM to collect the meeting details, {lead.display_name}!")

    await dm.send(
        f"📅 **Let's schedule a meeting for your team!**\n"
        f"I'll ask you a few quick questions. You have **2 minutes** to answer each one.\n"
        f"Type `cancel` at any time to stop.\n"
        f"{'─' * 40}"
    )

    try:
        # ── Step 1: Topic ──────────────────────────────────────────────────────
        topic = await ask(dm, "**1️⃣  What is the meeting topic or title?**\n_(e.g. Weekly Sprint Review, Design Sync)_", lead.id)
        if not topic or topic.lower() == "cancel":
            await dm.send("🚫 Scheduling cancelled.")
            return

        # ── Step 2: Date ───────────────────────────────────────────────────────
        while True:
            date_raw = await ask(
                dm,
                "**2️⃣  What date is the meeting?**\n_(Format: `DD/MM/YYYY` — e.g. `25/07/2025`)_",
                lead.id,
            )
            if not date_raw or date_raw.lower() == "cancel":
                await dm.send("🚫 Scheduling cancelled.")
                return

            # Quick sanity check on date format before combining with time
            from datetime import datetime as _dt
            valid_date = False
            for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]:
                try:
                    _dt.strptime(date_raw.strip(), fmt)
                    valid_date = True
                    break
                except ValueError:
                    pass
            if valid_date:
                break
            await dm.send("⚠️ I couldn't read that date. Please use `DD/MM/YYYY` format (e.g. `25/07/2025`).")

        # ── Step 3: Time ───────────────────────────────────────────────────────
        while True:
            time_raw = await ask(
                dm,
                "**3️⃣  What time is the meeting? (Karachi time)**\n_(Format: `HH:MM` 24-hour or `H:MM AM/PM` — e.g. `14:30` or `2:30 PM`)_",
                lead.id,
            )
            if not time_raw or time_raw.lower() == "cancel":
                await dm.send("🚫 Scheduling cancelled.")
                return

            meeting_dt = parse_datetime(date_raw, time_raw)
            if meeting_dt:
                break
            await dm.send("⚠️ I couldn't read that time. Try `14:30` or `2:30 PM`.")

        # ── Check the meeting is in the future ─────────────────────────────────
        now = datetime.now(TIMEZONE)
        if meeting_dt <= now:
            await dm.send(
                "⚠️ That date and time is already in the past. Scheduling cancelled.\n"
                "Run `!schedulemeeting` again with a future date and time."
            )
            return

        # ── Step 4: Optional agenda ────────────────────────────────────────────
        agenda_raw = await ask(
            dm,
            "**4️⃣  Any agenda or notes to share with the team?** _(optional)_\n"
            "Type your notes, or type `skip` to leave this blank.",
            lead.id,
        )
        if agenda_raw is None or agenda_raw.lower() == "cancel":
            await dm.send("🚫 Scheduling cancelled.")
            return
        agenda = None if agenda_raw.lower() == "skip" else agenda_raw

        # ── Confirmation ───────────────────────────────────────────────────────
        formatted_dt = meeting_dt.strftime("%A, %d %B %Y at %I:%M %p")
        agenda_line  = f"\n📋 **Agenda:** {agenda}" if agenda else ""
        members      = get_my_members(lead.id)
        count        = len(members)
        noun         = "member" if count == 1 else "members"

        confirm = await ask(
            dm,
            f"✅ **Here's your meeting summary:**\n\n"
            f"📌 **Topic:** {topic}\n"
            f"📅 **Date & Time:** {formatted_dt} (PKT){agenda_line}\n"
            f"👥 **Notifying:** {count} {noun}\n\n"
            f"Type **`confirm`** to schedule, or **`cancel`** to discard.",
            lead.id,
        )
        if not confirm or confirm.lower() != "confirm":
            await dm.send("🚫 Scheduling cancelled. Run `!schedulemeeting` to start again.")
            return

        # ── Save meeting & kick off reminders ──────────────────────────────────
        meeting_id = uuid.uuid4().hex[:8].upper()
        meeting = {
            "id":          meeting_id,
            "topic":       topic,
            "datetime":    meeting_dt,
            "agenda":      agenda,
            "lead_id":     lead.id,
            "lead_name":   get_lead_display_name(lead.id),
            "member_ids":  members,
        }
        scheduled_meetings[meeting_id] = meeting

        await dm.send(
            f"🎉 **Meeting scheduled successfully!**\n"
            f"**Meeting ID:** `{meeting_id}`\n"
            f"Your team will receive their invites now, "
            f"plus reminders **1 hour** and **5 minutes** before the meeting.\n"
            f"Use `!cancelmeeting {meeting_id}` to cancel it at any time."
        )
        log.info("Meeting %s scheduled by lead %s for %s", meeting_id, lead.name, formatted_dt)

        # Send notifications and schedule reminders
        await notify_meeting_scheduled(meeting)
        bot.loop.create_task(schedule_reminders(meeting))

    finally:
        active_schedulers.discard(lead.id)


# ═══════════════════════════════════════════════════════════════════════════════
#                     N O T I F I C A T I O N S
# ═══════════════════════════════════════════════════════════════════════════════

def build_meeting_card(meeting: dict, headline: str) -> str:
    """Builds a consistent formatted meeting info block."""
    dt: datetime = meeting["datetime"]
    formatted_dt = dt.strftime("%A, %d %B %Y")
    formatted_tm = dt.strftime("%I:%M %p")
    agenda_line  = f"\n📋 **Agenda:** {meeting['agenda']}" if meeting.get("agenda") else ""
    id_line      = f"\n🔖 **Meeting ID:** `{meeting['id']}`"

    return (
        f"{headline}\n\n"
        f"📌 **Topic:** {meeting['topic']}\n"
        f"📅 **Date:** {formatted_dt}\n"
        f"🕐 **Time:** **{formatted_tm}** (Pakistan Standard Time){agenda_line}"
        f"{id_line}"
    )


async def dm_user(user_id: int, message: str, view=None):
    """Helper to DM a user by ID safely."""
    try:
        user = await bot.fetch_user(user_id)
        dm   = await user.create_dm()
        if view:
            await dm.send(message, view=view)
        else:
            await dm.send(message)
        return True
    except discord.NotFound:
        log.warning("User %d not found — could not DM.", user_id)
    except discord.Forbidden:
        log.warning("Cannot DM user %d (DMs disabled?).", user_id)
    except Exception as e:
        log.error("Failed to DM user %d: %s", user_id, e)
    return False


async def notify_meeting_scheduled(meeting: dict):
    """Sends the initial meeting invite to all members and confirms to the lead."""
    dt: datetime     = meeting["datetime"]
    formatted_dt     = dt.strftime("%A, %d %B %Y at %I:%M %p")
    lead_display     = meeting["lead_name"]

    # ── Notify each member ─────────────────────────────────────────────────────
    member_msg = build_meeting_card(
        meeting,
        f"📣 **You have a new meeting scheduled by {lead_display}!**"
    )
    member_msg += (
        f"\n\n⏰ You'll receive a reminder **1 hour** before and a **meeting link 5 minutes** before it starts.\n"
        f"{'─' * 40}"
    )

    notified = 0
    for uid in meeting["member_ids"]:
        success = await dm_user(uid, member_msg)
        if success:
            notified += 1
            log.info("Meeting invite sent to member %d for meeting %s", uid, meeting["id"])
        await asyncio.sleep(0.5)

    # ── Confirm to lead ────────────────────────────────────────────────────────
    lead_confirm = (
        f"✅ **Invites sent!** {notified}/{len(meeting['member_ids'])} members notified.\n\n"
        + build_meeting_card(meeting, f"📅 **Your scheduled meeting:**")
        + f"\n\n🔔 Reminders will fire automatically **1 hour** and **5 minutes** before."
    )
    await dm_user(meeting["lead_id"], lead_confirm)
    log.info("Meeting %s: %d/%d members notified.", meeting["id"], notified, len(meeting["member_ids"]))


async def send_one_hour_reminder(meeting: dict):
    """Sends the 1-hour reminder to lead and all members."""
    dt: datetime = meeting["datetime"]
    time_str     = dt.strftime("%I:%M %p")

    msg = (
        f"⏰ **1-Hour Reminder!**\n\n"
        f"Your meeting **'{meeting['topic']}'** starts in **1 hour** at **{time_str} PKT**.\n"
        f"📅 **Date:** {dt.strftime('%A, %d %B %Y')}\n"
        f"🔖 **Meeting ID:** `{meeting['id']}`\n\n"
        f"Please wrap up your current work and get ready to join. 🙌\n"
        f"{'─' * 40}"
    )

    all_recipients = [meeting["lead_id"]] + meeting["member_ids"]
    for uid in all_recipients:
        await dm_user(uid, msg)
        await asyncio.sleep(0.5)

    log.info("1-hour reminder sent for meeting %s", meeting["id"])


async def send_five_minute_reminder(meeting: dict):
    """Generates a Meet link and sends the 5-minute reminder to lead and all members."""
    dt: datetime = meeting["datetime"]
    time_str     = dt.strftime("%I:%M %p")
    meet_link    = generate_meet_link()

    # Save the link back into the meeting record
    meeting["meet_link"] = meet_link

    msg = (
        f"🚀 **Meeting Starting in 5 Minutes!**\n\n"
        f"📌 **Topic:** {meeting['topic']}\n"
        f"🕐 **Time:** **{time_str} PKT**\n"
        f"🔗 **Join Link:** {meet_link}\n\n"
        f"**Click the link above to join now. See you there! 👋**\n"
        f"{'─' * 40}"
    )

    all_recipients = [meeting["lead_id"]] + meeting["member_ids"]
    for uid in all_recipients:
        await dm_user(uid, msg)
        await asyncio.sleep(0.5)

    log.info("5-minute reminder + Meet link sent for meeting %s: %s", meeting["id"], meet_link)


# ═══════════════════════════════════════════════════════════════════════════════
#                     R E M I N D E R   S C H E D U L E R
# ═══════════════════════════════════════════════════════════════════════════════

async def schedule_reminders(meeting: dict):
    """
    Waits until 1 hour before the meeting → sends reminder.
    Waits until 5 minutes before the meeting → sends link + reminder.
    Cleans up the meeting record afterward.
    """
    meeting_id = meeting["id"]
    meeting_dt: datetime = meeting["datetime"]
    now = datetime.now(TIMEZONE)

    one_hour_before  = meeting_dt - timedelta(hours=1)
    five_mins_before = meeting_dt - timedelta(minutes=5)

    # ── 1-hour reminder ────────────────────────────────────────────────────────
    wait_1h = (one_hour_before - now).total_seconds()
    if wait_1h > 0:
        log.info("Meeting %s: 1-hour reminder fires in %.0f seconds.", meeting_id, wait_1h)
        await asyncio.sleep(wait_1h)
        if meeting_id in scheduled_meetings:   # still not cancelled
            await send_one_hour_reminder(meeting)
    else:
        log.info("Meeting %s: 1-hour window already passed, skipping that reminder.", meeting_id)

    # ── 5-minute reminder ──────────────────────────────────────────────────────
    now = datetime.now(TIMEZONE)
    wait_5m = (five_mins_before - now).total_seconds()
    if wait_5m > 0:
        log.info("Meeting %s: 5-minute reminder fires in %.0f seconds.", meeting_id, wait_5m)
        await asyncio.sleep(wait_5m)
        if meeting_id in scheduled_meetings:   # still not cancelled
            await send_five_minute_reminder(meeting)
    else:
        log.info("Meeting %s: 5-minute window already passed, skipping that reminder.", meeting_id)

    # ── Cleanup ────────────────────────────────────────────────────────────────
    scheduled_meetings.pop(meeting_id, None)
    log.info("Meeting %s completed and removed from schedule.", meeting_id)


# ═══════════════════════════════════════════════════════════════════════════════
#                         A D M I N   C O M M A N D S
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="cancelmeeting")
@is_any_team_lead()
async def cancel_meeting(ctx: commands.Context, meeting_id: str = ""):
    """
    Cancels a scheduled meeting by its ID.
    Only the lead who created the meeting can cancel it.
    Usage: !cancelmeeting <MEETING_ID>
    """
    if not meeting_id:
        await ctx.send("⚠️ Please provide the meeting ID.\nUsage: `!cancelmeeting <MEETING_ID>`")
        return

    meeting_id = meeting_id.upper()
    meeting    = scheduled_meetings.get(meeting_id)

    if not meeting:
        await ctx.send(f"❌ No active meeting found with ID `{meeting_id}`.")
        return

    if meeting["lead_id"] != ctx.author.id:
        await ctx.send("❌ You can only cancel meetings that you scheduled.")
        return

    # Remove from store — the reminder task will see it's gone and skip
    del scheduled_meetings[meeting_id]

    dt: datetime = meeting["datetime"]
    formatted_dt = dt.strftime("%A, %d %B %Y at %I:%M %p")

    # Notify all members of cancellation
    cancel_msg = (
        f"❌ **Meeting Cancelled**\n\n"
        f"📌 **Topic:** {meeting['topic']}\n"
        f"📅 **Was scheduled for:** {formatted_dt} PKT\n"
        f"🔖 **Meeting ID:** `{meeting_id}`\n\n"
        f"This meeting has been cancelled by **{meeting['lead_name']}**.\n"
        f"{'─' * 40}"
    )

    for uid in meeting["member_ids"]:
        await dm_user(uid, cancel_msg)
        await asyncio.sleep(0.5)

    await ctx.send(
        f"✅ **Meeting `{meeting_id}` cancelled.**\n"
        f"All {len(meeting['member_ids'])} member(s) have been notified."
    )
    log.info("Meeting %s cancelled by lead %s", meeting_id, ctx.author.name)


@bot.command(name="mymeetings")
@is_any_team_lead()
async def my_meetings(ctx: commands.Context):
    """
    Lists all upcoming meetings scheduled by the lead who runs this command.
    """
    lead_meetings = [
        m for m in scheduled_meetings.values()
        if m["lead_id"] == ctx.author.id
    ]

    if not lead_meetings:
        await ctx.send("📭 You have no upcoming meetings scheduled.\nUse `!schedulemeeting` to create one.")
        return

    lead_meetings.sort(key=lambda m: m["datetime"])
    lines = []
    for m in lead_meetings:
        dt_str = m["datetime"].strftime("%d %b %Y • %I:%M %p")
        lines.append(f"🔖 `{m['id']}` — **{m['topic']}** — {dt_str} PKT")

    await ctx.send(
        f"📅 **Your upcoming meetings ({len(lead_meetings)}):**\n"
        + "\n".join(lines)
        + "\n\nTo cancel one: `!cancelmeeting <MEETING_ID>`"
    )


@bot.command(name="meethelp")
async def meet_help(ctx: commands.Context):
    """Shows available commands."""
    await ctx.send(
        "📖 **Tashi Meetings Bot — Commands**\n\n"
        "`!schedulemeeting` — Schedule a new meeting with your team _(team leads only)_\n"
        "`!mymeetings` — View all your upcoming meetings _(team leads only)_\n"
        "`!cancelmeeting <ID>` — Cancel a meeting by its ID _(team leads only)_\n"
        "`!meethelp` — Show this help message\n\n"
        "📌 All notifications are sent via **DM** — no group messages."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#                              B O T   E V E N T S
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    log.info("═" * 50)
    log.info("Tashi Meetings Bot is online!")
    log.info("Logged in as: %s (ID: %s)", bot.user, bot.user.id)
    log.info("Timezone: Asia/Karachi (PKT)")
    log.info("Team leads configured: %d", len(TEAM_LEADS))
    log.info("Members configured: %d", len(MEMBER_CONFIG))
    log.info("Use !schedulemeeting to schedule a meeting.")
    log.info("═" * 50)


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CheckFailure):
        pass  # already handled in the check predicate
    elif isinstance(error, commands.CommandNotFound):
        pass  # silently ignore unknown commands
    else:
        log.error("Unhandled command error: %s", error)


# ═══════════════════════════════════════════════════════════════════════════════
#                              E N T R Y   P O I N T
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not BOT_TOKEN:
        log.error("DISCORD_MEETING_BOT_TOKEN environment variable is not set. Exiting.")
        exit(1)
    bot.run(BOT_TOKEN)
