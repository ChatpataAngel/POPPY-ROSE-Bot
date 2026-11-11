STRINGS = {
    "en": {"not_admin": "❌ Admin access required.", "owner_only": "👑 Owner-only command."},
    "hi": {"not_admin": "❌ Sirf admins ye command chala sakte hain.", "owner_only": "👑 Ye command sirf bot owner ke liye hai."},
    "hinglish": {"not_admin": "❌ Bhai, ye command sirf admins ke liye locked hai.", "owner_only": "👑 Ye POPPY Owner-only command hai."},
}


async def t(user_id: int, key: str) -> str:
    from src.database.db_core import get_user_lang
    lang = await get_user_lang(user_id)
    return STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))
