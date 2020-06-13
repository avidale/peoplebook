from utils.chat_data import ChatData, ChatUserStats
from utils.database import Database


def update_chat_data(db: Database, chat_id: int, space: str, raw_data: dict) -> ChatData:
    filters = {'chat_id': chat_id, 'space': space}
    old_object = ChatData.from_record(
        record=db.mongo_chats.find_one(filters),
        chat_id=chat_id,
        space=space,
    )
    old_object.update(raw_data=raw_data)
    db.mongo_chats.update_one(
        filters,
        {'$set': old_object.to_dict()},  # todo: maybe don't update the keys
        upsert=True,
    )
    return old_object


def update_chat_stats(user_object, db: Database, chat_id: int, kicked=False):
    tg_id = user_object.get('tg_id')
    assert tg_id is not None
    old_object = ChatUserStats.from_record(
        record=db.mongo_chat_members.find_one({'tg_id': tg_id, 'chat_id': chat_id}),
        user_id=tg_id,
        chat_id=chat_id,
    )
    old_object.username = user_object.get('username')
    old_object.kicked = kicked
    old_object.update()
    db.mongo_chat_members.update_one(
        {'tg_id': tg_id, 'chat_id': chat_id},
        {'$set': old_object.to_dict()},  # todo: maybe don't update the keys
        upsert=True,
    )
    return old_object


def get_all_chat_users(db: Database, chat_id: int):
    return [
        u.get('username')
        for u in db.mongo_chat_members.find({'chat_id': chat_id, 'kicked': False})
        if u.get('username')
    ]


def tag_everyone(db: Database, chat_id: int):
    usernames = get_all_chat_users(db=db, chat_id=chat_id)
    if not usernames:
        return 'Мне некого призывать, увы!'
    return ' '.join([
        '@{}'.format(username)
        for username in usernames
    ])