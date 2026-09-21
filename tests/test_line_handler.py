"""Unit tests for LINE webhook event handling and onboarding dialog flows."""
from unittest.mock import MagicMock, patch
import pytest
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent
from linebot.v3.messaging import TextMessage, FlexMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, ProcessedWebhook
from app.services.line_handler import handle_line_events, WELCOME_INTRO_TEXT, WELCOME_FEATURES_TEXT


def get_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


@patch("app.services.line_handler.get_line_clients")
def test_follow_event_onboarding_sequence(mock_get_clients):
    """Verify FollowEvent triggers 3-message onboarding sequence modeled after KinDee."""
    mock_messaging_api = MagicMock()
    mock_blob_api = MagicMock()
    mock_get_clients.return_value = (MagicMock(), mock_messaging_api, mock_blob_api)

    db = get_test_db()
    event = MagicMock(spec=FollowEvent)
    event.reply_token = "test_reply_token"
    event.source = MagicMock()
    event.source.user_id = "new_user_123"

    handle_line_events([event], db)

    # Verify reply_message was called
    assert mock_messaging_api.reply_message.called
    call_args = mock_messaging_api.reply_message.call_args[0][0]
    assert call_args.reply_token == "test_reply_token"
    assert len(call_args.messages) == 3

    # Message 1: Intro Text
    assert isinstance(call_args.messages[0], TextMessage)
    assert call_args.messages[0].text == WELCOME_INTRO_TEXT

    # Message 2: Features Text
    assert isinstance(call_args.messages[1], TextMessage)
    assert call_args.messages[1].text == WELCOME_FEATURES_TEXT

    # Message 3: Profile Onboarding Flex Message
    assert isinstance(call_args.messages[2], FlexMessage)
    # The LIFF URL must not carry an owner chosen by the browser.  The web app
    # authenticates the LINE subject with a verified ID token instead.
    assert "user_id" not in str(call_args.messages[2].contents.to_dict())
    assert "new_user_123" not in str(call_args.messages[2].contents.to_dict())


@patch("app.services.line_handler.get_line_clients")
def test_help_guide_text_command(mock_get_clients):
    """Verify 'วิธีใช้' command replies cleanly with Welcome guide card."""
    mock_messaging_api = MagicMock()
    mock_get_clients.return_value = (MagicMock(), mock_messaging_api, MagicMock())

    db = get_test_db()
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "reply_tok_help"
    event.source = MagicMock()
    event.source.user_id = "user_help_test"
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = "วิธีใช้งาน"

    handle_line_events([event], db)

    assert mock_messaging_api.reply_message.called
    call_args = mock_messaging_api.reply_message.call_args[0][0]
    assert len(call_args.messages) == 1
    assert isinstance(call_args.messages[0], FlexMessage)


@patch("app.services.line_handler.get_line_clients")
def test_profile_unconfigured_command(mock_get_clients):
    """Verify 'โปรไฟล์' prompts unconfigured user with onboarding card."""
    mock_messaging_api = MagicMock()
    mock_get_clients.return_value = (MagicMock(), mock_messaging_api, MagicMock())

    db = get_test_db()
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "reply_tok_profile"
    event.source = MagicMock()
    event.source.user_id = "fresh_user_456"
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = "โปรไฟล์"

    handle_line_events([event], db)

    assert mock_messaging_api.reply_message.called
    call_args = mock_messaging_api.reply_message.call_args[0][0]
    assert len(call_args.messages) == 1
    assert isinstance(call_args.messages[0], FlexMessage)


@patch("app.services.line_handler.get_line_clients")
def test_greeting_command(mock_get_clients):
    """Verify 'สวัสดี' sends a warm greeting."""
    mock_messaging_api = MagicMock()
    mock_get_clients.return_value = (MagicMock(), mock_messaging_api, MagicMock())

    db = get_test_db()
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "reply_tok_hi"
    event.source = MagicMock()
    event.source.user_id = "user_greet"
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = "สวัสดี"

    handle_line_events([event], db)

    assert mock_messaging_api.reply_message.called
    call_args = mock_messaging_api.reply_message.call_args[0][0]
    assert len(call_args.messages) == 1
    assert "สวัสดีครับ" in call_args.messages[0].text


def test_welcome_copy_uses_simple_food_command():
    assert "กิน ตามด้วยชื่อเมนู" in WELCOME_FEATURES_TEXT
    assert "เพื่อเข้าสู่ flow เดียวกับการถ่ายรูป" not in WELCOME_FEATURES_TEXT


@patch("app.services.line_handler.reply_webapp")
@patch("app.services.line_handler.require_completed_profile", return_value=True)
@patch("app.services.line_handler.get_line_clients")
def test_history_command_uses_single_webapp_entrypoint(mock_get_clients, _profile, mock_reply_webapp):
    """History is a LIFF page, so chat should not add a redundant Flex card."""
    mock_get_clients.return_value = (MagicMock(), MagicMock(), MagicMock())
    db = get_test_db()
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "reply_tok_history"
    event.source = MagicMock()
    event.source.user_id = "user_history"
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = "ประวัติ"

    handle_line_events([event], db)

    mock_reply_webapp.assert_called_once()
    assert mock_reply_webapp.call_args.args[2:] == ("history", "เปิดประวัติ")


@patch("app.services.line_handler.get_line_clients")
@patch("app.services.line_handler.reply_messages", side_effect=RuntimeError("LINE unavailable"))
def test_failed_event_is_not_marked_and_is_propagated(mock_reply, mock_get_clients):
    mock_get_clients.return_value = (MagicMock(), MagicMock(), MagicMock())
    db = get_test_db()
    event = MagicMock(spec=FollowEvent)
    event.reply_token = "reply-failure"
    event.webhook_event_id = "event-failure"
    event.source = MagicMock()
    event.source.user_id = "failed-user"

    with pytest.raises(RuntimeError, match="LINE unavailable"):
        handle_line_events([event], db)

    assert db.query(ProcessedWebhook).filter_by(event_id="event-failure").count() == 0


@patch("app.services.line_handler.get_line_clients")
def test_successful_event_is_idempotent(mock_get_clients):
    messaging = MagicMock()
    mock_get_clients.return_value = (MagicMock(), messaging, MagicMock())
    db = get_test_db()
    event = MagicMock(spec=FollowEvent)
    event.reply_token = "reply-success"
    event.webhook_event_id = "event-success"
    event.source = MagicMock()
    event.source.user_id = "success-user"

    handle_line_events([event], db)
    handle_line_events([event], db)

    assert db.query(ProcessedWebhook).filter_by(event_id="event-success").count() == 1
    assert messaging.reply_message.call_count == 1
