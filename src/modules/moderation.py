"""Group moderation commands."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions
from telegram.error import TelegramError
from telegram.ext import CommandHandler

from src.database.db_core import add_warning, clear_warnings, get_warning_count
from src.utils.decorators import admin_only


def target(update, context):
    message = update.effective_message
    if message and message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.first_name
    if context.args:
        try:
            uid = int(context.args[0])
            return (uid, str(uid)) if uid > 0 else (None, None)
        except (ValueError, TypeError):
            pass
    return None, None


def parse_duration(value):
    match = re.fullmatch(r"([1-9]\d*)(s|m|h|d|w)", value.lower())
    if not match:
        return None
    seconds = int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[match.group(2)]
    if seconds > 30 * 86400:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


async def _reply_error(update, prefix: str, exc: TelegramError):
    message = update.effective_message
    if message:
        await message.reply_text(f"❌ {prefix}: {getattr(exc, 'message', str(exc))}")


@admin_only
async def ban(update, context):
    uid, name = target(update, context)
    if not uid:
        return await update.effective_message.reply_text("🚫 Reply to a user or use `/ban USER_ID`.")
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, uid)
        await update.effective_message.reply_text(f"🚫 Banned: {name} (`{uid}`)", parse_mode="Markdown")
    except TelegramError as exc:
        await _reply_error(update, "Ban failed", exc)


@admin_only
async def unban(update, context):
    uid, _ = target(update, context)
    if not uid:
        return await update.effective_message.reply_text("Use `/unban USER_ID`.")
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, uid, only_if_banned=True)
        await update.effective_message.reply_text("✅ Unbanned.")
    except TelegramError as exc:
        await _reply_error(update, "Unban failed", exc)


@admin_only
async def kick(update, context):
    uid, name = target(update, context)
    if not uid:
        return await update.effective_message.reply_text("🚪 Reply to a user or use `/kick USER_ID`.")
    try:
        chat_id = update.effective_chat.id
        await context.bot.ban_chat_member(chat_id, uid)
        await context.bot.unban_chat_member(chat_id, uid)
        await update.effective_message.reply_text(f"🦶 Kicked: {name}")
    except TelegramError as exc:
        await _reply_error(update, "Kick failed", exc)


@admin_only
async def mute(update, context):
    message = update.effective_message
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply_text("🤫 Reply to a user: `/mute 10m` or `/mute`.")
    until = parse_duration(context.args[0]) if context.args else None
    if context.args and not until:
        return await message.reply_text("❌ Duration: `10m`, `2h`, `3d`, `1w` (max 30d).")
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            message.reply_to_message.from_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await message.reply_text("🤫 User muted.")
    except TelegramError as exc:
        await _reply_error(update, "Mute failed", exc)


@admin_only
async def unmute(update, context):
    message = update.effective_message
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply_text("🔊 Reply to a user.")
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, message.reply_to_message.from_user.id, permissions=permissions)
        await message.reply_text("🔊 Unmuted.")
    except TelegramError as exc:
        await _reply_error(update, "Unmute failed", exc)


@admin_only
async def warn(update, context):
    uid, name = target(update, context)
    if not uid:
        return await update.effective_message.reply_text("⚠️ Reply to a user: `/warn reason`.")
    reason = " ".join(context.args) or "No reason"
    count = await add_warning(update.effective_chat.id, uid, reason)
    await update.effective_message.reply_text(f"⚠️ {name} warned.\nWarnings: {count}/3\nReason: {reason}")
    if count >= 3:
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, uid)
            await clear_warnings(update.effective_chat.id, uid)
            await update.effective_message.reply_text("🚨 3 warnings reached — user banned and warnings reset.")
        except TelegramError:
            await update.effective_message.reply_text("⚠️ 3 warnings reached, but automatic ban failed.")


@admin_only
async def warnings(update, context):
    uid, name = target(update, context)
    uid = uid or update.effective_user.id
    count = await get_warning_count(update.effective_chat.id, uid)
    await update.effective_message.reply_text(f"⚠️ Warnings for {name or uid}: {count}/3")


@admin_only
async def unwarn(update, context):
    uid, name = target(update, context)
    if not uid:
        return await update.effective_message.reply_text("Reply to a user.")
    await clear_warnings(update.effective_chat.id, uid)
    await update.effective_message.reply_text(f"✅ Warnings cleared for {name}.")


mod_handlers = [
    CommandHandler(["ban", "forceban"], ban),
    CommandHandler("unban", unban),
    CommandHandler("kick", kick),
    CommandHandler("mute", mute),
    CommandHandler("unmute", unmute),
    CommandHandler("warn", warn),
    CommandHandler(["warnings", "warns"], warnings),
    CommandHandler(["unwarn", "clearwarns"], unwarn),
]
