"""Regression tests for Telegram welcome/goodbye update delivery."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def test_all_polling_paths_explicitly_subscribe_to_chat_member_updates():
    main = read("src/__main__.py")
    lease = read("src/utils/lease.py")
    assert "allowed_updates=Update.ALL_TYPES" in main
    assert "allowed_updates=Update.ALL_TYPES" in lease
    assert "Update," in main and "from telegram import (" in main
    assert "from telegram import Update" in lease

def test_polling_does_not_drop_membership_updates_on_restart():
    main = read("src/__main__.py")
    lease = read("src/utils/lease.py")
    assert "drop_pending_updates=False" in main
    assert "drop_pending_updates=False" in lease

def test_single_chat_member_dispatcher_is_registered():
    greetings = read("src/modules/greetings_broadcast.py")
    assert "ChatMemberHandler(" in greetings and "on_chat_member" in greetings
    assert "await greet_member(update, context)" in greetings
    assert "await goodbye_member(update, context)" in greetings

def test_telegram_send_errors_are_logged():
    greetings = read("src/modules/greetings_broadcast.py")
    assert "Welcome message failed" in greetings
    assert "Goodbye message failed" in greetings
    assert "log.exception(" in greetings
