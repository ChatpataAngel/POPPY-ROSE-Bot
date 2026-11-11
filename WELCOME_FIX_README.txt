POPPY ROSE — membership update fix

Main fix:
- Explicitly requests Telegram's chat_member updates using Update.ALL_TYPES
  in BOTH normal polling and the Render HA leader polling path.
- Stops dropping queued updates every time a poller starts.
- Handles restricted members who join with is_member=True.
- Logs welcome/goodbye send failures instead of silently swallowing them.

REQUIRED TELEGRAM CONFIGURATION:
1. The bot MUST be an administrator in the target supergroup.
2. In BotFather, run /setprivacy and disable privacy for this bot if it is
   not already disabled. (This is not the primary requirement for
   chat_member updates, but helps if the bot also relies on ordinary group
   messages; admin status is the key requirement for chat_member.)
3. Ensure only ONE active polling service uses this bot token. If you have
   four Render services, keep HA_ENABLED=true and ensure they all share the
   same MongoDB database and each has a unique INSTANCE_ID. Do not deploy a
   second unrelated service with the same token.
4. After deploying, run /setwelcome in the discussion group and send the
   desired welcome post as the next message.

VERIFY:
- Render logs should show one instance acquiring the poller lease and
  "Telegram polling started".
- When a test account joins, logs should show "Join event received".
- If the event log appears but sending fails, inspect the following
  "Failed to send welcome" traceback; it will show the Telegram API error.
- If no join event appears, confirm the bot is admin in the exact group,
  the new build is deployed, and no other process is consuming the token.

Do not share BOT_TOKEN, MONGO_DB_URI, or dashboard secrets in screenshots.
