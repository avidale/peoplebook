from utils.chat_data import ChatData
from utils.spaces import SpaceConfig
from utils.sugar import fill_none


def get_public_chat_intro_text(space: SpaceConfig, chat_data: ChatData):
    if chat_data.public_chat_intro_text:
        return chat_data.public_chat_intro_text
    if space.public_chat_intro_text:
        return space.public_chat_intro_text
    whois_tag = fill_none(chat_data.whois_tag, space.whois_tag)
    text = f'Добро пожаловать в чат сообщества {space.title}.\n' \
        f'Пожалуйста, представьтесь сообществу.\n' \
        f'Расскажите:\n' \
        f'- чем вы занимаетесь или занимались;\n' \
        f'- на какие темы с вами стоит поговорить;\n' \
        f'- как с вами можно связаться.\n' \
        f'Обязательно включите в своё сообщение тег {whois_tag}, иначе я не распознаю его.'
    # todo: add the kick text.
    return text


def get_public_chat_greeting_text(space: SpaceConfig, chat_data: ChatData):
    if chat_data.public_chat_greeting_text:
        return chat_data.public_chat_greeting_text
    if space.public_chat_greeting_text:
        return space.public_chat_greeting_text
    return 'Ура! Ваше приветствие распознано и появится в пиплбуке сообщества.'


def get_public_chat_failed_greeting_text(space: SpaceConfig, chat_data: ChatData):
    return 'Спасибо, что вы представились! ' \
           'Мне нравится ваше представление, но хотелось бы узнать о вас побольше. ' \
           'Пожалуйста, отредактируйте ваше сообщение, добавив больше деталей.'


def get_kick_timeout(space: SpaceConfig, chat_data: ChatData):
    if chat_data.kick_timeout is not None:
        return chat_data.kick_timeout
    return space.kick_timeout or 0
