"""POPPY ROSE - welcome, goodbye and global broadcast module."""

import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ChatMemberHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

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
    is_active_restricted_member = (
        new_status == "restricted"
        and bool(getattr(new_member, "is_member", False))
    )

    return (
        old_status in {"left", "kicked"}
        and (
            new_status in {"member", "administrator"}
            or is_active_restricted_member
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
        and (
            new_status in {"left", "kicked"}
            or (
                new_status == "restricted"
                and not bool(getattr(result.new_chat_member, "is_member", True))
            )
        )
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
            caption=_render_message(
                data.get("caption", ""),
                user,
            ),
        )

    elif post_type == "video":
        await context.bot.send_video(
            chat_id,
            video=data["file_id"],
            caption=_render_message(
                data.get("caption", ""),
                user,
            ),
        )

    elif post_type == "animation":
        await context.bot.send_animation(
            chat_id,
            animation=data["file_id"],
            caption=_render_message(
                data.get("caption", ""),
                user,
            ),
        )

    elif post_type == "document":
        await context.bot.send_document(
            chat_id,
            document=data["file_id"],
            caption=_render_message(
                data.get("caption", ""),
                user,
            ),
        )

    elif post_type == "audio":
        await context.bot.send_audio(
            chat_id,
            audio=data["file_id"],
            caption=_render_message(
                data.get("caption", ""),
                user,
            ),
        )

    elif post_type == "voice":
        await context.bot.send_voice(
            chat_id,
            voice=data["file_id"],
        )

    elif post_type == "text":
        await context.bot.send_message(
            chat_id,
            _render_message(
                data.get("text", ""),
                user,
            ),
        )


# ============================================================
# JOIN EVENT
# ============================================================

async def greet_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    result = update.chat_member
    chat = update.effective_chat

    if not result or not chat:
        return

    if not _is_join(result):
        return

    data = await get_group_setting(
        chat.id,
        "welcome",
    )

    if not data:
        return

    user = result.new_chat_member.user

    try:
        await _send_saved_post(
            chat.id,
            data,
            user,
            context,
        )
    except TelegramError as exc:
        log.exception(
            "Welcome message failed | chat=%s | user=%s | error=%s",
            chat.id,
            user.id,
            exc,
        )


# ============================================================
# LEAVE / KICK EVENT
# ============================================================

async def goodbye_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    result = update.chat_member
    chat = update.effective_chat

    if not result or not chat:
        return

    if not _is_leave(result):
        return

    data = await get_group_setting(
        chat.id,
        "goodbye",
    )

    if not data:
        return

    user = result.old_chat_member.user

    try:
        await _send_saved_post(
            chat.id,
            data,
            user,
            context,
        )
    except TelegramError as exc:
        log.exception(
            "Goodbye message failed | chat=%s | user=%s | error=%s",
            chat.id,
            user.id,
            exc,
        )


# ============================================================
# UNIFIED CHAT-MEMBER DISPATCHER
# ============================================================

async def on_chat_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Single CHAT_MEMBER handler that dispatches join vs leave.

    greet_member and goodbye_member must NOT be registered as two sibling
    ChatMemberHandlers in the same group: PTB runs at most one handler per
    group, so the second one (goodbye) would never execute. One dispatcher
    guarantees both paths stay reachable.
    """
    result = update.chat_member

    if not result:
        return

    if _is_join(result):
        await greet_member(update, context)

    elif _is_leave(result):
        await goodbye_member(update, context)


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
        filters.ALL & ~filters.COMMAND,
        receive_greeting_post,
    ),
]

# Join/leave events: registered in their OWN handler group. Exactly ONE
# ChatMemberHandler exists (the unified dispatcher), so welcome and
# goodbye both run for every membership change.
member_handlers = [
    ChatMemberHandler(
        on_chat_member,
        ChatMemberHandler.CHAT_MEMBER,
    ),
]
