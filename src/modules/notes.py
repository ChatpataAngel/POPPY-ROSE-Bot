from telegram.ext import CommandHandler
from src.utils.decorators import admin_only
from src.database.db_core import save_group_setting, get_group_setting

@admin_only
async def set_rules(update, context):
    if not context.args: return await update.message.reply_text("Use `/setrules your rules here`")
    await save_group_setting(update.effective_chat.id,"rules"," ".join(context.args))
    await update.message.reply_text("📜 Rules saved.")

async def rules(update, context):
    text=await get_group_setting(update.effective_chat.id,"rules")
    await update.message.reply_text(f"📜 *Group Rules*\n\n{text}" if text else "📜 No rules set yet.",parse_mode="Markdown")

@admin_only
async def set_note(update, context):
    if len(context.args)<2: return await update.message.reply_text("Use `/save note_name note text`")
    name=context.args[0].lower()
    notes=await get_group_setting(update.effective_chat.id,"notes",{})
    notes[name]=" ".join(context.args[1:])
    await save_group_setting(update.effective_chat.id,"notes",notes)
    await update.message.reply_text(f"📝 Saved note `{name}`",parse_mode="Markdown")

async def get_note(update, context):
    if not context.args: return await update.message.reply_text("Use `/get note_name`")
    notes=await get_group_setting(update.effective_chat.id,"notes",{})
    text=notes.get(context.args[0].lower())
    await update.message.reply_text(text or "❌ Note not found.")

@admin_only
async def del_note(update, context):
    if not context.args: return await update.message.reply_text("Use `/delnote note_name`")
    notes=await get_group_setting(update.effective_chat.id,"notes",{})
    notes.pop(context.args[0].lower(),None)
    await save_group_setting(update.effective_chat.id,"notes",notes)
    await update.message.reply_text("🗑 Note deleted.")

note_handlers=[
    CommandHandler("setrules",set_rules),CommandHandler("rules",rules),
    CommandHandler("save",set_note),CommandHandler("get",get_note),
    CommandHandler("delnote",del_note)
]
