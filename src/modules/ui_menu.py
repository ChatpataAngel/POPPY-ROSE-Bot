"""POPPY ROSE user interface and command help."""

import time
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)

from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from telegram.helpers import escape_markdown

from config import (
    BOT_NAME,
    SUPPORT_USERNAME,
    GROUP_1,
    GROUP_2,
)

from src.database.db_core import (
    db,
    register_user,
    set_user_lang,
)

from src.utils.status import (
    error_status,
    started_at,
)


async def language_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    keyboard = [
        [
            InlineKeyboardButton(
                "English 🇬🇧",
                callback_data="lang_en",
            ),
            InlineKeyboardButton(
                "Hindi 🇮🇳",
                callback_data="lang_hi",
            ),
        ],
        [
            InlineKeyboardButton(
                "Hinglish 🚀",
                callback_data="lang_hinglish",
            ),
        ],
    ]

    await update.effective_message.reply_text(
        "🌐 Choose your language:",
        reply_markup=InlineKeyboardMarkup(
            keyboard,
        ),
    )


async def language_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer()

    language = query.data.replace(
        "lang_",
        "",
    )

    await set_user_lang(
        query.from_user.id,
        language,
    )

    await query.edit_message_text(
        f"✅ Language changed to {language.upper()}."
    )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    await register_user(user)

    if chat.type != "private":
        return

    me = await context.bot.get_me()

    keyboard = [
        [
            InlineKeyboardButton(
                "➕ Add to Group",
                url=(
                    f"https://t.me/{me.username}"
                    "?startgroup=true"
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                "👨‍💻 Support",
                url=(
                    f"https://t.me/"
                    f"{SUPPORT_USERNAME}"
                ),
            ),
        ],
    ]

    await update.effective_message.reply_text(
        f"🌹 *WELCOME TO {BOT_NAME.upper()}* 🌹\n\n"
        f"✨ Hello, {user.first_name}!\n\n"
        "You've entered the *Rose Garden* — "
        "a premium Telegram community management "
        "experience built for protection, moderation "
        "and control. 🥀\n\n"
        "🛡️ Advanced Moderation\n"
        "🔒 Smart Protection\n"
        "⚡ Powerful Admin Tools\n"
        "🌸 Premium Community Experience\n\n"
        "Add me to your group as an administrator "
        "and use /help to explore my commands.\n\n"
        "🥂 *Stay classy. Stay protected.*\n"
        "🌹 *Welcome to the Rose Garden.*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            keyboard,
        ),
        disable_web_page_preview=True,
    )


async def help_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        f"🌹 *{BOT_NAME} — COMMAND CENTER* 🌹\n\n"

        "🌸 *Getting Started*\n"
        "/start — Open the control panel\n"
        "/help — Show this command center\n"
        "/language — Change language\n\n"

        "🛡️ *Moderation*\n"
        "/ban — Ban a user\n"
        "/forceban — Ban a user\n"
        "/unban — Unban a user\n"
        "/kick — Kick a user\n"
        "/mute — Mute a user\n"
        "/unmute — Unmute a user\n\n"

        "⚠️ *Warnings*\n"
        "/warn — Add a warning\n"
        "/warnings — Show warnings\n"
        "/warns — Show warnings\n"
        "/unwarn — Clear warnings\n"
        "/clearwarns — Clear warnings\n\n"

        "🔒 *Protection & Locks*\n"
        "/lock — Lock a content type\n"
        "/unlock — Unlock a content type\n"
        "/purge — Purge messages\n"
        "/spurge — Purge alias\n\n"

        "🌹 *Welcome & Goodbye*\n"
        "/setwelcome — Configure welcome message\n"
        "/welcomecheck — Diagnose welcome setup\n"
        "/setgoodbye — Configure goodbye message\n"
        "/setwelcome off — Disable welcome\n"
        "/setgoodbye off — Disable goodbye\n\n"

        "👑 *Group Management*\n"
        "/promote — Promote a member\n"
        "/demote — Demote an administrator\n"
        "/pin — Pin a message\n"
        "/unpin — Unpin a message\n"
        "/del — Delete a replied message\n"
        "/info — Show user information\n"
        "/setrules — Set group rules\n"
        "/rules — Show group rules\n\n"

        "📝 *Notes*\n"
        "/save — Save a note\n"
        "/get — Get a note\n"
        "/delnote — Delete a note\n\n"

        "📢 *Broadcasting*\n"
        "/broadcast — Owner broadcast\n"
        "/announce — Owner announcement\n\n"

        "👑 *Owner Commands*\n"
        "/god — Owner status\n"
        "/ownerhelp — Owner command help\n"
        "/owners — List owners\n"
        "/addowner — Add owner\n"
        "/owneradd — Add owner alias\n"
        "/delowner — Remove owner\n"
        "/ownerremove — Remove owner alias\n"
        "/stats — Bot statistics\n"
        "/setbotname — Change bot name\n"
        "/setbotdescription — Change bot description\n\n"

        "🆔 *Utilities*\n"
        "/id — Your Telegram ID\n"
        "/myid — Your Telegram ID\n"
        "/chatid — Current chat ID\n"
        "/ping — Measure latency & errors\n\n"

        "🔐 *Admin Access*\n"
        "Group administrators can use group-admin "
        "commands, including anonymous administrators.\n"
        "Global-owner commands require recognized "
        "global-owner authorization.\n\n"

        f"👨‍💻 @{SUPPORT_USERNAME}\n"
        f"🌸 @{GROUP_1} • @{GROUP_2}"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


def _grade(ms: float) -> str:
    if ms <= 150:
        return "🟢 excellent"
    if ms <= 350:
        return "🟡 acceptable"
    return "🔴 slow"


def _age(delta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


async def ping(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Measure update, Telegram API, and database latency.

    Every probe failure is reported inline instead of crashing the
    handler, and errors captured by the shared error handler since
    process start are shown as well.
    """
    started = time.perf_counter()
    problems = 0

    # 1) Update delay: when Telegram timestamped the message vs now
    #    (polling lag + queue delay + handler processing start).
    try:
        sent_at = update.effective_message.date
        update_ms = max(
            0.0,
            (datetime.now(timezone.utc) - sent_at).total_seconds() * 1000,
        )
        update_line = (
            f"⏱ Update delay: `{update_ms:.0f} ms` — "
            f"{_grade(update_ms)}"
        )
    except Exception as exc:
        problems += 1
        update_line = (
            "⏱ Update delay: ❌ "
            f"{escape_markdown(str(exc))}"
        )

    # 2) Round trip to Telegram's API.
    try:
        probe = time.perf_counter()
        await context.bot.get_me()
        api_ms = (time.perf_counter() - probe) * 1000
        api_line = (
            f"📡 Telegram API: `{api_ms:.0f} ms` — "
            f"{_grade(api_ms)}"
        )
    except Exception as exc:
        problems += 1
        api_line = (
            "📡 Telegram API: ❌ "
            f"{escape_markdown(str(exc))}"
        )

    # 3) Round trip to MongoDB.
    try:
        probe = time.perf_counter()
        await db.command("ping")
        db_ms = (time.perf_counter() - probe) * 1000
        db_line = (
            f"🗄 Database: `{db_ms:.0f} ms` — "
            f"{_grade(db_ms)}"
        )
    except Exception as exc:
        problems += 1
        db_line = (
            "🗄 Database: ❌ "
            f"{escape_markdown(str(exc))}"
        )

    total_ms = (time.perf_counter() - started) * 1000

    # 4) Errors the shared error handler has seen since process start.
    count, last_text, last_at = error_status()
    if count and last_text and last_at is not None:
        error_line = (
            f"🧯 Errors since start: `{count}` — last "
            f"{_age(datetime.now(timezone.utc) - last_at)} ago:\n"
            f"    {escape_markdown(last_text[:160])}"
        )
    else:
        error_line = "🧯 Errors since start: 0"

    uptime = _age(
        datetime.now(timezone.utc) - started_at(),
    )

    if problems:
        status = f"⚠️ {problems} check(s) failed"
    else:
        status = "✅ All systems healthy"

    await update.effective_message.reply_text(
        f"🏓 *PONG* — {BOT_NAME}\n\n"
        f"{update_line}\n"
        f"{api_line}\n"
        f"{db_line}\n"
        f"🔁 Total probe time: `{total_ms:.0f} ms` • Uptime: {uptime}\n"
        f"{error_line}\n\n"
        f"{status}",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


ui_handlers = [
    CommandHandler(
        "start",
        start,
    ),
    CommandHandler(
        "help",
        help_cmd,
    ),
    CommandHandler(
        "language",
        language_cmd,
    ),
    CommandHandler(
        "ping",
        ping,
    ),
    CallbackQueryHandler(
        language_callback,
        pattern=r"^lang_",
    ),
]
