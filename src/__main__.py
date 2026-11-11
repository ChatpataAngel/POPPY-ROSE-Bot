"""POPPY ROSE application entry point."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict

from telegram import (
    Update,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    BOT_NAME,
    BOT_TOKEN,
    HA_ENABLED,
    INSTANCE_ID,
    LOG_LEVEL,
    OWNER_ID,
    validate_config,
)

from src.database.db_core import (
    close_db,
    get_owner_ids,
    init_db,
    ping_db,
    register_group,
    register_user,
)

from src.keep_alive import (
    STATE,
    keep_alive,
)

from src.modules.greetings_broadcast import (
    greet_broadcast_handlers,
    greet_message_handlers,
    member_handlers,
)

from src.modules.locks_purge import (
    locks_purge_handlers,
    lock_filter_handlers,
)

from src.modules.management import (
    management_handlers,
)

from src.modules.moderation import (
    mod_handlers,
)

from src.modules.notes import (
    note_handlers,
)

from src.modules.ui_menu import (
    ui_handlers,
)

from src.utils.status import (
    record_error,
)

from src.utils.lease import (
    leader_loop,
)


logging.basicConfig(
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    ),
    level=getattr(
        logging,
        LOG_LEVEL,
        logging.INFO,
    ),
)

log = logging.getLogger("poppy_rose")


_seen_users: OrderedDict[int, None] = OrderedDict()
_seen_groups: OrderedDict[int, None] = OrderedDict()

_MAX_SEEN_USERS = 10_000
_MAX_SEEN_GROUPS = 2_000


def _remember(
    cache: OrderedDict[int, None],
    key: int,
    limit: int,
) -> bool:

    if key in cache:
        cache.move_to_end(key)
        return False

    cache[key] = None

    if len(cache) > limit:
        cache.popitem(last=False)

    return True


async def tracker(
    update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    chat = update.effective_chat

    if user and _remember(
        _seen_users,
        int(user.id),
        _MAX_SEEN_USERS,
    ):
        try:
            await register_user(user)
        except Exception:
            log.exception(
                "User registration failed | user=%s",
                user.id,
            )

    if (
        chat
        and chat.type != "private"
        and _remember(
            _seen_groups,
            int(chat.id),
            _MAX_SEEN_GROUPS,
        )
    ):
        try:
            await register_group(chat)
        except Exception:
            log.exception(
                "Group registration failed | chat=%s",
                chat.id,
            )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    error = context.error

    # Record it so the /ping command can surface recent errors.
    record_error(
        f"{type(error).__name__}: {error}",
    )

    if isinstance(error, TelegramError):
        log.error(
            "Telegram error: %s",
            error,
        )
    else:
        log.exception(
            "Unhandled update error",
            exc_info=error,
        )


async def post_init(app):
    await init_db()

    if not await ping_db():
        raise RuntimeError(
            "MongoDB is unreachable."
        )

    me = await app.bot.get_me()

    public_private_commands = [
        (
            "start",
            "Open the POPPY ROSE control panel",
        ),
        (
            "help",
            "Show the complete command center",
        ),
        (
            "id",
            "Show your Telegram ID",
        ),
        (
            "myid",
            "Show your Telegram ID",
        ),
        (
            "chatid",
            "Show the current chat ID",
        ),
        (
            "rules",
            "Show group rules",
        ),
        (
            "language",
            "Change language",
        ),
        (
            "ping",
            "Measure latency and errors",
        ),
    ]

    admin_commands = [
        (
            "help",
            "Show the complete command center",
        ),
        (
            "ban",
            "Ban a user",
        ),
        (
            "forceban",
            "Ban a user",
        ),
        (
            "unban",
            "Unban a user",
        ),
        (
            "kick",
            "Kick a user",
        ),
        (
            "mute",
            "Mute a user",
        ),
        (
            "unmute",
            "Unmute a user",
        ),
        (
            "warn",
            "Warn a user",
        ),
        (
            "warnings",
            "Show warnings",
        ),
        (
            "warns",
            "Show warnings",
        ),
        (
            "unwarn",
            "Clear warnings",
        ),
        (
            "clearwarns",
            "Clear warnings",
        ),
        (
            "purge",
            "Purge messages",
        ),
        (
            "spurge",
            "Purge messages",
        ),
        (
            "lock",
            "Lock a content type",
        ),
        (
            "unlock",
            "Unlock a content type",
        ),
        (
            "promote",
            "Promote a member",
        ),
        (
            "demote",
            "Demote an administrator",
        ),
        (
            "pin",
            "Pin a message",
        ),
        (
            "unpin",
            "Unpin a message",
        ),
        (
            "del",
            "Delete a replied message",
        ),
        (
            "info",
            "Show user information",
        ),
        (
            "setwelcome",
            "Configure welcome message",
        ),
        (
            "setgoodbye",
            "Configure goodbye message",
        ),
        (
            "setrules",
            "Set group rules",
        ),
        (
            "save",
            "Save a note",
        ),
        (
            "get",
            "Get a saved note",
        ),
        (
            "delnote",
            "Delete a saved note",
        ),
        (
            "rules",
            "Show group rules",
        ),
        (
            "id",
            "Show your Telegram ID",
        ),
        (
            "myid",
            "Show your Telegram ID",
        ),
        (
            "chatid",
            "Show current chat ID",
        ),
        (
            "ping",
            "Measure latency and errors",
        ),
    ]

    owner_commands = [
        (
            "ownerhelp",
            "Show owner commands",
        ),
        (
            "god",
            "Show owner status",
        ),
        (
            "owners",
            "List global owners",
        ),
        (
            "addowner",
            "Add a global owner",
        ),
        (
            "owneradd",
            "Add a global owner",
        ),
        (
            "delowner",
            "Remove a global owner",
        ),
        (
            "ownerremove",
            "Remove a global owner",
        ),
        (
            "stats",
            "Show bot statistics",
        ),
        (
            "announce",
            "Send owner announcement",
        ),
        (
            "broadcast",
            "Broadcast a message",
        ),
        (
            "setbotname",
            "Change bot display name",
        ),
        (
            "setbotdescription",
            "Change bot description",
        ),
    ]

    await app.bot.set_my_commands(
        public_private_commands,
        scope=BotCommandScopeAllPrivateChats(),
    )

    await app.bot.set_my_commands(
        admin_commands,
        scope=BotCommandScopeAllChatAdministrators(),
    )

    for owner_id in await get_owner_ids():
        try:
            await app.bot.set_my_commands(
                owner_commands,
                scope=BotCommandScopeChat(
                    owner_id,
                ),
            )
        except TelegramError as exc:
            log.warning(
                "Could not set owner command scope | "
                "owner=%s | %s",
                owner_id,
                exc,
            )

    log.info(
        "%s started as @%s | configured_owner=%s",
        BOT_NAME,
        me.username,
        OWNER_ID,
    )

    STATE["bot_username"] = me.username
    STATE["bot_ready"] = True


async def post_shutdown(app):
    STATE["bot_ready"] = False
    await close_db()


# Handler groups (PTB evaluates groups in ascending order and runs at most
# ONE handler per group, but ALL groups are evaluated for every update):
#
#   -10 : usage tracker (must run for every update, never blocks)
#    0  : all command/UI handlers
#    1  : receive_greeting_post  (/setwelcome follow-up capture)
#    2  : filter_locked          (content locks enforcement)
#    3  : on_chat_member         (welcome/goodbye dispatch)
#
# Each catch-all handler sits alone in its own group so it can neither
# shadow nor be shadowed by another catch-all handler.
GROUP_GREETING_CAPTURE = 1
GROUP_LOCK_FILTER = 2
GROUP_MEMBER_EVENTS = 3


def register_handlers(app):
    """Attach every handler (and the error handler) to the application."""

    app.add_handler(
        MessageHandler(
            filters.ALL,
            tracker,
            block=False,
        ),
        group=-10,
    )

    # Command/UI handlers share group 0. They all require a specific
    # command or callback query, so they can never shadow each other.
    app.add_handlers(
        ui_handlers,
    )

    app.add_handlers(
        mod_handlers,
    )

    app.add_handlers(
        greet_broadcast_handlers,
    )

    app.add_handlers(
        locks_purge_handlers,
    )

    app.add_handlers(
        management_handlers,
    )

    app.add_handlers(
        note_handlers,
    )

    # Catch-all handlers: one per group (see group table above).
    app.add_handlers(
        greet_message_handlers,
        group=GROUP_GREETING_CAPTURE,
    )

    app.add_handlers(
        lock_filter_handlers,
        group=GROUP_LOCK_FILTER,
    )

    app.add_handlers(
        member_handlers,
        group=GROUP_MEMBER_EVENTS,
    )

    app.add_error_handler(
        error_handler,
    )


def main():

    validate_config()

    keep_alive()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )

    register_handlers(app)

    log.info(
        "🌹 %s is starting... | ha_enabled=%s | instance=%s",
        BOT_NAME,
        HA_ENABLED,
        INSTANCE_ID,
    )

    if HA_ENABLED:
        # Multi-instance mode: every Render project runs this exact code with
        # the SAME bot token, but only the MongoDB lease holder polls Telegram
        # (a second concurrent getUpdates gets 409 Conflict). The HTTP
        # health/API server above is already running, so standby instances
        # stay reachable for Render health checks and the dashboard.
        asyncio.run(leader_loop(app))
    else:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            bootstrap_retries=-1,
        )


if __name__ == "__main__":
    main()
