from .conftest import mocked_sender, mocked_db  # noqa


def test_reset_intent(mocked_sender, mocked_db):
    uid = 123
    mocked_db.mongo_users.insert_one({'tg_id': uid})
    mocked_sender(
        text='Вы уже договорились?',
        database=mocked_db,
        intent='custom_intent',
        reset_intent=True,
        user_id=uid,
    )
    assert mocked_db.mongo_users.find_one({'tg_id': uid})['last_intent'] == 'custom_intent'
