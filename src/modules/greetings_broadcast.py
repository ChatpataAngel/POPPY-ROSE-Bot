"""POPPY ROSE - welcome, goodbye and global broadcast module."""

import asyncio
import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ChatMemberHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

log = logging.getLogger("poppy_rose.greetings")

# Both Telegram membership updates and the optional new-chat-members service
# message can describe the same join. Use a per-member lock and a short event
# time window so those two paths never send two welcomes for one join.
_WELCOME_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}
_RECENT_WELCOME_EVENTS: OrderedDict[
    tuple[int, int], tuple[float, float]
] = OrderedDict()
_WELCOME_DUPLICATE_WINDOW_SECONDS = 5.0
_WELCOME_CACHE_TTL_SECONDS = 600.0
_WELCOME_CACHE_LIMIT = 5000

from src.utils.decorators import admin_only, owner_only
from src.database.db_core import (
    save_group_setting,
    get_group_setting,
)
from src.utils.broadcast import copy_to_active_groups


# ============================================================
# HELPERS
# ============================================================

def _render_message(text: str, user) -> str:
    """Replace supported placeholders."""

    if not text:
        return ""

    first_name = user.first_name or "there"
    full_name = user.full_name or first_name
    username = (
        f"@{user.username}"
        if user.username
        else first_name
    )

    return (
        text
        .replace("{name}", first_name)
        .replace("{first_name}", first_name)
        .replace("{full_name}", full_name)
        .replace("{username}", username)
        .replace("{mention}", first_name)
    )


def _is_join(result) -> bool:
    """Check whether this update represents a new member."""

    if not result:
        return False

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    new_member = result.new_chat_member
    is_restricted_member = (
        new_status == "restricted"
        and bool(getattr(new_member, "is_member", False))
    )
    return (
        old_status in {"left", "kicked"}
        and (
            new_status in {"member", "administrator", "creator"}
            or is_restricted_member
        )
    )


def _is_leave(result) -> bool:
    """Check whether this update represents a member leaving/kicked."""

    if not result:
        return False

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    return (
        old_status in {
            "member",
            "administrator",
            "creator",
            "restricted",
        }
        and new_status in {
            "left",
            "kicked",
        }
    )


def _message_to_setting(message):
    """
    Convert the second message into a database-safe
    welcome/goodbye setting.
    """

    if message.photo:
        return {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.caption or "",
        }

    if message.video:
        return {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": message.caption or "",
        }

    if message.animation:
        return {
            "type": "animation",
            "file_id": message.animation.file_id,
            "caption": message.caption or "",
        }

    if message.document:
        return {
            "type": "document",
            "file_id": message.document.file_id,
            "caption": message.caption or "",
        }

    if message.audio:
        return {
            "type": "audio",
            "file_id": message.audio.file_id,
            "caption": message.caption or "",
        }

    if message.voice:
        return {
            "type": "voice",
            "file_id": message.voice.file_id,
            "caption": message.caption or "",
        }

    text = message.text or message.caption

    if text:
        return {
            "type": "text",
            "text": text,
        }

    return None


# ============================================================
# CONFIGURATION START
# ============================================================

@admin_only
async def set_welcome(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Start two-message welcome configuration.

    Admin:
        /setwelcome

    Bot:
        asks for the next message.

    Admin:
        sends the actual welcome post.

    Bot:
        saves that second message.
    """

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    # Disable immediately.
    if context.args and context.args[0].lower() in {
        "off",
        "disable",
        "disabled",
    }:
        await save_group_setting(
            chat.id,
            "welcome",
            None,
        )

        await message.reply_text(
            "🥀 Welcome messages have been disabled."
        )
        return

    # Store pending configuration.
    context.user_data["pending_greeting"] = {
        "type": "welcome",
        "chat_id": chat.id,
    }

    await message.reply_text(
        "🌹 Welcome configuration started.\n\n"
        "📩 Send the **next message** now.\n\n"
        "That next message will become the complete "
        "welcome post.\n\n"
        "You can send:\n"
        "• 📝 Text\n"
        "• 🖼️ Photo + caption\n"
        "• 🎥 Video + caption\n"
        "• 🎞️ Animation + caption\n"
        "• 📄 Document + caption\n"
        "• 🎵 Audio + caption\n"
        "• 🎙️ Voice\n\n"
        "✨ Supported placeholders:\n"
        "`{name}`\n"
        "`{first_name}`\n"
        "`{full_name}`\n"
        "`{username}`\n"
        "`{mention}`\n\n"
        "Send `/cancel` to cancel.",
        parse_mode="Markdown",
    )


@admin_only
async def set_goodbye(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Start two-message goodbye configuration.

    Admin:
        /setgoodbye

    Bot:
        asks for the next message.

    Admin:
        sends the actual goodbye post.

    Bot:
        saves that second message.
    """

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    # Disable immediately.
    if context.args and context.args[0].lower() in {
        "off",
        "disable",
        "disabled",
    }:
        await save_group_setting(
            chat.id,
            "goodbye",
            None,
        )

        await message.reply_text(
            "🥀 Goodbye messages have been disabled."
        )
        return

    # Store pending configuration.
    context.user_data["pending_greeting"] = {
        "type": "goodbye",
        "chat_id": chat.id,
    }

    await message.reply_text(
        "🥀 Goodbye configuration started.\n\n"
        "📩 Send the **next message** now.\n\n"
        "That next message will become the complete "
        "goodbye post.\n\n"
        "You can send:\n"
        "• 📝 Text\n"
        "• 🖼️ Photo + caption\n"
        "• 🎥 Video + caption\n"
        "• 🎞️ Animation + caption\n"
        "• 📄 Document + caption\n"
        "• 🎵 Audio + caption\n"
        "• 🎙️ Voice\n\n"
        "✨ Supported placeholders:\n"
        "`{name}`\n"
        "`{first_name}`\n"
        "`{full_name}`\n"
        "`{username}`\n"
        "`{mention}`\n\n"
        "Send `/cancel` to cancel.",
        parse_mode="Markdown",
    )


async def cancel_greeting_setup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Cancel pending welcome/goodbye configuration."""

    message = update.effective_message

    if not message:
        return

    pending = context.user_data.pop(
        "pending_greeting",
        None,
    )

    if pending:
        await message.reply_text(
            "❌ Welcome/goodbye configuration cancelled."
        )
    else:
        await message.reply_text(
            "ℹ️ There is no pending welcome/goodbye setup."
        )


# ============================================================
# SECOND MESSAGE HANDLER
# ============================================================

async def receive_greeting_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Receive the SECOND message after /setwelcome or /setgoodbye.

    This is the actual post that gets stored.
    """

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    pending = context.user_data.get(
        "pending_greeting"
    )

    if not pending:
        return

    # Only accept the post in the same chat where setup started.
    if pending.get("chat_id") != chat.id:
        return

    setting_name = pending.get("type")

    if setting_name not in {
        "welcome",
        "goodbye",
    }:
        context.user_data.pop(
            "pending_greeting",
            None,
        )
        return

    data = _message_to_setting(message)

    if not data:
        await message.reply_text(
            "⚠️ I couldn't use that message.\n\n"
            "Please send text, photo, video, animation, "
            "document, audio or voice."
        )
        return

    try:
        await save_group_setting(
            chat.id,
            setting_name,
            data,
        )
    except Exception:
        log.exception(
            "GREETING_CONFIGURATION_SAVE_FAILED | chat_id=%s | setting=%s | user_id=%s",
            chat.id,
            setting_name,
            user.id,
        )
        context.user_data.pop(
            "pending_greeting",
            None,
        )

        await message.reply_text(
            "❌ I couldn't save that post. "
            "Please try again."
        )
        return

    context.user_data.pop(
        "pending_greeting",
        None,
    )
    log.info(
        "GREETING_CONFIGURATION_SAVED | chat_id=%s | setting=%s | user_id=%s | post_type=%s",
        chat.id,
        setting_name,
        user.id,
        data.get("type", "unknown"),
    )

    if setting_name == "welcome":
        await message.reply_text(
            "✅ 🌹 **Welcome post saved successfully!**\n\n"
            "The message you just sent is now your "
            "group's automatic welcome post.",
            parse_mode="Markdown",
        )
    else:
        await message.reply_text(
            "✅ 🥀 **Goodbye post saved successfully!**\n\n"
            "The message you just sent is now your "
            "group's automatic farewell post.",
            parse_mode="Markdown",
        )


# ============================================================
# SEND SAVED POST
# ============================================================

async def _send_saved_post(
    chat_id: int,
    data: dict,
    user,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Send a stored welcome/goodbye post."""

    if not data:
        return

    post_type = data.get("type")

    if post_type == "photo":
        await context.bot.send_photo(
            chat_id,
            photo=data["file_id"],
            caption=_render_message(data.get("caption", ""), user),
        )
    elif post_type == "video":
        await context.bot.send_video(
            chat_id,
            video=data["file_id"],
            caption=_render_message(data.get("caption", ""), user),
        )
    elif post_type == "animation":
        await context.bot.send_animation(
            chat_id,
            animation=data["file_id"],
            caption=_render_message(data.get("caption", ""), user),
        )
    elif post_type == "document":
        await context.bot.send_document(
            chat_id,
            document=data["file_id"],
            caption=_render_message(data.get("caption", ""), user),
        )
    elif post_type == "audio":
        await context.bot.send_audio(
            chat_id,
            audio=data["file_id"],
            caption=_render_message(data.get("caption", ""), user),
        )
    elif post_type == "voice":
        await context.bot.send_voice(
            chat_id,
            voice=data["file_id"],
        )
    elif post_type == "text":
        await context.bot.send_message(
            chat_id,
            _render_message(data.get("text", ""), user),
        )
    else:
        raise ValueError(f"Unsupported saved greeting type: {post_type!r}")


def _event_timestamp(value) -> float:
    """Normalize Telegram's event date to a UTC Unix timestamp."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    return time.time()


def _prune_welcome_cache(now: float) -> None:
    """Bound the in-process duplicate cache and remove old idle locks."""
    expired = [
        key
        for key, (_, sent_at) in _RECENT_WELCOME_EVENTS.items()
        if now - sent_at > _WELCOME_CACHE_TTL_SECONDS
    ]
    for key in expired:
        _RECENT_WELCOME_EVENTS.pop(key, None)

    while len(_RECENT_WELCOME_EVENTS) > _WELCOME_CACHE_LIMIT:
        _RECENT_WELCOME_EVENTS.popitem(last=False)

    for key in list(_WELCOME_LOCKS):
        if key not in _RECENT_WELCOME_EVENTS and not _WELCOME_LOCKS[key].locked():
            _WELCOME_LOCKS.pop(key, None)


async def _dispatch_welcome(
    chat_id: int,
    user,
    event_date,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    source: str,
) -> None:
    """Look up and send a welcome once, regardless of which update path fires."""
    if not user or getattr(user, "is_bot", False):
        log.info(
            "WELCOME_SKIPPED | reason=missing_or_bot_user | chat_id=%s | source=%s",
            chat_id,
            source,
        )
        return

    key = (int(chat_id), int(user.id))
    lock = _WELCOME_LOCKS.setdefault(key, asyncio.Lock())

    async with lock:
        now = time.monotonic()
        _prune_welcome_cache(now)

        event_ts = _event_timestamp(event_date)
        previous = _RECENT_WELCOME_EVENTS.get(key)
        if previous:
            previous_event_ts, previous_sent_at = previous
            if (
                now - previous_sent_at <= _WELCOME_CACHE_TTL_SECONDS
                and abs(event_ts - previous_event_ts)
                <= _WELCOME_DUPLICATE_WINDOW_SECONDS
            ):
                log.info(
                    "WELCOME_DUPLICATE_SUPPRESSED | chat_id=%s | member_id=%s | source=%s",
                    chat_id,
                    user.id,
                    source,
                )
                _RECENT_WELCOME_EVENTS.move_to_end(key)
                return

        log.info(
            "WELCOME_LOOKUP_STARTED | chat_id=%s | member_id=%s | source=%s",
            chat_id,
            user.id,
            source,
        )

        try:
            data = await get_group_setting(chat_id, "welcome")
        except Exception as exc:
            log.exception(
                "WELCOME_LOOKUP_FAILED | chat_id=%s | member_id=%s | source=%s | error_type=%s",
                chat_id,
                user.id,
                source,
                type(exc).__name__,
            )
            return

        if not data:
            log.warning(
                "WELCOME_NOT_CONFIGURED | chat_id=%s | member_id=%s | source=%s | action=run_setwelcome_in_this_group",
                chat_id,
                user.id,
                source,
            )
            return

        try:
            await _send_saved_post(chat_id, data, user, context)
        except TelegramError as exc:
            log.exception(
                "WELCOME_SEND_FAILED | chat_id=%s | member_id=%s | source=%s | telegram_error=%s",
                chat_id,
                user.id,
                source,
                type(exc).__name__,
            )
            return
        except Exception as exc:
            log.exception(
                "WELCOME_SEND_FAILED | chat_id=%s | member_id=%s | source=%s | error_type=%s",
                chat_id,
                user.id,
                source,
                type(exc).__name__,
            )
            return

        _RECENT_WELCOME_EVENTS[key] = (event_ts, time.monotonic())
        _RECENT_WELCOME_EVENTS.move_to_end(key)
        _prune_welcome_cache(time.monotonic())
        log.info(
            "WELCOME_SENT | chat_id=%s | member_id=%s | post_type=%s | source=%s",
            chat_id,
            user.id,
            data.get("type", "unknown"),
            source,
        )


# ============================================================
# JOIN EVENT
# ============================================================

async def greet_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Send the configured welcome post for a confirmed new member."""
    result = update.chat_member
    chat = update.effective_chat

    if not result or not chat:
        log.warning("WELCOME_SKIPPED | reason=missing_chat_member_update")
        return

    if not _is_join(result):
        log.debug(
            "WELCOME_SKIPPED | reason=not_a_join | chat_id=%s | old_status=%s | new_status=%s",
            chat.id,
            result.old_chat_member.status,
            result.new_chat_member.status,
        )
        return

    user = result.new_chat_member.user
    await _dispatch_welcome(
        chat.id,
        user,
        result.date,
        context,
        source="chat_member",
    )


# ============================================================
# LEAVE / KICK EVENT
# ============================================================

async def goodbye_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Send the configured goodbye post for a member who left or was kicked."""
    result = update.chat_member
    chat = update.effective_chat

    if not result or not chat:
        log.warning("GOODBYE_SKIPPED | reason=missing_chat_member_update")
        return

    if not _is_leave(result):
        return

    user = result.old_chat_member.user
    try:
        data = await get_group_setting(chat.id, "goodbye")
    except Exception:
        log.exception(
            "GOODBYE_LOOKUP_FAILED | chat_id=%s | member_id=%s",
            chat.id,
            user.id,
        )
        return

    if not data:
        log.info(
            "GOODBYE_NOT_CONFIGURED | chat_id=%s | member_id=%s",
            chat.id,
            user.id,
        )
        return

    try:
        await _send_saved_post(chat.id, data, user, context)
        log.info(
            "GOODBYE_SENT | chat_id=%s | member_id=%s | post_type=%s",
            chat.id,
            user.id,
            data.get("type", "unknown"),
        )
    except TelegramError as exc:
        log.exception(
            "GOODBYE_SEND_FAILED | chat_id=%s | member_id=%s | telegram_error=%s",
            chat.id,
            user.id,
            type(exc).__name__,
        )
    except Exception as exc:
        log.exception(
            "GOODBYE_SEND_FAILED | chat_id=%s | member_id=%s | error_type=%s",
            chat.id,
            user.id,
            type(exc).__name__,
        )


# ============================================================
# UNIFIED CHAT-MEMBER DISPATCHER
# ============================================================

async def on_chat_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Audit every chat-member update and dispatch join/leave actions."""
    result = update.chat_member
    chat = update.effective_chat

    if not result:
        log.warning("CHAT_MEMBER_UPDATE_IGNORED | reason=missing_payload")
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    member_id = result.new_chat_member.user.id
    chat_id = chat.id if chat else None

    log.info(
        "CHAT_MEMBER_UPDATE_RECEIVED | chat_id=%s | member_id=%s | old_status=%s | new_status=%s | actor_id=%s",
        chat_id,
        member_id,
        old_status,
        new_status,
        result.from_user.id if result.from_user else None,
    )

    if _is_join(result):
        log.info(
            "MEMBER_JOIN_DETECTED | chat_id=%s | member_id=%s",
            chat_id,
            member_id,
        )
        await greet_member(update, context)
    elif _is_leave(result):
        log.info(
            "MEMBER_LEAVE_DETECTED | chat_id=%s | member_id=%s",
            chat_id,
            member_id,
        )
        await goodbye_member(update, context)
    else:
        log.debug(
            "MEMBER_STATUS_CHANGE_NOT_JOIN_OR_LEAVE | chat_id=%s | member_id=%s | old_status=%s | new_status=%s",
            chat_id,
            member_id,
            old_status,
            new_status,
        )


async def on_new_chat_members(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Fallback for Telegram's ``new_chat_members`` service messages.

    Telegram does not expose this service message for every join in every
    supergroup. The chat_member update remains the primary mechanism; this
    handler is an independent fallback whenever the service message is sent.
    """
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        log.warning("WELCOME_FALLBACK_IGNORED | reason=missing_message_or_chat")
        return

    members = message.new_chat_members or []
    log.info(
        "NEW_CHAT_MEMBERS_SERVICE_UPDATE_RECEIVED | chat_id=%s | members_count=%s | message_id=%s",
        chat.id,
        len(members),
        message.message_id,
    )

    for user in members:
        log.info(
            "MEMBER_JOIN_DETECTED | chat_id=%s | member_id=%s | source=service_message",
            chat.id,
            user.id,
        )
        await _dispatch_welcome(
            chat.id,
            user,
            message.date,
            context,
            source="service_message",
        )


@admin_only
async def welcome_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Show actionable diagnostics for the current group's welcome setup."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type == "private":
        if message:
            await message.reply_text("Run /welcomecheck inside the group you want to diagnose.")
        return

    bot_status = "unknown"
    bot_status_error = None
    try:
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(chat.id, me.id)
        bot_status = member.status
    except TelegramError as exc:
        bot_status_error = type(exc).__name__
        log.warning(
            "WELCOME_CHECK_BOT_STATUS_FAILED | chat_id=%s | error_type=%s",
            chat.id,
            bot_status_error,
        )

    try:
        saved = await get_group_setting(chat.id, "welcome")
    except Exception as exc:
        log.exception(
            "WELCOME_CHECK_SETTING_LOOKUP_FAILED | chat_id=%s | error_type=%s",
            chat.id,
            type(exc).__name__,
        )
        saved = None
        setting_error = type(exc).__name__
    else:
        setting_error = None

    is_admin = bot_status in {"administrator", "creator"}
    configured = bool(saved)
    post_type = saved.get("type", "unknown") if isinstance(saved, dict) else "none"
    updater = getattr(context.application, "updater", None)
    polling_active = bool(updater and updater.running)

    lines = [
        "🌹 POPPY ROSE — Welcome diagnostics",
        f"Group ID: {chat.id}",
        f"Bot status: {bot_status}",
        f"chat_member updates: {'available (bot is admin)' if is_admin else 'NOT GUARANTEED — bot must be an administrator'}",
        f"Service-message fallback: registered (Telegram may omit it in some supergroups)",
        f"Welcome post: {'saved' if configured else 'NOT SAVED'}",
        f"Welcome type: {post_type}",
        f"This instance polling: {'yes' if polling_active else 'no (this may be an HA standby)'}",
    ]
    if bot_status_error:
        lines.append(f"Bot status check error: {bot_status_error}")
    if setting_error:
        lines.append(f"Welcome setting lookup error: {setting_error}")
    if not is_admin:
        lines.append("Action: promote POPPY ROSE to administrator, then test another new member.")
    if not configured:
        lines.append("Action: run /setwelcome in this exact group.")

    log.info(
        "WELCOME_DIAGNOSTICS | chat_id=%s | bot_status=%s | chat_member_ready=%s | configured=%s | post_type=%s | polling_active=%s",
        chat.id,
        bot_status,
        is_admin,
        configured,
        post_type,
        polling_active,
    )
    await message.reply_text("\n".join(lines))


# ============================================================
# BOT ADMIN / MEMBERSHIP AUDIT
# ============================================================

async def on_bot_chat_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Log changes to the bot's own membership/administrator status."""
    result = update.my_chat_member
    chat = update.effective_chat
    if not result or not chat:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    log.info(
        "BOT_MEMBERSHIP_STATUS_CHANGED | chat_id=%s | old_status=%s | new_status=%s | actor_id=%s",
        chat.id,
        old_status,
        new_status,
        result.from_user.id if result.from_user else None,
    )

    if new_status not in {"administrator", "creator"}:
        log.warning(
            "BOT_NOT_ADMIN | chat_id=%s | current_status=%s | requirement=administrator_for_chat_member_updates",
            chat.id,
            new_status,
        )


# ============================================================
# GLOBAL BROADCAST
# ============================================================

@owner_only
async def global_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Copy a replied message to every active group."""

    message = update.effective_message

    if not message:
        return

    if not message.reply_to_message:
        return await message.reply_text(
            "⚠️ Reply to the message you want to broadcast."
        )

    try:
        result = await copy_to_active_groups(
            message.reply_to_message,
        )
    except Exception as exc:
        return await message.reply_text(
            f"❌ Broadcast error:\n{exc}"
        )

    await message.reply_text(
        "📢 *Broadcast complete*\n\n"
        f"✅ Sent: `{result['sent']}`\n"
        f"❌ Failed: `{result['failed']}`"
        + (
            "\n⚠️ Aborted early after repeated failures."
            if result["aborted"]
            else ""
        ),
        parse_mode="Markdown",
    )


# ============================================================
# HANDLERS
# ============================================================

# Command handlers: registered together in the default group 0.
greet_broadcast_handlers = [
    # FIRST MESSAGE
    CommandHandler(
        "setwelcome",
        set_welcome,
    ),

    CommandHandler(
        "setgoodbye",
        set_goodbye,
    ),

    CommandHandler(
        "welcomecheck",
        welcome_check,
    ),

    CommandHandler(
        "cancel",
        cancel_greeting_setup,
    ),

    # OWNER BROADCAST
    CommandHandler(
        "broadcast",
        global_broadcast,
    ),
]

# Catch-all message handler: registered in its OWN handler group (see
# register_handlers in src/__main__.py) so it cannot shadow or be
# shadowed by other catch-all handlers (PTB: one handler per group).
greet_message_handlers = [
    MessageHandler(
        filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
        receive_greeting_post,
    ),
]

# Membership updates and the service-message fallback share a dedicated
# group. These filters match mutually exclusive update types, so either one
# can handle an update without shadowing the other.
member_handlers = [
    ChatMemberHandler(
        on_chat_member,
        ChatMemberHandler.CHAT_MEMBER,
    ),
    MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        on_new_chat_members,
    ),
]


# Bot's own admin/member status changes are a separate Telegram update type.
bot_membership_handlers = [
    ChatMemberHandler(
        on_bot_chat_member,
        ChatMemberHandler.MY_CHAT_MEMBER,
    ),
]
