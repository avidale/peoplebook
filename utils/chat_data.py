import attr
import time


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


@attr.s
class ChatData:
    chat_id = attr.ib()
    space: str = attr.ib()
    message_count: int = attr.ib(default=0)
    last_active: float = attr.ib(default=None)
    raw_data: dict = attr.ib(default=None)

    # set specific properties, such as whois settings
    # None means using default settings propagated from the whole space
    add_chat_members_to_community: str = attr.ib(default=None)  # should belong to MembershipStatus
    require_whois: bool = attr.ib(default=None)
    whois_tag: bool = attr.ib(default=None)
    public_chat_intro_text: str = attr.ib(default=None)
    public_chat_greeting_text: str = attr.ib(default=None)
    add_whois_to_peoplebook: bool = attr.ib(default=None)
    kick_timeout: int = attr.ib(default=None)

    @property
    def title(self):
        return (self.raw_data or {}).get('title')

    def update(self, raw_data):
        self.message_count += 1
        self.last_active = time.time()
        self.raw_data = raw_data

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_record(cls, record, chat_id, space):
        if record is None:
            return cls(chat_id=chat_id, space=space)
        else:
            new_record = {
                k: v
                for k, v in record.items()
                if k not in {'_id'}
            }
            return cls(**new_record)
