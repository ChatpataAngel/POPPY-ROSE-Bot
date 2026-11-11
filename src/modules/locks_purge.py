"""Message locks and purge tools."""
from __future__ import annotations

import asyncio
import re

from telegram.error import RetryAfter, TelegramError
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from src.database.db_core import get_group_setting, save_group_setting
from src.utils.decorators import admin_only, is_anonymous_admin, is_global_owner
from src.utils.flood import retry_after_seconds

LOCKS = frozenset({"all", "url", "forward", "emojis", "sticker", "photo", "video", "document", "audio", "voice"})


@admin_only
async def purge(update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or not message.reply_to_message:
        return await message.reply_text("🧹 Reply to the first message and use `/purge`.")

    start = message.reply_to_message.message_id
    end = message.message_id
    deleted = 0
    for mid in range(start, end):
        for _ in range(3):
            try:
                await context.bot.delete_message(chat.id, mid)
                deleted += 1
                break
            except RetryAfter as exc:
                # Flood control: wait the requested time and retry this ID.
                await asyncio.sleep(retry_after_seconds(exc))
            except TelegramError:
                break
        # ~20 deletions/second keeps large purges well under Telegram's
        # request limits (an unthrottled delete loop can get the token flagged).
        await asyncio.sleep(0.05)

    try:
        await message.delete()
    except TelegramError:
        pass

    status = await context.bot.send_message(chat.id, f"🧹 Purged `{deleted}` messages.", parse_mode="Markdown")
    await asyncio.sleep(2)
    try:
        await status.delete()
    except TelegramError:
        pass


async def _set_lock(update, context, enabled: bool):
    message = update.effective_message
    if not message or not context.args:
        return await message.reply_text("🔒 Types: " + ", ".join(sorted(LOCKS)))
    typ = context.args[0].lower()
    if typ not in LOCKS:
        return await message.reply_text("🔒 Types: " + ", ".join(sorted(LOCKS)))
    locks = await get_group_setting(update.effective_chat.id, "locks", {}) or {}
    locks[typ] = enabled
    await save_group_setting(update.effective_chat.id, "locks", locks)
    await message.reply_text(f"{'🔒 Locked' if enabled else '🔓 Unlocked'}: `{typ}`", parse_mode="Markdown")


@admin_only
async def lock(update, context):
    return await _set_lock(update, context, True)


@admin_only
async def unlock(update, context):
    return await _set_lock(update, context, False)


async def _message_is_privileged(update, context) -> bool:
    msg = update.effective_message
    if not msg:
        return False
    if is_anonymous_admin(update):
        return True
    user = update.effective_user
    if not user:
        return False
    return await is_global_owner(user.id) or await _telegram_member_is_admin(update, context)


async def _telegram_member_is_admin(update, context) -> bool:
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in {"creator", "administrator"}
    except TelegramError:
        return False


async def filter_locked(update, context):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or chat.type == "private" or not user or user.is_bot:
        return

    locks = await get_group_setting(chat.id, "locks", {}) or {}
    if not any(bool(v) for v in locks.values()):
        return

    # Never apply content locks to a real admin or anonymous admin.
    if await _message_is_privileged(update, context):
        return

    delete = False
    if locks.get("all"):
        delete = True
    elif locks.get("forward") and msg.forward_origin:
        delete = True
    elif locks.get("sticker") and msg.sticker:
        delete = True
    elif locks.get("photo") and msg.photo:
        delete = True
    elif locks.get("video") and (msg.video or msg.video_note):
        delete = True
    elif locks.get("document") and msg.document:
        delete = True
    elif locks.get("audio") and msg.audio:
        delete = True
    elif locks.get("voice") and msg.voice:
        delete = True
    elif locks.get("url"):
        entities = (msg.entities or []) + (msg.caption_entities or [])
        delete = any(e.type in {"url", "text_link"} for e in entities)
    elif locks.get("emojis") and msg.text:
        delete = bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", msg.text))

    if delete:
        try:
            await msg.delete()
        except TelegramError:
            pass


# Command handlers: registered together in the default group 0.
locks_purge_handlers = [
    CommandHandler(["purge", "spurge"], purge),
    CommandHandler("lock", lock),
    CommandHandler("unlock", unlock),
]

# Catch-all filter: registered in its OWN handler group (see
# register_handlers in src/__main__.py). PTB runs at most one handler per
# group, so keeping this beside other catch-alls would silently disable it.
lock_filter_handlers = [
    MessageHandler(filters.ALL & ~filters.COMMAND, filter_locked),
]
