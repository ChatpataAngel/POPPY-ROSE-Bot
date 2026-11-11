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

WELCOME EVENT FALLBACK + DIAGNOSTICS (v4)
-----------------------------------------
This build registers two independent join paths:

1. ChatMemberHandler.CHAT_MEMBER (primary; Telegram requires the bot to be an
   administrator and the poller explicitly subscribes to chat_member).
2. MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS) (fallback; runs only
   when Telegram includes a new_chat_members service message in the update).

The two paths share duplicate protection so one join should not produce two
welcome posts. The message-capture handler used by /setwelcome explicitly
ignores service messages so a join event cannot accidentally become the
saved welcome media.

Run /welcomecheck inside the target group as an administrator. It reports the
current chat ID, the bot's actual membership status, whether a welcome post is
saved, and the saved post type. The Render logs also record service update
metadata at INFO level without logging user message contents.

IMPORTANT TELEGRAM LIMITATION:
The new_chat_members fallback is best-effort. Telegram may omit these service
messages in some supergroups. For dependable chat_member updates, POPPY ROSE
must be an administrator in that exact group. The /welcomecheck command is
provided to verify the current status. If its output says the bot is not an
administrator, promote it and test again.

After deploying, run /welcomecheck, then have a genuinely new account join.
Expected relevant logs include UPDATE_RECEIVED with service_kind=new_chat_members
and/or CHAT_MEMBER_UPDATE_RECEIVED, followed by MEMBER_JOIN_DETECTED and
WELCOME_SENT. If there is no membership log at all, verify the bot's admin
status, group ID, and that exactly one Render poller owns the token.
