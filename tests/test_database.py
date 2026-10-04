from pathlib import Path

from app.database import Database


def test_queue_lifecycle(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.init()
    item = database.add_queue_item(
        target_thread_id="thread-1",
        target_username="student_a",
        target_text="Cần tìm thợ chụp kỷ yếu tại Hà Nội",
        permalink="https://www.threads.net/@student_a/post/demo",
        reply_text="Chào bạn, mình gửi thông tin nhé.",
    )
    assert item["status"] == "draft"

    approved = database.update_queue_item(item["id"], status="approved")
    assert approved["status"] == "approved"

    sent = database.update_queue_item(
        item["id"], status="sent", published_reply_id="reply-1", sent_at="2026-10-04T05:00:00+00:00"
    )
    assert sent["published_reply_id"] == "reply-1"
    assert database.history()[0]["status"] == "sent"


def test_sent_item_is_not_overwritten_by_duplicate(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.init()
    first = database.add_queue_item(
        target_thread_id="thread-1",
        target_username="a",
        target_text="first",
        permalink="https://example.com/1",
        reply_text="original reply",
    )
    database.update_queue_item(first["id"], status="sent", sent_at="2026-10-04T05:00:00+00:00")
    duplicate = database.add_queue_item(
        target_thread_id="thread-1",
        target_username="a",
        target_text="updated source",
        permalink="https://example.com/1",
        reply_text="replacement reply",
    )
    assert duplicate["status"] == "sent"
    assert duplicate["reply_text"] == "original reply"

