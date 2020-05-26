from typing import Optional


class FEATURE_NAMES:
    COFFEE = 'coffee'
    EVENTS = 'events'
    PEOPLEBOOK = 'peoplebook'


class SpaceConfig:
    def __init__(
            self,
            key,
            title,
            bot_token=None,
            peoplebook_is_public=False,
            member_chat_id=None,
            guest_chat_id=None,
            owner_uid=None,
            admins=None,
            **other_data
    ):
        self.key = key
        self.title = title
        self.bot_token = bot_token
        self.peoplebook_is_public = peoplebook_is_public
        self.member_chat_id = member_chat_id
        self.guest_chat_id = guest_chat_id
        self.owner_uid = owner_uid  # the one who runs the space and will receive bug reports
        self.admins = admins or []  # list of usernames of space admins (who can create events etc.)

        self.other_data = other_data

    def __str__(self):
        return self.key

    @classmethod
    def from_record(cls, record):
        return cls(**record)

    def supports(self, feature):
        # todo: make it configurable
        if feature == FEATURE_NAMES.COFFEE:
            return True
        elif feature == FEATURE_NAMES.EVENTS:
            return self.key == 'kv'
        elif feature == FEATURE_NAMES.PEOPLEBOOK:
            return True
        else:
            return True


def get_space_config(mongo_db, space_name) -> Optional[SpaceConfig]:
    collection = mongo_db.get_collection('spaces')
    raw_config = collection.find_one({'key': space_name})
    if not raw_config:
        return None
    return SpaceConfig.from_record(raw_config)
