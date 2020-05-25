from typing import Optional


class SpaceConfig:
    def __init__(
            self,
            key,
            title,
            bot_token=None,
            peoplebook_is_public=False,
            **other_data
    ):
        self.key = key
        self.title = title
        self.bot_token = bot_token
        self.other_data = other_data
        self.peoplebook_is_public = peoplebook_is_public

    def __str__(self):
        return self.key

    @classmethod
    def from_record(cls, record):
        return cls(**record)


def get_space_config(mongo_db, space_name) -> Optional[SpaceConfig]:
    collection = mongo_db.get_collection('spaces')
    raw_config = collection.find_one({'key': space_name})
    if not raw_config:
        return None
    return SpaceConfig.from_record(raw_config)
