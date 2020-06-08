import attr
import time

from utils.database import Database


@attr.s
class ChatUserStats:
    tg_id = attr.ib()
    chat_id = attr.ib()
    username: str = attr.ib(default=None)
    message_count: int = attr.ib(default=0)
    last_active: float = attr.ib(default=None)
    kicked: bool = attr.ib(default=False)

    def update(self):
        self.message_count += 1
        self.last_active = time.time()

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_record(cls, record, user_id, chat_id):
        if record is None:
            return cls(tg_id=user_id, chat_id=chat_id)
        else:
            new_record = {
                k: v
                for k, v in record.items()
                if k not in {'_id'}
            }
            return cls(**new_record)


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
