"""Static authorization regression tests; no Telegram/Mongo connection required."""
from pathlib import Path
import ast
import os

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    # UTF-8 is mandatory: the sources contain emoji and the tests run on
    # Windows where the default locale (cp1252) would raise UnicodeDecodeError.
    return (ROOT / path).read_text(encoding="utf-8")


def _decorated_functions(path: str):
    tree = ast.parse(_read(path))
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = {
                d.id if isinstance(d, ast.Name) else getattr(d, "attr", "")
                for d in node.decorator_list
            }
    return result


def test_all_owner_handlers_are_owner_only():
    funcs = _decorated_functions("src/modules/management.py")
    for name in ["god", "ownerhelp", "addowner", "delowner", "owners", "stats", "setbotname", "setbotdescription", "announce"]:
        assert "owner_only" in funcs[name], name


def test_broadcast_is_owner_only():
    funcs = _decorated_functions("src/modules/greetings_broadcast.py")
    assert "owner_only" in funcs["global_broadcast"]


def test_admin_handlers_use_admin_only():
    for path in [
        "src/modules/moderation.py",
        "src/modules/locks_purge.py",
        "src/modules/management.py",
        "src/modules/greetings_broadcast.py",
        "src/modules/notes.py",
    ]:
        funcs = _decorated_functions(path)
        for name, decorators in funcs.items():
            if name in {"filter_locked", "greet_member", "info", "rules", "get_note"}:
                continue
            if name in {"ban", "unban", "kick", "mute", "unmute", "warn", "warnings", "unwarn", "purge", "lock", "unlock", "promote", "demote", "pin", "unpin", "delete_reply", "set_welcome", "set_rules", "set_note", "del_note"}:
                assert "admin_only" in decorators, f"{path}:{name}"


def test_no_bootstrap_owner_startup_text_or_logic():
    config = _read("config.py")
    db = _read("src/database/db_core.py")
    assert "first person" not in config.lower()
    assert "first person" not in db.lower()
    assert "source: \"explicit\"" in db or '"source": "explicit"' in db


def test_anonymous_admin_logic_is_centralized():
    decorators = _read("src/utils/decorators.py")
    assert "GROUP_ANONYMOUS_BOT_ID = 1087968824" in decorators
    # The guard must REJECT senders that are not the chat itself.
    assert "sender_chat.id != chat.id" in decorators
    assert "if is_anonymous_admin(update):" in decorators


def _assigned_list(path: str, name: str):
    """Return the AST node of a module-level assignment like `x = [...]`."""
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    raise AssertionError(f"assignment {name!r} not found in {path}")


def _called_names(node) -> set:
    """Names of the (directly) called constructors inside an AST node."""
    return {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }


def test_catch_all_handlers_are_isolated():
    """PTB runs at most ONE handler per group.

    The catch-all MessageHandler (greeting capture) and the two
    ChatMemberHandlers used to share group 0, silently disabling content
    locks and goodbye messages. Each catch-all now lives in its own group.
    """
    greet_commands = _assigned_list(
        "src/modules/greetings_broadcast.py",
        "greet_broadcast_handlers",
    )
    greet_names = _called_names(greet_commands)
    assert "MessageHandler" not in greet_names, "greeting capture must not share the command group"
    assert "ChatMemberHandler" not in greet_names, "a single unified ChatMember dispatcher must be used"

    lock_commands = _assigned_list(
        "src/modules/locks_purge.py",
        "locks_purge_handlers",
    )
    assert "MessageHandler" not in _called_names(lock_commands), "lock filter must not share the command group"

    # The unified dispatcher must exist and route both join and leave events.
    greet_src = _read("src/modules/greetings_broadcast.py")
    assert "async def on_chat_member(" in greet_src
    assert "await greet_member(update, context)" in greet_src
    assert "await goodbye_member(update, context)" in greet_src

    # Each catch-all is registered in its own dedicated group.
    main_src = _read("src/__main__.py")
    assert "group=GROUP_GREETING_CAPTURE" in main_src
    assert "group=GROUP_LOCK_FILTER" in main_src
    assert "group=GROUP_MEMBER_EVENTS" in main_src
    assert "GROUP_GREETING_CAPTURE = 1" in main_src
    assert "GROUP_LOCK_FILTER = 2" in main_src
    assert "GROUP_MEMBER_EVENTS = 3" in main_src
    assert "GROUP_BOT_STATUS_EVENTS = 4" in main_src


def test_broadcast_operations_are_rate_limited():
    """Unthrottled fan-out is what gets bot tokens frozen by Telegram."""
    config = _read("config.py")
    assert "BROADCAST_DELAY" in config

    broadcast_util = _read("src/utils/broadcast.py")
    assert "flood_safe" in broadcast_util
    assert "BROADCAST_DELAY" in broadcast_util
    assert "MAX_CONSECUTIVE_FAILURES" in broadcast_util

    flood_util = _read("src/utils/flood.py")
    assert "RetryAfter" in flood_util

    for path in (
        "src/modules/greetings_broadcast.py",
        "src/modules/management.py",
    ):
        assert "copy_to_active_groups" in _read(path), path

    # Purges must be throttled too.
    assert "retry_after_seconds" in _read("src/modules/locks_purge.py")


def test_db_validates_config_before_creating_client():
    db = _read("src/database/db_core.py")
    assert db.index("validate_config()") < db.index("AsyncIOMotorClient(")


def test_runtime_handler_groups():
    """Build the real Application and assert catch-alls are isolated.

    Requires python-telegram-bot (a declared dependency); skipped cleanly
    when the library is not installed. Never contacts Telegram/MongoDB.
    """
    os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
    os.environ.setdefault("MONGO_DB_URI", "mongodb://localhost:27017")
    os.environ.setdefault("OWNER_ID", "1")

    ext = pytest.importorskip("telegram.ext")

    from src.__main__ import register_handlers

    app = ext.Application.builder().token("123456:TEST-token").build()
    register_handlers(app)

    def group_of(callback_name):
        for group, handlers in app.handlers.items():
            for handler in handlers:
                if getattr(handler.callback, "__name__", None) == callback_name:
                    return group
        return None

    # Commands stay in group 0; catch-alls each get their own group.
    assert group_of("ban") == 0
    assert group_of("ping") == 0
    receive_group = group_of("receive_greeting_post")
    lock_group = group_of("filter_locked")
    member_group = group_of("on_chat_member")
    assert receive_group is not None
    assert lock_group is not None
    assert member_group is not None
    assert len({0, receive_group, lock_group, member_group}) == 4

    # Exactly ONE ChatMemberHandler so welcome + goodbye both dispatch.
    from telegram.ext import ChatMemberHandler

    only_member = [
        h
        for h in app.handlers[member_group]
        if isinstance(h, ChatMemberHandler)
    ]
    assert len(only_member) == 1


def test_welcome_has_service_message_fallback_and_diagnostics():
    """A new_chat_members service message is a second, deduplicated path."""
    greet_src = _read("src/modules/greetings_broadcast.py")
    main_src = _read("src/__main__.py")

    assert "async def on_new_chat_members(" in greet_src
    assert "filters.StatusUpdate.NEW_CHAT_MEMBERS" in greet_src
    assert 'source="service_message"' in greet_src
    assert "WELCOME_DUPLICATE_SUPPRESSED" in greet_src
    assert "async def welcome_check(" in greet_src
    assert '"welcomecheck"' in main_src
    assert "service_kind = \"new_chat_members\"" in main_src
    assert "service_message_fallback=enabled" in main_src

    # A join service message must not be mistaken for the admin's pending
    # /setwelcome media/text payload.
    assert "~filters.StatusUpdate.ALL" in greet_src


def test_ping_command_is_registered_and_documented():
    """/ping must live in the shared command group, be listed in /help,
    and surface the errors tracked by the shared error handler."""
    handlers = _assigned_list("src/modules/ui_menu.py", "ui_handlers")
    ping_calls = [
        node
        for node in ast.walk(handlers)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "CommandHandler"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "ping"
    ]
    assert ping_calls, "/ping must be registered in ui_handlers (group 0)"
    assert (
        isinstance(ping_calls[0].args[1], ast.Name)
        and ping_calls[0].args[1].id == "ping"
    ), "/ping must dispatch to the ping coroutine"

    ui = _read("src/modules/ui_menu.py")
    assert "/ping" in ui, "/ping must be documented in /help"
    assert "error_status(" in ui, "/ping must report tracked errors"

    # The shared error handler records errors for /ping to display.
    main = _read("src/__main__.py")
    assert "record_error(" in main
    assert '"ping",' in main, "/ping must be exposed in the Telegram command menu"
