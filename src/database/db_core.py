"""MongoDB access layer for POPPY ROSE.

Security model:
- Global owners come only from OWNER_ID and explicit owner records.
- There is no first-user/first-/start owner bootstrap.
- Owner mutations are atomic and invalidate the in-process owner cache.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from config import DB_NAME, MONGO_DB_URI, OWNER_ID, validate_config

log = logging.getLogger("poppy_rose.database")

# Fail fast with a clear, human-readable configuration error *before*
# constructing the MongoDB client. Without this, a missing/invalid
# MONGO_DB_URI surfaces as a confusing pymongo traceback on first query.
validate_config()

client = AsyncIOMotorClient(
    MONGO_DB_URI,
    serverSelectionTimeoutMS=10_000,
    connectTimeoutMS=10_000,
    socketTimeoutMS=20_000,
    maxPoolSize=20,
    minPoolSize=1,
)
db = client[DB_NAME]

users_col = db["users"]
groups_col = db["groups"]
settings_col = db["settings"]
warnings_col = db["warnings"]
owners_col = db["owners"]
meta_col = db["meta"]

_owner_cache: frozenset[int] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def init_db() -> None:
    global _owner_cache

    await users_col.create_index("user_id", unique=True)
    await groups_col.create_index("chat_id", unique=True)
    await warnings_col.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
    await owners_col.create_index("user_id", unique=True)
    await meta_col.create_index("key", unique=True)
    await settings_col.create_index("chat_id", unique=True)

    # Mark the configured primary owner explicitly. The configuration itself
    # remains authoritative, so deleting this DB document cannot lock out the owner.
    if OWNER_ID:
        await owners_col.update_one(
            {"user_id": int(OWNER_ID)},
            {
                "$set": {"source": "configured", "updated_at": _now()},
                "$setOnInsert": {"user_id": int(OWNER_ID), "created_at": _now()},
            },
            upsert=True,
        )
    _owner_cache = None


async def ping_db() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        log.exception("MongoDB ping failed")
        return False


async def close_db() -> None:
    client.close()


# --------------------------- OWNER SYSTEM ---------------------------

async def claim_first_owner(user) -> bool:
    """Compatibility shim: only the configured OWNER_ID can ever be owner."""
    if not user or not OWNER_ID:
        return False
    try:
        return int(user.id) == int(OWNER_ID)
    except (TypeError, ValueError):
        return False


async def get_owner_ids() -> list[int]:
    global _owner_cache
    if _owner_cache is not None:
        return sorted(_owner_cache)

    ids: set[int] = set()
    if OWNER_ID:
        ids.add(int(OWNER_ID))

    cursor = owners_col.find(
        {"source": {"$in": ["explicit", "configured"]}},
        {"user_id": 1},
    )
    async for doc in cursor:
        try:
            uid = int(doc["user_id"])
            if uid > 0:
                ids.add(uid)
        except (KeyError, TypeError, ValueError):
            continue

    _owner_cache = frozenset(ids)
    return sorted(ids)


async def get_owner_id() -> int:
    ids = await get_owner_ids()
    return ids[0] if ids else 0


async def is_owner(user_id: int) -> bool:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    return uid in await get_owner_ids()


async def add_owner(user_id: int) -> bool:
    global _owner_cache
    uid = int(user_id)
    if uid <= 0:
        raise ValueError("Telegram user ID must be positive")
    if OWNER_ID and uid == int(OWNER_ID):
        return False

    result = await owners_col.update_one(
        {"user_id": uid},
        {
            "$set": {"source": "explicit", "updated_at": _now()},
            "$setOnInsert": {"user_id": uid, "created_at": _now()},
        },
        upsert=True,
    )
    _owner_cache = None
    return bool(result.upserted_id is not None or result.modified_count > 0)


async def remove_owner(user_id: int) -> bool:
    global _owner_cache
    uid = int(user_id)
    if OWNER_ID and uid == int(OWNER_ID):
        return False

    result = await owners_col.delete_one({"user_id": uid, "source": "explicit"})
    _owner_cache = None
    return result.deleted_count > 0


# --------------------------- USERS / GROUPS ---------------------------

async def set_user_lang(user_id: int, lang: str):
    await users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {"lang": lang, "updated_at": _now()}},
        upsert=True,
    )


async def get_user_lang(user_id: int) -> str:
    doc = await users_col.find_one({"user_id": int(user_id)}, {"lang": 1})
    return doc.get("lang", "en") if doc else "en"


async def register_user(user) -> None:
    if not user:
        return
    await users_col.update_one(
        {"user_id": int(user.id)},
        {
            "$set": {
                "first_name": user.first_name,
                "username": user.username,
                "updated_at": _now(),
            },
            "$setOnInsert": {"created_at": _now()},
        },
        upsert=True,
    )


async def register_group(chat) -> None:
    if not chat or chat.type == "private":
        return
    await groups_col.update_one(
        {"chat_id": int(chat.id)},
        {
            "$set": {
                "title": chat.title or str(chat.id),
                "username": chat.username,
                "type": chat.type,
                "active": True,
                "updated_at": _now(),
            },
            "$setOnInsert": {"created_at": _now()},
        },
        upsert=True,
    )


async def deactivate_group(chat_id: int) -> None:
    await groups_col.update_one(
        {"chat_id": int(chat_id)},
        {"$set": {"active": False, "updated_at": _now()}},
    )


def get_active_groups():
    return groups_col.find({"active": {"$ne": False}}, {"chat_id": 1})


async def save_group_setting(chat_id: int, key: str, value):
    # Settings keys are internal constants, not user-supplied Mongo operators.
    if not key or key.startswith("$") or "." in key:
        raise ValueError("Invalid setting key")
    await settings_col.update_one(
        {"chat_id": int(chat_id)},
        {"$set": {key: value, "updated_at": _now()}},
        upsert=True,
    )


async def get_group_setting(chat_id: int, key: str, default=None):
    doc = await settings_col.find_one({"chat_id": int(chat_id)}, {key: 1})
    return doc.get(key, default) if doc else default


# --------------------------- WARNINGS ---------------------------

async def add_warning(chat_id: int, user_id: int, reason: str) -> int:
    reason = (reason or "No reason").strip()[:500]
    doc = await warnings_col.find_one_and_update(
        {"chat_id": int(chat_id), "user_id": int(user_id)},
        {
            "$inc": {"count": 1},
            "$push": {"items": {"$each": [{"reason": reason, "at": _now()}], "$slice": -100}},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc.get("count", 1))


async def get_warning_count(chat_id: int, user_id: int) -> int:
    doc = await warnings_col.find_one({"chat_id": int(chat_id), "user_id": int(user_id)})
    return int(doc.get("count", 0)) if doc else 0


async def clear_warnings(chat_id: int, user_id: int) -> None:
    await warnings_col.delete_one({"chat_id": int(chat_id), "user_id": int(user_id)})
