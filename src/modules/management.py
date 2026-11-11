"""POPPY ROSE - group management and owner control center.

Includes:
- Anonymous-admin-safe permission handling via decorators.py
- Multiple global owners
- /addowner, /delowner, /owners
- Promote / demote
- Pin / unpin
- User info / myid / chatid
- Stats
- Announce
- Bot profile commands
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from telegram.error import TelegramError

from types import SimpleNamespace

from config import BOT_NAME, SUPPORT_USERNAME, GROUP_1, GROUP_2

from src.utils.decorators import admin_only, owner_only, is_anonymous_admin
from src.utils.broadcast import copy_to_active_groups
from src.database.db_core import (
    add_owner,
    remove_owner,
    get_owner_ids,
    is_owner,
)


# ============================================================
# TARGET USER
# ============================================================

def reply_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return None

    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user

    if context.args:
        try:
            user_id = int(context.args[0])
        except (ValueError, TypeError):
            return None

        return SimpleNamespace(
            id=user_id,
            first_name=str(user_id),
            full_name=str(user_id),
            username=None,
            is_premium=False,
        )

    return None


# ============================================================
# PROMOTE
# ============================================================

@admin_only
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    user = reply_user(update, context)
    if not user:
        return await message.reply_text(
            "👤 Reply to a user or provide their numeric Telegram ID."
        )

    try:
        await context.bot.promote_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=True,
            can_restrict_members=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_post_messages=True,
            can_edit_messages=True,
        )
        await message.reply_text(
            f"👑 Promoted: {getattr(user, 'first_name', user.id)}"
        )
    except TelegramError as exc:
        await message.reply_text(f"❌ Telegram error:\n{exc}")


# ============================================================
# DEMOTE
# ============================================================

@admin_only
async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    user = reply_user(update, context)
    if not user:
        return await message.reply_text(
            "👤 Reply to a user or provide their numeric Telegram ID."
        )

    try:
        await context.bot.promote_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_post_messages=False,
            can_edit_messages=False,
        )
        await message.reply_text("📉 Admin rights removed.")
    except TelegramError as exc:
        await message.reply_text(f"❌ Telegram error:\n{exc}")


# ============================================================
# PIN / UNPIN
# ============================================================

@admin_only
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    if not message.reply_to_message:
        return await message.reply_text("📌 Reply to a message.")

    try:
        await context.bot.pin_chat_message(
            chat_id=chat.id,
            message_id=message.reply_to_message.message_id,
            disable_notification=True,
        )
        await message.reply_text("📌 Message pinned.")
    except TelegramError as exc:
        await message.reply_text(f"❌ {exc}")


@admin_only
async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    try:
        if message.reply_to_message:
            await context.bot.unpin_chat_message(
                chat_id=chat.id,
                message_id=message.reply_to_message.message_id,
            )
        else:
            await context.bot.unpin_all_chat_messages(chat_id=chat.id)
        await message.reply_text("📌 Unpinned.")
    except TelegramError as exc:
        await message.reply_text(f"❌ {exc}")


# ============================================================
# USER INFO
# ============================================================

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    user = reply_user(update, context) or message.from_user
    if not user:
        return await message.reply_text(
            "❌ Telegram did not provide a sender identity."
        )

    await message.reply_text(
        "👤 *User Info*\n\n"
        f"• Name: `{getattr(user, 'first_name', 'Unknown')}`\n"
        f"• ID: `{user.id}`\n"
        f"• Username: `@{getattr(user, 'username', None) or 'N/A'}`\n"
        f"• Premium: {'Yes ⭐' if getattr(user, 'is_premium', False) else 'No'}",
        parse_mode="Markdown",
    )


# ============================================================
# GOD
# ============================================================

@owner_only
async def god(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    identity_line = "👑 Global owner access verified.\n"

    await message.reply_text(
        f"👑 *{BOT_NAME} GOD MODE*\n\n"
        f"{identity_line}"
        "⚡ Group-management privileges enabled.\n\n"
        f"Developer: @{SUPPORT_USERNAME}\n"
        f"Groups: @{GROUP_1} • @{GROUP_2}",
        parse_mode="Markdown",
    )


# ============================================================
# OWNER HELP
# ============================================================

@owner_only
async def ownerhelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "👑 *POPPY OWNER ARSENAL*\n\n"
        "/addowner <id> — Add a global owner\n"
        "/delowner <id> — Remove a global owner\n"
        "/owners — List global owners\n"
        "/stats — Bot/database statistics\n"
        "/announce — Broadcast a replied message to active groups\n"
        "/setbotname — Change bot name\n"
        "/setbotdescription — Change bot description\n\n"
        "🔐 Owner commands require a recognized personal Telegram ID.",
        parse_mode="Markdown",
    )


# ============================================================
# MULTI-OWNER SYSTEM
# ============================================================

@owner_only
async def addowner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    target = reply_user(update, context)
    if not target:
        return await message.reply_text(
            "👑 Usage: `/addowner 6490704993`\n\n"
            "Or reply to a user's message with `/addowner`.",
            parse_mode="Markdown",
        )

    try:
        user_id = int(target.id)
    except (TypeError, ValueError):
        return await message.reply_text("❌ Invalid Telegram user ID.")

    if user_id <= 0:
        return await message.reply_text("❌ Invalid Telegram user ID.")

    if await is_owner(user_id):
        return await message.reply_text(
            f"ℹ️ `{user_id}` is already a POPPY owner.",
            parse_mode="Markdown",
        )

    try:
        created = await add_owner(user_id)
    except Exception as exc:
        return await message.reply_text(
            f"❌ Could not add owner:\n`{exc}`",
            parse_mode="Markdown",
        )

    if not created:
        return await message.reply_text(
            f"ℹ️ `{user_id}` is already a POPPY owner.",
            parse_mode="Markdown",
        )

    await message.reply_text(
        "👑 *OWNER ADDED*\n\n"
        f"🆔 User ID: `{user_id}`\n"
        "✅ Global owner privileges are now enabled.",
        parse_mode="Markdown",
    )


@owner_only
async def delowner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    target = reply_user(update, context)
    if not target:
        return await message.reply_text(
            "👑 Usage: `/delowner 6490704993`\n\n"
            "Or reply to a user's message with `/delowner`.",
            parse_mode="Markdown",
        )

    try:
        user_id = int(target.id)
    except (TypeError, ValueError):
        return await message.reply_text("❌ Invalid Telegram user ID.")

    try:
        from config import OWNER_ID
        if OWNER_ID and user_id == int(OWNER_ID):
            return await message.reply_text(
                "🛡️ The configured `OWNER_ID` cannot be removed.\n"
                "Change OWNER_ID in your environment variables if you need to transfer primary ownership.",
                parse_mode="Markdown",
            )
    except Exception:
        pass

    owners = await get_owner_ids()
    if user_id not in owners:
        return await message.reply_text(
            f"ℹ️ `{user_id}` is not a POPPY owner.",
            parse_mode="Markdown",
        )

    # Never allow the database to become ownerless when there is no
    # configured OWNER_ID.
    if len(owners) <= 1:
        return await message.reply_text(
            "🛡️ You cannot remove the last owner. Add another owner first.",
        )

    try:
        removed = await remove_owner(user_id)
    except Exception as exc:
        return await message.reply_text(
            f"❌ Could not remove owner:\n`{exc}`",
            parse_mode="Markdown",
        )

    await message.reply_text(
        (
            "🗑️ *OWNER REMOVED*\n\n"
            f"🆔 User ID: `{user_id}`\n"
            "✅ Global owner privileges revoked."
        ) if removed else (
            f"ℹ️ `{user_id}` was not removed."
        ),
        parse_mode="Markdown",
    )


@owner_only
async def owners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    try:
        owner_ids = await get_owner_ids()
    except Exception as exc:
        return await message.reply_text(f"❌ Owner database error:\n{exc}")

    if not owner_ids:
        return await message.reply_text("⚠️ No owners are configured.")

    lines = ["👑 *POPPY GLOBAL OWNERS*", ""]
    for index, owner_id in enumerate(owner_ids, 1):
        try:
            member = await context.bot.get_chat(owner_id)
            name = member.full_name
            username = f"@{member.username}" if member.username else "no username"
            lines.append(f"{index}. `{owner_id}` — {name} ({username})")
        except TelegramError:
            lines.append(f"{index}. `{owner_id}`")

    await message.reply_text("\n".join(lines), parse_mode="Markdown")


# ============================================================
# STATS
# ============================================================

@owner_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    from src.database.db_core import users_col, groups_col

    try:
        users = await users_col.count_documents({})
        groups = await groups_col.count_documents({"active": {"$ne": False}})
        owner_count = len(await get_owner_ids())

        await message.reply_text(
            f"📊 *{BOT_NAME} Stats*\n\n"
            f"👤 Users: `{users}`\n"
            f"👥 Active groups: `{groups}`\n"
            f"👑 Owners: `{owner_count}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        await message.reply_text(f"❌ Database error:\n{exc}")


# ============================================================
# BOT PROFILE
# ============================================================

@owner_only
async def setbotname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    if not context.args:
        return await message.reply_text(
            "Use: `/setbotname New Name`",
            parse_mode="Markdown",
        )

    name = " ".join(context.args)[:64]
    try:
        await context.bot.set_my_name(name=name)
        await message.reply_text(f"✨ Bot name updated:\n{name}")
    except TelegramError as exc:
        await message.reply_text(f"❌ {exc}")


@owner_only
async def setbotdescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    if not context.args:
        return await message.reply_text(
            "Use: `/setbotdescription Your description`",
            parse_mode="Markdown",
        )

    description = " ".join(context.args)[:512]
    try:
        await context.bot.set_my_description(description=description)
        await message.reply_text("✨ Bot description updated.")
    except TelegramError as exc:
        await message.reply_text(f"❌ {exc}")


# ============================================================
# ANNOUNCE
# ============================================================

@owner_only
async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    if not message.reply_to_message:
        return await message.reply_text(
            "📢 Reply to the message you want to announce."
        )

    try:
        # Paced + flood-safe fan-out (see src/utils/broadcast.py).
        result = await copy_to_active_groups(
            message.reply_to_message,
        )
    except Exception as exc:
        return await message.reply_text(
            f"❌ Broadcast error:\n{exc}"
        )

    await message.reply_text(
        "📢 *Announcement complete*\n\n"
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
# CHAT / USER ID
# ============================================================

async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    await message.reply_text(
        f"🆔 Chat ID: `{chat.id}`",
        parse_mode="Markdown",
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the actual Telegram sender when Telegram exposes it.

    Anonymous administrators remain anonymous. The bot cannot recover the
    hidden personal ID from an anonymous group message.
    """
    message = update.effective_message
    chat = update.effective_chat
    if not message:
        return

    user = message.from_user

    if is_anonymous_admin(update):
        return await message.reply_text(
            "🕵️ *POPPY ID CHECK*\n\n"
            "👤 Name: `Anonymous Administrator`\n"
            "🆔 User ID: `Hidden by Telegram`\n"
            f"💬 Chat ID: `{chat.id if chat else 'Unknown'}`\n"
            f"🏷 Chat Type: `{chat.type if chat else 'Unknown'}`\n\n"
            "🔐 Your real Telegram ID is not exposed to bots while "
            "anonymous administrator mode is enabled.",
            parse_mode="Markdown",
        )

    if not user:
        return await message.reply_text(
            "❌ Telegram did not provide a sender identity."
        )

    username = f"@{user.username}" if user.username else "N/A"
    await message.reply_text(
        "🆔 *POPPY ID CHECK*\n\n"
        f"👤 Name: `{user.full_name}`\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🔗 Username: `{username}`\n"
        f"💬 Chat ID: `{chat.id if chat else 'Unknown'}`\n"
        f"🏷 Chat Type: `{chat.type if chat else 'Unknown'}`",
        parse_mode="Markdown",
    )


# ============================================================
# DELETE
# ============================================================

@admin_only
async def delete_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    if not message.reply_to_message:
        return await message.reply_text(
            "🗑 Reply to a message to delete it."
        )

    try:
        await message.reply_to_message.delete()
        await message.delete()
    except TelegramError as exc:
        await message.reply_text(f"❌ {exc}")


# ============================================================
# HANDLERS
# ============================================================

management_handlers = [
    CommandHandler("promote", promote),
    CommandHandler("demote", demote),
    CommandHandler("pin", pin),
    CommandHandler("unpin", unpin),
    CommandHandler("info", info),
    CommandHandler("god", god),
    CommandHandler("ownerhelp", ownerhelp),
    CommandHandler("addowner", addowner),
    CommandHandler("owneradd", addowner),
    CommandHandler("delowner", delowner),
    CommandHandler("ownerremove", delowner),
    CommandHandler("owners", owners),
    CommandHandler("stats", stats),
    CommandHandler("announce", announce),
    CommandHandler("setbotname", setbotname),
    CommandHandler("setbotdescription", setbotdescription),
    CommandHandler("chatid", chatid),
    CommandHandler("id", myid),
    CommandHandler("myid", myid),
    CommandHandler("del", delete_reply),
]
