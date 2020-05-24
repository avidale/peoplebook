import pymongo

from datetime import datetime
from typing import Callable

from utils.database import Database
from utils.dialogue_management import Context
from utils import matchers

from peoplebot.scenarios.coffee_match_maker import generate_good_pairs
from peoplebot.scenarios.peoplebook_auth import make_pb_url

from config import ADMIN_UID, BATCH_MESSAGE_TIMEOUT, DEFAULT_SPACE

import random
import time

TAKE_PART = 'Участвовать в следующем кофе'
NOT_TAKE_PART = 'Не участвовать в следующем кофе'


INTENT_COFFEE_PUSH_FIRST = 'coffee_push_first'
INTENT_COFFEE_PUSH_REMIND = 'coffee_push_remind'
INTENT_COFFEE_PUSH_FEEDBACK = 'coffee_push_feedback'


def get_coffee_score(text):
    text = text.lower()
    if 'участ' in text and ('кофе' in text or 'coffee' in text):
        if 'не ' in text or 'отказ' in text:
            return -1
        return 1
    return 0


def daily_random_coffee(database: Database, sender: Callable, force_restart=False):
    if force_restart or datetime.today().weekday() == 5:  # on saturday, we recalculate the matches
        user_to_matches = generate_good_pairs(database)
        database.mongo_coffee_pairs.insert_one({'date': str(datetime.utcnow()), 'matches': user_to_matches})

    last_matches = database.mongo_coffee_pairs.find_one({}, sort=[('_id', pymongo.DESCENDING)])

    if last_matches is None:
        sender(
            text='я не нашёл матчей, посмотри логи плз',
            user_id=ADMIN_UID, database=database, notify_on_error=False
        )
    else:
        str_uid_to_username = {str(uo['tg_id']): uo['username'] for uo in database.mongo_users.find({})}
        converted_matches = {
            str_uid_to_username[key]: [str_uid_to_username[value] for value in values]
            for key, values in last_matches['matches'].items()
        }
        sender(
            text='вот какие матчи сегодня: {}'.format(converted_matches),
            user_id=ADMIN_UID, database=database, notify_on_error=False
        )
        for username, matches in converted_matches.items():
            user_obj = database.mongo_users.find_one({'username': username})
            if user_obj is None:
                sender(
                    text='юзер {} не был найден!'.format(username),
                    user_id=ADMIN_UID, database=database, notify_on_error=False
                )
            else:
                remind_about_coffee(user_obj, matches, database=database, sender=sender, force_restart=force_restart)
                time.sleep(BATCH_MESSAGE_TIMEOUT)


def remind_about_coffee(user_obj, matches, database: Database, sender: Callable, force_restart=False):
    user_id = user_obj['tg_id']
    match_texts = []
    for m in matches:
        in_pb = database.mongo_peoplebook.find_one({'username': m, 'space': DEFAULT_SPACE})
        if in_pb:
            match_texts.append('@{} (<a href="{}">пиплбук</a>)'.format(m, make_pb_url('/person/' + m, user_id)))
        else:
            match_texts.append('@{}'.format(m))

    with_whom = 'с {}'.format(match_texts[0])
    for next_match in match_texts[1:]:
        with_whom = with_whom + ' и c {}'.format(next_match)

    response = None
    if force_restart or datetime.today().weekday() == 5:  # saturday
        response = 'На этой неделе вы пьёте кофе {}.\nЕсли вы есть, будьте первыми!'.format(with_whom)
        intent = INTENT_COFFEE_PUSH_FIRST
    elif datetime.today().weekday() == 4:  # friday
        response = 'На этой неделе вы, наверное, пили кофе {}.\nКак оно прошло?'.format(with_whom)
        intent = INTENT_COFFEE_PUSH_FEEDBACK
        # todo: remember the feedback (with expected_intent)
    elif datetime.today().weekday() == 0:  # monday
        response = 'Напоминаю, что на этой неделе вы пьёте кофе {}.\n'.format(with_whom) + \
            '\nНадеюсь, вы уже договорились о встрече?	\U0001f609'
        intent = INTENT_COFFEE_PUSH_REMIND
    if response is not None:
        user_in_pb = database.mongo_peoplebook.find_one({'username': user_obj.get('username'), 'space': DEFAULT_SPACE})
        if not user_in_pb:
            response = response + '\n\nКстати, кажется, вас нет в пиплбуке, а жаль: ' \
                                  'с пиплбуком даже незнакомому собеседнику проще будет начать с вами общение.' \
                                  '\nПожалуйста, когда будет время, напишите мне "мой пиплбук" ' \
                                  'и заполните свою страничку.\nЕсли вы есть, будьте первыми!'
        # avoiding circular imports
        from peoplebot.scenarios.suggests import make_standard_suggests
        suggests = make_standard_suggests(database=database, user_object=user_obj)
        sender(user_id=user_id, text=response, database=database, suggests=suggests,
               reset_intent=True, intent=intent)


def try_coffee_management(ctx: Context, database: Database):
    if not database.is_at_least_guest(user_object=ctx.user_object):
        return ctx
    coffee_score = get_coffee_score(ctx.text)
    if ctx.text == TAKE_PART or coffee_score == 1:
        if ctx.user_object.get('username') is None:
            ctx.intent = 'COFFEE_NO_USERNAME'
            ctx.response = 'Чтобы участвовать в random coffee, нужно иметь имя пользователя в Телеграме.' \
                           '\nПожалуйста, создайте себе юзернейм (ТГ > настройки > изменить профиль > ' \
                           'имя пользователя) и попробуйте снова.\nВ случае ошибки напишите @cointegrated.' \
                           '\nЕсли вы есть, будьте первыми!'
            return ctx
        ctx.the_update = {"$set": {'wants_next_coffee': True}}
        ctx.response = 'Окей, на следующей неделе вы будете участвовать в random coffee!'
        ctx.intent = 'TAKE_PART'
    elif ctx.text == NOT_TAKE_PART or coffee_score == -1:
        ctx.the_update = {"$set": {'wants_next_coffee': False}}
        ctx.response = 'Окей, на следующей неделе вы не будете участвовать в random coffee!'
        ctx.intent = 'NOT_TAKE_PART'
    return ctx


def try_coffee_feedback_collection(ctx: Context, database: Database):
    if not database.is_at_least_guest(user_object=ctx.user_object):
        return ctx
    if ctx.last_intent in {INTENT_COFFEE_PUSH_FEEDBACK, INTENT_COFFEE_PUSH_REMIND}:
        if matchers.is_like_yes(ctx.text_normalized):
            ctx.intent = ctx.last_intent + '_did_agree'
            ctx.response = 'Ура! Я рад, что у вас получается.'
        elif matchers.like_will_meet(ctx.text_normalized):
            ctx.intent = ctx.last_intent + '_will_meet'
            ctx.response = 'Отлично! Надеюсь, у вас всё получится.\n' \
                           'Когда встретитесь, не забудьте поделиться фидбеком :)'
        elif ctx.last_intent == INTENT_COFFEE_PUSH_REMIND and matchers.is_like_no(ctx.text_normalized):
            ctx.intent = ctx.last_intent + '_not'
            ctx.response = 'Хорошо. Пожалуйста, напишите друг другу, не слишком затягивая.'
        elif matchers.like_did_not_meet(ctx.text_normalized) or matchers.like_did_not_agree(ctx.text):
            ctx.intent = ctx.last_intent + '_did_not_meet'
            ctx.response = 'Жаль, что у вас не получилось.\n' \
                           'Надеюсь, в следующий раз встретиться удастся!\n' \
                           'Кстати, если у вас нет времени или желания на встречи, ' \
                           'можете сказать мне "Не участвовать в следующем кофе".'
        elif matchers.like_positive_feedback(ctx.text_normalized) or matchers.like_positive_emoji(ctx.text):
            ctx.intent = ctx.last_intent + '_positive'
            ctx.response = random.choice([
                'Отлично! Очень рад за вас \U0001F917',
                'Здорово, что всё прошло хорошо. Чувствую, что не зря вас сматчил \U0001F604',
                'Класс! Продолжайте в том же духе \U0001F4AA',
                'Ура! Я так и знал, что вам понравится \U0001F603'
            ])
        else:
            ctx.intent = 'coffee_feedback_probably'
            ctx.response = random.choice([
                'Благодарю за обратную связь! \U00002615',
                'Спасибо за фибдек! Я рад, что вы пользуетесь Random Coffee \U0001F642',
                'Спасибо, что делитесь своими впечатлениями. Если вы есть, будьте первыми!'
            ])
    return ctx
