import pytest
import peoplebot

from utils.dialogue_management import Context
from utils.spaces import SpaceConfig
from peoplebot.scenarios.dog_mode import doggy_style
from peoplebot.scenarios.coffee import TAKE_PART, NOT_TAKE_PART, INTENT_COFFEE_PUSH_REMIND
from peoplebot.response_logic import respond


from .conftest import make_mocked_message  # noqa


TEST_SPACE = SpaceConfig(key='test', title='TestSpace')


def test_everything_is_ok():
    """ This is just a simple example of how a test may be created. """
    assert "A" == "A"


@pytest.mark.parametrize("text,expected_intent", [
    ("привет", None),
    ("покажи встречи", None),
    ("участвовать в следующем кофе", None),
    ("мой пиплбук", None),
    ("да", None),
    ("добавить членов", None),
    ("сука бля", "DOG"),
    ("чё выёбываешься", "DOG"),
    ("ну ты пидор", "DOG"),
])
def test_dog_mode_activation(mocked_member_uo, mocked_db, text, expected_intent):
    ctx = Context(text=text, user_object=mocked_member_uo, space=TEST_SPACE)
    new_ctx = doggy_style(ctx, database=mocked_db)
    assert new_ctx.intent == expected_intent


@pytest.mark.parametrize("text,expected_intent", [
    ("привет", "HELLO"),
    ("покажи встречи", "EVENT_GET_LIST"),
    ("Участвовать в следующем кофе", "TAKE_PART"),
    ("мой пиплбук", "PEOPLEBOOK_GET_FAIL"),
    ("да", "OTHER"),
    ("абырвалг", "OTHER"),
    ("добавить членов", "OTHER"),
    ("создать встречу", "OTHER"),
    ("сука бля", "DOG"),
    ("чё выёбываешься", "DOG"),
    ("ну ты пидор", "DOG"),
])
def test_basic_responses(mocked_sender, mocked_db, mocked_space, text, expected_intent):
    respond(
        message=make_mocked_message(text),
        database=mocked_db,
        sender=mocked_sender,
        space_cfg=mocked_space,
    )
    assert len(mocked_sender.sent_messages) == 1
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == expected_intent


@pytest.mark.parametrize("text,expected_intent", [
    ("добавить новых членов клуба", "MEMBER_ADD_INIT"),
    ("добавь членов сообщества", "FRIEND_ADD_INIT"),
    ("добавить членов", "FRIEND_OR_MEMBER_ADD_TRY"),
    ("создать встречу", "EVENT_CREATE_INIT"),
])
def test_admin(mocked_sender, mocked_db, mocked_space, text, expected_intent):
    respond(
        message=make_mocked_message(text, username='an_admin'),
        database=mocked_db,
        sender=mocked_sender,
        space_cfg=mocked_space,
    )
    assert len(mocked_sender.sent_messages) == 1
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == expected_intent


def test_roles(mocked_db, mocked_space):
    assert mocked_db.is_at_least_guest({'username': 'a_guest', 'space': mocked_space.key})
    assert not mocked_db.is_at_least_member({'username': 'a_guest', 'space': mocked_space.key})


def test_guest_can_see_coffee(mocked_sender, mocked_db, mocked_space):
    respond(
        message=make_mocked_message('привет', username='a_guest'),
        database=mocked_db,
        sender=mocked_sender,
        space_cfg=mocked_space,
    )
    assert len(mocked_sender.sent_messages) == 1
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == 'HELLO'
    assert TAKE_PART in last_message.suggests
    assert NOT_TAKE_PART not in last_message.suggests

    respond(
        message=make_mocked_message(TAKE_PART, username='a_guest'),
        database=mocked_db,
        sender=mocked_sender,
        space_cfg=mocked_space,
    )
    assert len(mocked_sender.sent_messages) == 2
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == 'TAKE_PART'
    assert TAKE_PART not in last_message.suggests
    assert NOT_TAKE_PART in last_message.suggests


def test_coffee_feedback(mocked_sender, mocked_db, mocked_space):
    mocked_sender(
        text='Вы уже договорились?',
        database=mocked_db,
        user_id=123,
        intent=INTENT_COFFEE_PUSH_REMIND,
        reset_intent=True,
    )
    assert mocked_db.mongo_users.find_one({'tg_id': 123})['last_intent'] == INTENT_COFFEE_PUSH_REMIND
    respond(
        message=make_mocked_message('да', username='a_guest', user_id=123),  # user id is required to track context
        database=mocked_db,
        sender=mocked_sender,
        space_cfg=mocked_space,
    )
    assert mocked_db.is_at_least_guest(user_object={'username': 'a_guest', 'space': mocked_space.key})
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.text.startswith('Ура')
