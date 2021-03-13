import re

from utils.database import Database
from utils.dialogue_management import Context

from utils.spaces import SpaceConfig

from peoplebot.scenarios.peoplebook_auth import make_pb_url


CREATE_A_SPACE = 'Добавить собщество'
CANCEL = 'Отмена'


FORBIDDEN_SPACE_NAMES = {
    'about',
    'admin',
    'bot',
    'contacts',
    'details',
    'faq',
    'father_bot',
    'features',
    'help',
    'main',
    'meta',
    'prices',
}

INTENT_SET_TITLE = 'create_a_space__set_title'
INTENT_SET_KEY = 'create_a_space__set_key'
INTENT_SET_BOT_TOKEN = 'create_a_space__set_bot_token'


def space_creation(ctx: Context, database: Database):
    space_to_create = ctx.user_object.get('space_to_create') or {}
    if not ctx.user_object.get('username'):
        ctx.intent = 'has_no_username'
        ctx.response = 'Чтобы общаться со мной, пожалуйста, создайте себе юзернейм.'
    elif ctx.text_normalized == CREATE_A_SPACE.lower():
        ctx.intent = 'create_a_space'
        ctx.response = 'Отлично! Начинаем добавление, это займёт три шага. ' \
                       'Для начала, отправьте мне название вашего сообщества.'
        ctx.suggests.append(CANCEL)
        ctx.expected_intent = INTENT_SET_TITLE
        space_to_create = {
            'owner_uid': ctx.user_object['tg_id'],
            'owner_username': ctx.user_object['username'],
            'admins': [ctx.user_object['username']],
        }
        ctx.the_update = {'$set': {'space_to_create': space_to_create}}
    elif ctx.text_normalized == 'отмена':
        ctx.intent = 'create_a_space__cancel'
        ctx.response = 'Хорошо! Прекращаю добавления сообщества. ' \
                       'Напишите мне что-нибудь для продолжения.'
        ctx.suggests.append('Продолжим наш разговор')
    elif ctx.last_expected_intent == INTENT_SET_TITLE:
        # todo: validate the length of the space title
        ctx.intent = INTENT_SET_TITLE
        ctx.expected_intent = INTENT_SET_KEY
        ctx.response = 'Отличное название, так и запишем! ' \
                       '\nТеперь придумайте код сообщества. ' \
                       '\nОн должен состоять из латинских букв и цифр в нижнем регистре ' \
                       '(их можно разделять дефисом или символом "_").' \
                       '\nЭтот код станет частью адреса сообщества на сайте.'
        ctx.suggests.append(CANCEL)
        space_to_create['title'] = ctx.text
        ctx.the_update = {'$set': {'space_to_create': space_to_create}}
    elif ctx.last_expected_intent == INTENT_SET_KEY:
        ctx.intent = INTENT_SET_KEY
        key = ctx.text.strip()
        if len(key) < 3:
            ctx.expected_intent = INTENT_SET_KEY
            ctx.response = 'Этот код слишком короткий. Пожалуйста, попробуйте другой.'
        elif not re.match('^[a-z0-9][a-z0-9_\\-]+[a-z0-9]$', key):
            ctx.expected_intent = INTENT_SET_KEY
            ctx.response = 'Код должен состоять из цифр и латинских букв в нижнем регистре. ' \
                           'Пожалуйста, попробуйте ещё раз.'
        elif key in FORBIDDEN_SPACE_NAMES or database.mongo_spaces.find_one({'key': key}) is not None:
            ctx.expected_intent = INTENT_SET_KEY
            ctx.response = 'Сообщество с таким кодом уже есть. Пожалуйста, придумайте другой код.'
        else:
            space_to_create['key'] = key
            try:
                # test that the space can be created
                new_space = SpaceConfig.from_record(space_to_create)
                database.mongo_spaces.insert_one(space_to_create)
                url = '/admin/{}/details'.format(new_space.key)
                url = make_pb_url(url, user_tg_id=ctx.user_object['tg_id'])
                ctx.response = 'Сообщество успешно добавлено!' \
                               '\nНастроить его вы можете <a href="{}">по этой ссылке</a>.' \
                               '\nОстался последний и самый сложный шаг. ' \
                               'Вы должны написать боту @BotFather и создать через него нового бота ' \
                               '- админа для вашего сообщества, придумав ему имя и юзернейм.' \
                               '\nПосле этого пришлите мне токен, который даст вам BotFather.'.format(url)
                ctx.expected_intent = INTENT_SET_BOT_TOKEN
                ctx.the_update = {'$set': {'space_to_create': space_to_create}}
            except Exception:
                ctx.response = 'Что-то пошло не так при добавлении сообщества, простите. ' \
                               'Пожалуйста, обратитесь к админу - @cointegrated.'
                ctx.suggests.append('Назад')
    elif ctx.last_expected_intent == INTENT_SET_BOT_TOKEN:
        key = space_to_create.get('key')
        ctx.intent = INTENT_SET_BOT_TOKEN
        database.mongo_spaces.update_one({'key': key}, {'$set': {'bot_token': ctx.text}})
        database.update_spaces_cache()

        from peoplebot.new_main import MULTIVERSE
        MULTIVERSE.init_spaces()
        MULTIVERSE.create_bots()
        # todo: maybe force adding a route
        MULTIVERSE.set_web_hooks()
        ctx.response = 'Всё готово! ' \
                       'Теперь переходите к созданному вами боту и начинайте управлять вашим сообществом.' \
                       '\n\nЧто вы можете сделать:' \
                       '\n - Написать боту, чтобы понять, как он работает;' \
                       '\n - Добавить через бота членов в сообщество;' \
                       '\n - Заполнить через бота свою страничку в пиплбуке;' \
                       '\n - Пройти по ссылке выше и заполнить настройки сообщества;' \
                       '\n\nЕсли что-то будет непонятно, пишите @cointegrated.'
        # todo: ask for bot's username
        # todo: add a scenario of filling the peoplebook
        # todo: add a scenario of adding members
        # todo: add a scenario of creating events
        ctx.suggests.append('В начало')
    return ctx
