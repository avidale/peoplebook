import mongomock
import pytest
import unittest.mock

from telebot.types import Message, User, Chat

from utils.database import Database
from utils.messaging import TelegramSender
from peoplebot.response_logic import PROCESSED_MESSAGES


class MockedDatabase(Database):
    def _setup_client(self, mongo_url):
        self._mongo_client = mongomock.MongoClient()
        self._mongo_db = self._mongo_client.db


class MockedMessage:
    def __init__(self, text, intent, suggests):
        self.text = text
        self.intent = intent
        self.suggests = suggests


class MockedSender(TelegramSender):
    def __init__(self, *args, **kwargs):
        super(MockedSender, self).__init__(*args, **kwargs)
        self.sent_messages = []

    def __call__(self, *args, **kwargs):
        super(MockedSender, self).__call__(*args, **kwargs)
        self.sent_messages.append(MockedMessage(
            text=kwargs['text'], intent=kwargs.get('intent'),
            suggests=kwargs.get('suggests', [])
        ))


class MockedBot:
    def send_message(self, *args, **kwargs):
        pass

    def reply_to(self, *args, **kwargs):
        pass

    def send_document(self, *args, **kwargs):
        pass


@pytest.fixture()
def mocked_member_uo():
    return {}


@pytest.fixture()
def mocked_db():
    db = MockedDatabase(mongo_url="no url", admins=['an_admin'])
    db.mongo_membership.insert_one({'username': 'a_member', 'is_member': True})
    db.mongo_events.insert_one({'code': 'an_event', 'title': 'An Event', 'date': '2030.12.30'})
    db.mongo_participations.insert_one({'event_code': 'an_event', 'username': 'a_guest'})
    db.mongo_users.insert_one({'tg_id': 123})
    db._update_cache(force=True)
    return db


@pytest.fixture()
def mocked_sender():
    config = unittest.mock.Mock()
    config.ADMIN_UID = 12345
    return MockedSender(bot=MockedBot(), config=config)


def make_mocked_message(text, user_id=123, first_name='Юзер', username='a_member', message_id=None):
    if message_id is None:
        message_id = len(PROCESSED_MESSAGES)
    message = Message(
        message_id=message_id,
        from_user=User(id=user_id, is_bot=False, first_name=first_name, username=username),
        date=None,
        chat=Chat(id=user_id, type='private'),
        content_type=None,
        options={},
        json_string=None
    )
    message.text = text
    return message
