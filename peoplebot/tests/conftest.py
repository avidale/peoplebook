import mongomock
import pytest
import unittest.mock

from telebot.types import Message, User, Chat

from utils.database import Database
from utils.events import InvitationStatuses
from utils.messaging import TelegramSender
from utils.spaces import SpaceConfig
from peoplebot.response_logic import PROCESSED_MESSAGES


test_space_id = 'autotest'


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
def mocked_space_dict():
    return dict(
        key=test_space_id,
        title='Space for autotests',
        bot_token='lol:kek',
        admins=['an_admin'],
        text_help_authorized='help for internals',
        text_help_guests='help for guests',
        text_help_unauthorized='help for externals',
    )


@pytest.fixture()
def mocked_db(mocked_space_dict):
    db = MockedDatabase(mongo_url="no url")
    db.mongo_membership.insert_one({'username': 'a_member', 'is_member': True, 'space': test_space_id})
    db.mongo_events.insert_one({'code': 'an_event', 'title': 'An Event', 'date': '2030.12.30', 'space': test_space_id})
    db.mongo_participations.insert_one(
        {
            'event_code': 'an_event', 'username': 'a_guest', 'space': test_space_id,
            'status': InvitationStatuses.PAYMENT_PAID
        }
    )
    db.mongo_users.insert_one({'tg_id': 123, 'space': test_space_id})
    db.mongo_spaces.insert_one(mocked_space_dict)
    db.update_cache(force=True)
    return db


@pytest.fixture()
def mocked_space(mocked_space_dict):
    return SpaceConfig.from_record(mocked_space_dict)


@pytest.fixture()
def mocked_sender(mocked_space):
    return MockedSender(bot=MockedBot(), space=mocked_space)


def make_mocked_message(text, user_id=123, first_name='Юзер', username='a_member', message_id=None):
    if message_id is None:
        message_id = sum(len(subspace) for subspace in PROCESSED_MESSAGES.values())
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
