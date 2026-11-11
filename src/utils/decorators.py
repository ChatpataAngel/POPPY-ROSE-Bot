"""POPPY ROSE - permission and access control.

Handles normal administrators, group creators, anonymous administrators,
and multiple global bot owners.
"""

from functools import wraps
import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from src.database.db_core import get_owner_ids, is_owner
from src.utils.localization import t

log = logging.getLogger("poppy_rose.permissions")

# Telegram's special anonymous-admin identity.
GROUP_ANONYMOUS_BOT_ID = 1087968824


async def is_global_owner(user_id: int) -> bool:
    try:
        return await is_owner(int(user_id))
    except (TypeError, ValueError):
        return False
    except Exception:
        log.exception("Global owner check failed | user=%s", user_id)
        return False


async def get_telegram_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Return the real user's Telegram member status when available."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return None

    # Telegram represents an anonymous administrator as the special
    # GroupAnonymousBot account. Do NOT ask Telegram whether that special
    # account is a member; it is not the actual administrator.
    if is_anonymous_admin(update):
        return "administrator"

    try:
        member = await context.bot.get_chat_member(
            chat_id=chat.id,
            user_id=user.id,
        )

        log.info(
            "TELEGRAM PERMISSION CHECK | user=%s | chat=%s | status=%s",
            user.id,
            chat.id,
            member.status,
        )
        return member.status

    except TelegramError as exc:
        log.warning(
            "TELEGRAM PERMISSION ERROR | user=%s | chat=%s | error=%s",
            user.id,
            chat.id,
            exc,
        )
        return None
    except Exception:
        log.exception(
            "Unexpected permission error | user=%s | chat=%s",
            user.id,
            chat.id,
        )
        return None


def is_anonymous_admin(update: Update) -> bool:
    """Detect Telegram's anonymous administrator message format.

    When an admin uses 'Remain Anonymous', Telegram sends the message as the
    group itself and exposes GroupAnonymousBot as `from_user`. The actual
    account ID is intentionally unavailable to bots.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return False

    sender_chat = getattr(message, "sender_chat", None)

    if user.id != GROUP_ANONYMOUS_BOT_ID:
        return False

    if not sender_chat or sender_chat.id != chat.id:
        return False

    return chat.type in {"group", "supergroup"}


async def is_group_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return False

    # A normal global owner has admin access everywhere.
    if await is_global_owner(user.id):
        log.info("GLOBAL OWNER ACCESS GRANTED | user=%s", user.id)
        return True

    if chat.type == "private":
        # Group-admin commands have nothing to act on in a private chat.
        # The global owner was already accepted above, so deny everyone
        # else here instead of granting *all* private users admin access.
        return False

    # Anonymous administrators cannot be resolved to their personal ID.
    # However, a message sent as the current group is an anonymous-admin
    # message and should be treated as a group-admin command.
    if is_anonymous_admin(update):
        log.info(
            "ANONYMOUS ADMIN ACCESS GRANTED | chat=%s | user=%s",
            chat.id,
            user.id,
        )
        return True

    status = await get_telegram_status(update, context)

    if status in {"creator", "administrator"}:
        log.info(
            "GROUP ADMIN ACCESS GRANTED | user=%s | chat=%s | status=%s",
            user.id,
            chat.id,
            status,
        )
        return True

    log.warning(
        "GROUP ADMIN ACCESS DENIED | user=%s | chat=%s | status=%s",
        user.id,
        chat.id,
        status,
    )
    return False


def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user

        # Anonymous admins cannot be identified as global owners. Do not
        # accidentally treat GroupAnonymousBot as an owner.
        if user and not is_anonymous_admin(update):
            if await is_global_owner(user.id):
                return await func(update, context)

        if update.effective_message:
            try:
                user_id = user.id if user else 0
                message = await t(user_id, "owner_only")
            except Exception:
                message = "👑 POPPY owner access required."

            await update.effective_message.reply_text(message)

    return wrapper


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat:
            return

        if await is_group_admin(update, context):
            return await func(update, context)

        if update.effective_message:
            status = await get_telegram_status(update, context)
            await update.effective_message.reply_text(
                "🚫 *Admin access required.*\n\n"
                f"🆔 Your ID: `{update.effective_user.id}`\n"
                f"💬 Chat ID: `{update.effective_chat.id}`\n"
                f"📌 Telegram status: `{status or 'unknown'}`",
                parse_mode="Markdown",
            )

    return wrapper
