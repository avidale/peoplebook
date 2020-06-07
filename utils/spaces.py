from typing import Optional


class FeatureName:
    COFFEE = 'coffee'
    EVENTS = 'events'
    PEOPLEBOOK = 'peoplebook'


class MembershipStatus:
    NONE = 'none'
    GUEST = 'guest'
    MEMBER = 'member'
    ADMIN = 'admin'
    OWNER = 'owner'


class SpaceConfig:
    def __init__(
            self,
            key,
            title,
            bot_token=None,
            bot_username=None,
            peoplebook_is_public=False,
            member_chat_id=None,
            guest_chat_id=None,
            owner_uid=None,
            owner_username='cointegrated',
            admins=None,
            text_help_authorized=None,  # todo: default one
            text_help_unauthorized=None,  # todo: default one
            text_after_messages='',
            add_chat_members_to_community=MembershipStatus.NONE,
            require_whois=False,
            whois_tag='#whois',
            public_chat_intro_text=None,
            public_chat_greeting_text=None,
            **other_data
    ):
        self.key = key
        self.title = title
        self.bot_token = bot_token
        self.bot_username = bot_username
        self.peoplebook_is_public = peoplebook_is_public
        self.member_chat_id = member_chat_id
        self.guest_chat_id = guest_chat_id
        self.owner_uid = owner_uid  # the one who runs the space and will receive bug reports
        self.owner_username = owner_username
        self.admins = admins or []  # list of usernames of space admins (who can create events etc.)

        # basic NLG setup
        self.text_help_authorized = text_help_authorized
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

        self.other_data = other_data

    def __str__(self):
        return self.key

    @classmethod
    def from_record(cls, record):
        return cls(**record)

    def supports(self, feature):
        # todo: make it configurable
        if feature == FeatureName.COFFEE:
            return True
        elif feature == FeatureName.EVENTS:
            return self.key == 'kv'
        elif feature == FeatureName.PEOPLEBOOK:
            return True
        else:
            return True

    def get_text_help_unauthorized(self):
        if self.text_help_unauthorized:
            return self.text_help_unauthorized
        return f'Это бот сообщества {self.title}.\n' \
            f'Чтобы получить к нему доступ, обратитесь к администратору сообщества.'

    def get_text_help_authorized(self):
        if self.text_help_authorized:
            return self.text_help_authorized
        return f'Это бот сообщества {self.title}. ' \
            f'Я умею:' \
            f'- назначать random coffee между участниками;' \
            f'- показывать пиплбук (список профилей членов сообщества);' \
            f'- назначать встречи сообщества и собирать на них гостей.'

    def get_public_chat_intro_text(self):
        if self.public_chat_intro_text:
            return self.public_chat_intro_text
        text = f'Добро пожаловать в чат сообщества {self.title}.\n' \
            f'Пожалуйста, представьтесь сообществу.\n' \
            f'Расскажите:\n' \
            f'- чем вы занимаетесь или занимались;\n' \
            f'- на какие темы с вами стоит поговорить;\n' \
            f'- как с вами можно связаться.\n' \
            f'Обязательно включите в своё сообщение тег {self.whois_tag}, иначе я не распознаю его.'
        # todo: add the kick text.
        return text

    def get_public_chat_greeting_text(self):
        if self.public_chat_greeting_text:
            return self.public_chat_greeting_text
        return 'Ура! Ваше приветствие распознано и появится в пиплбуке сообщества.'

    def get_public_chat_failed_greeting_text(self):
        return 'Спасибо, что вы представились! ' \
               'Мне нравится ваше представление, но хотелось бы узнать о вас побольше. ' \
               'Пожалуйста, отредактируйте ваше сообщение, добавив больше деталей.'


def get_space_config(mongo_db, space_name) -> Optional[SpaceConfig]:
    collection = mongo_db.get_collection('spaces')
    raw_config = collection.find_one({'key': space_name})
    if not raw_config:
        return None
    return SpaceConfig.from_record(raw_config)
