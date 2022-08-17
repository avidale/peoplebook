from typing import Optional

from config import DEFAULT_SPACE, DEMIURGE
from peoplebot.scenarios.peoplebook_auth import make_pb_url


class FeatureName:
    COFFEE = 'coffee'
    EVENTS = 'events'
    PEOPLEBOOK = 'peoplebook'


class MembershipStatus:
    NONE = 'none'
    NO_STATUS = 'no_status'
    ANYONE = 'anyone'
    GUEST = 'guest'
    FRIEND = 'friend'
    MEMBER = 'member'
    ADMIN = 'admin'
    OWNER = 'owner'

    @classmethod
    def is_at_least(cls, user_status, level):
        if level in {cls.NO_STATUS, cls.ANYONE, cls.NONE}:
            return True
        if level == cls.OWNER:
            return user_status in {cls.OWNER}
        if level == cls.ADMIN:
            return user_status in {cls.OWNER, cls.ADMIN}
        if level == cls.MEMBER:
            return user_status in {cls.OWNER, cls.ADMIN, cls.MEMBER}
        if level == cls.FRIEND:
            return user_status in {cls.OWNER, cls.ADMIN, cls.MEMBER, cls.FRIEND}
        if level == cls.GUEST:
            return user_status in {cls.OWNER, cls.ADMIN, cls.MEMBER, cls.FRIEND, cls.GUEST}
        return False


MEMBERSHIP_STATUSES = [
    (MembershipStatus.NONE, 'Не менять статус'),
    (MembershipStatus.GUEST, 'Поднять до гостя сообщества'),
    (MembershipStatus.FRIEND, 'Поднять до простого члена сообщества'),
    (MembershipStatus.MEMBER, 'Поднять до привилегированного члена сообщества'),
]

MEMBERSHIP_STATUSES_ALL = [
    (MembershipStatus.ANYONE, 'Кто угодно'),
    (MembershipStatus.GUEST, 'Гость сообщества'),
    (MembershipStatus.FRIEND, 'Простой член сообщества'),
    (MembershipStatus.MEMBER, 'Привилегированный член сообщества (член Клуба)'),
    (MembershipStatus.ADMIN, 'Админ сообщества'),
]


class SpaceConfig:
    def __init__(
            self,
            key,
            title,
            bot_token=None,
            bot_username=None,
            anyone_can_enter=False,
            peoplebook_is_public=False,
            member_chat_id=None,
            guest_chat_id=None,
            owner_uid=None,
            owner_username=DEMIURGE,
            admins=None,
            text_help_authorized=None,  # todo: default one
            text_help_guests=None,  # todo: default one
            text_help_unauthorized=None,  # todo: default one
            text_after_messages='',
            add_chat_members_to_community=MembershipStatus.NONE,
            require_whois=False,
            whois_tag='#whois',
            public_chat_intro_text=None,
            public_chat_greeting_text=None,
            add_whois_to_peoplebook=False,
            kick_timeout=None,

            web_show_pb_club=False,
            web_show_pb_community=True,
            web_show_pb_event=False,
            web_show_pb_all=True,

            feature_coffee_on=True,
            feature_events_on=False,
            feature_peoplebook_on=True,

            who_can_create_events='admin',
            who_can_add_invite_to_events='member',
            can_external_guests_be_invited=True,
            who_can_use_random_coffee='guest',

            db=None,  # a global database object
            **other_data
    ):
        self.key = key
        self.title = title
        self.bot_token = bot_token
        self.bot_username = bot_username
        self.anyone_can_enter = anyone_can_enter,
        self.peoplebook_is_public = peoplebook_is_public
        self.member_chat_id = member_chat_id
        self.guest_chat_id = guest_chat_id
        self.owner_uid = owner_uid  # the one who runs the space and will receive bug reports
        self.owner_username = owner_username
        self.admins = admins or []  # list of usernames of space admins (who can create events etc.)

        # basic NLG setup
        self.text_help_authorized = text_help_authorized
        self.text_help_guests = text_help_guests
        self.text_help_unauthorized = text_help_unauthorized
        if text_after_messages.strip() and not text_after_messages.startswith('\n'):
            text_after_messages = '\n' + text_after_messages
        self.text_after_messages = text_after_messages

        # setup of the whois process
        self.add_chat_members_to_community = add_chat_members_to_community
        self.require_whois = require_whois
        self.whois_tag = whois_tag
        self.public_chat_intro_text = public_chat_intro_text  # before whois
        self.public_chat_greeting_text = public_chat_greeting_text  # after whois
        self.add_whois_to_peoplebook = add_whois_to_peoplebook
        self.kick_timeout = kick_timeout  # None means no kick

        # access settings
        self.web_show_pb_club = web_show_pb_club
        self.web_show_pb_community = web_show_pb_community
        self.web_show_pb_event = web_show_pb_event
        self.web_show_pb_all = web_show_pb_all

        # features
        self.feature_coffee_on = feature_coffee_on
        self.feature_peoplebook_on = feature_peoplebook_on
        self.feature_events_on = feature_events_on

        # feature access based on user level
        self.who_can_create_events = who_can_create_events
        self.who_can_add_invite_to_events = who_can_add_invite_to_events
        self.can_external_guests_be_invited = can_external_guests_be_invited
        self.who_can_use_random_coffee = who_can_use_random_coffee

        self.other_data = other_data
        self.db = db

    def __str__(self):
        return self.key

    @classmethod
    def from_record(cls, record, db):
        return cls(**record, db=db)

    def supports(self, feature) -> bool:
        # todo: make it configurable
        if feature == FeatureName.COFFEE:
            return bool(self.feature_coffee_on)
        elif feature == FeatureName.EVENTS:
            return self.key in {'kv', 'phoenix'} or bool(self.feature_events_on)
        elif feature == FeatureName.PEOPLEBOOK:
            return bool(self.feature_peoplebook_on)
        else:
            return True

    def get_text_help_unauthorized(self):
        if self.text_help_unauthorized:
            return self.text_help_unauthorized
        return f'Это бот сообщества {self.title}.\n' \
            f'Чтобы получить к нему доступ, обратитесь к администратору сообщества.'

    def get_text_help_guests(self):
        if self.text_help_guests:
            return self.text_help_guests
        return self.get_text_help_unauthorized()

    def get_text_help_authorized(self, user_object=None):
        if self.text_help_authorized:
            result = self.text_help_authorized
        else:
            result = f'Это бот сообщества {self.title}. ' \
                f'\nЯ умею:' \
                f'\n- назначать random coffee между участниками;' \
                f'\n- показывать пиплбук (список профилей членов сообщества);' \
                f'\n- назначать встречи сообщества и собирать на них гостей.'
        if user_object is not None and user_object.get('tg_id'):
            url = make_pb_url('/{}/all'.format(self.key), user_object['tg_id'])
            result = result + f'\n\n<a href="{url}">Авторизоваться и посмотреть пиплбук</a>'
        return result

    @property
    def community_is_split(self) -> bool:
        return self.key in {DEFAULT_SPACE, 'test', 'autotest'}


def get_space_config(mongo_db, space_name) -> Optional[SpaceConfig]:
    collection = mongo_db.get_collection('spaces')
    raw_config = collection.find_one({'key': space_name})
    if not raw_config:
        return None
    return SpaceConfig.from_record(raw_config, db=mongo_db)
