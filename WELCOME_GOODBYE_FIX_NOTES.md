POPPY ROSE — Welcome/Goodbye Fix
================================

What was fixed
--------------
1. Both polling modes now explicitly subscribe to Telegram's full update list
   (`Update.ALL_TYPES`). Telegram does not include `chat_member` updates in its
   default update subscription, so the previous configuration could miss every
   group join/leave event.
2. The multi-instance Render leader-election polling path is fixed as well as
   the single-instance polling path. This matters because this project defaults
   to HA_ENABLED=true and normally starts polling through src/utils/lease.py.
3. Pending Telegram updates are no longer deliberately discarded at each
   polling start/restart (`drop_pending_updates=False`).
4. Restricted members who are actually in the group are handled as joins;
   restricted members who are no longer in the group are handled as leaves.
5. Telegram send failures are now written to Render logs instead of being
   silently swallowed.

Deploy on Render
----------------
1. Back up the current GitHub repository.
2. Replace the repository files with the contents of this ZIP, or upload the
   changed files while preserving your existing environment variables.
3. Commit and push the changes to the branch connected to Render.
4. In Render, open the POPPY ROSE service and use Manual Deploy → Deploy latest
   commit (or wait for the connected Git push to deploy).
5. Wait until the service is Live. Check Logs for the startup line and ensure
   there are no Telegram 409 Conflict errors or MongoDB connection errors.
6. If you run multiple Render services with the same bot token, deploy the same
   code to every instance. They must share BOT_TOKEN, MONGO_DB_URI and DB_NAME,
   but each must have a unique INSTANCE_ID. Only one instance should report
   that it is LEADER and has Telegram polling started; the others should be
   STANDBY. Never run two independent pollers with the same bot token.

Telegram group requirements
---------------------------
1. Add the bot to the target group and promote it to administrator.
2. Ensure it has permission to send messages (and media, if the welcome post
   contains media). Telegram requires the bot to be an administrator to receive
   all `chat_member` updates.
3. In the group, run /setwelcome as an administrator and send the actual
   welcome post as the next message in that same group.
4. Confirm the bot replies that the welcome post was saved successfully.
5. Test with a different Telegram account joining the group. A bot cannot
   reliably test a new-member greeting by having an existing member simply
   send a message.
6. To configure farewell, use /setgoodbye and send the post. Use /setwelcome off
   or /setgoodbye off to disable either feature.

Verification limits
-------------------
The source can be syntax-checked locally, but actual delivery must be verified
against your live Telegram bot, Render service, group permissions and MongoDB.
No live Render or Telegram account was accessed during this repair.

Security warning
----------------
The uploaded archive contained local environment files (including .env and
multiple .env.render* files) and a frontend .env inside a nested ZIP. Those
files were excluded from this repaired ZIP. Treat any credentials previously
inside those files as exposed: rotate the Telegram bot token through BotFather,
rotate the MongoDB database user's password/connection URI, and replace the
Dashboard API key in Render. Do not commit .env files; keep secrets only in
Render Environment settings. Use the included .env.example files as templates.
