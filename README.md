# Tashi Meetings Bot

A Discord bot that lets team leads schedule meetings, notifies members via DM,
and sends automatic reminders 1 hour and 5 minutes before the meeting starts.

---

## How It Works

1. Team lead types `!schedulemeeting` in any channel (or DM)
2. Bot opens a DM with the lead and asks 4 questions:
   - Meeting topic
   - Date (DD/MM/YYYY)
   - Time (HH:MM or H:MM AM/PM, Karachi time)
   - Agenda/notes (optional)
3. Lead confirms → bot sends invites to all their members via DM
4. **1 hour before** → bot sends a reminder to everyone
5. **5 minutes before** → bot generates a Google Meet link and sends it to everyone

---

## Commands

| Command | Who | Description |
|---|---|---|
| `!schedulemeeting` | Team leads | Start scheduling a new meeting |
| `!mymeetings` | Team leads | View all your upcoming meetings |
| `!cancelmeeting <ID>` | Team leads | Cancel a meeting by its ID |
| `!meethelp` | Anyone | Show command list |

---

## Deploy on Railway

1. Push this folder to a GitHub repo
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Add this environment variable in Railway's **Variables** tab:

| Variable | Value |
|---|---|
| `DISCORD_MEETING_BOT_TOKEN` | Your bot token from Discord Developer Portal |

4. Railway auto-detects Python and runs `python meeting_bot.py`

---

## Discord Bot Setup

1. Go to https://discord.com/developers/applications
2. Open your **Tashi Meetings** app → **Bot**
3. Enable these **Privileged Gateway Intents**:
   - ✅ Server Members Intent
   - ✅ Message Content Intent
4. Under **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Permissions: `Send Messages`, `Read Message History`
5. Use the URL to invite the bot to your server

> The bot only sends DMs — it never posts in channels or threads.

---

## Notes

- Meetings are stored in memory. If the bot restarts, pending reminders are lost.
  For production use, add a database (SQLite/PostgreSQL) to persist meetings.
- The Google Meet link generated is a formatted unique URL.
  For real Meet links, integrate the Google Calendar API.
