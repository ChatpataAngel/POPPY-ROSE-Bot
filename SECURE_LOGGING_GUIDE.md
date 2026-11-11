# POPPY ROSE — Secure Logging and Welcome Diagnostics

## What changed

- All Python console log records use a redacting formatter, including formatted arguments and exception tracebacks.
- Telegram API success-request logs (`httpx`/`httpcore`) are reduced to WARNING because those request URLs include the bot token.
- Telegram bot tokens, MongoDB/PostgreSQL/MySQL connection strings, bearer credentials, common API-key/secret/password fields, GitHub tokens, and AWS access-key IDs are masked before console output.
- `/api/status` and `/ping` error summaries are sanitized before storage or display.
- Welcome/goodbye handling now logs each received membership transition, status change, configuration lookup, and send result without logging message contents or credentials.
- Normal polling no longer discards pending Telegram updates on restart.

## Render environment

Set:

```text
LOG_LEVEL=INFO
```

Use `LOG_LEVEL=DEBUG` temporarily only when diagnosing a problem. Return to `INFO` afterwards.

## How to diagnose a welcome failure

After deployment, have a genuinely new account join the group and inspect Render logs:

1. `HANDLERS_REGISTERED` — membership and bot-status handlers were registered.
2. `Telegram polling started` — this Render instance became the active poller (HA mode).
3. `BOT_MEMBERSHIP_STATUS_CHANGED` — Telegram reported a change to the bot's own group status; `BOT_NOT_ADMIN` means administrator status needs attention.
4. `CHAT_MEMBER_UPDATE_RECEIVED` — Telegram delivered a membership update to the bot.
5. `MEMBER_JOIN_DETECTED` — the status transition qualifies as a join.
6. `WELCOME_LOOKUP_STARTED` — the bot checked the saved welcome for that group.
7. `WELCOME_SENT` — Telegram accepted the welcome message.

Common outcomes:

- No `CHAT_MEMBER_UPDATE_RECEIVED`: verify bot administrator status, the exact group, the active poller, and that only one service is polling the token.
- `WELCOME_NOT_CONFIGURED`: run `/setwelcome` in that same group and send the welcome post as the next message.
- `WELCOME_SEND_FAILED`: inspect the Telegram error class and traceback; check the bot has permission to send messages and that the saved media/message is still valid.

## Security limitations

Redaction is defense in depth, not a guarantee that arbitrary unknown secret formats can never be logged. Never log environment variables, request headers, bot objects, raw configuration dictionaries, or message contents. Do not paste credentials into support chats. Revoke any credential previously exposed and replace it in Render.

## Welcome-event troubleshooting (v4)

Run `/welcomecheck` in the affected group. It checks the bot's current Telegram
membership status and the saved welcome setting. The service-message fallback
is also registered and logs `NEW_CHAT_MEMBERS_SERVICE_UPDATE_RECEIVED` when
Telegram includes that service update. It is a fallback, not a replacement for
being an administrator: Telegram may omit such service messages in some
supergroups, while `chat_member` updates require administrator status.
