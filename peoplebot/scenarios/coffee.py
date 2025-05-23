import pymongo

from datetime import datetime

from utils.database import Database
from utils.dialogue_management import Context
from utils.messaging import BaseSender
from utils.spaces import SpaceConfig, FeatureName
from utils import matchers

from peoplebot.scenarios.coffee_match_maker import generate_good_pairs, days_since
from peoplebot.scenarios.peoplebook_auth import make_pb_url

from config import ADMIN_UID, BATCH_MESSAGE_TIMEOUT

import random
import time

TAKE_PART = 'Участвовать в следующем кофе'
NOT_TAKE_PART = 'Не участвовать в следующем кофе'


INTENT_COFFEE_PUSH_ALONE = 'coffee_push_alone'
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


def daily_random_coffee(database: Database, sender: BaseSender, space: SpaceConfig, force_restart=False):
    from peoplebot.scenarios.suggests import make_standard_suggests
    # do a cleanup: cut all inactive users from coffee until they deliberately decide to turn in
    for user in database.mongo_users.find({'wants_next_coffee': True, 'space': space.key}):
        if user.get('deactivated') or not user.get('last_activity') or days_since(user['last_activity']) >= 31:
            database.update_user_object(
                username_or_id=user.get('tg_id') or user.get('username'),
                space_name=space.key,
                change={'$set': {'wants_next_coffee': False}},
            )
            if days_since(user['last_activity']) >= 31:
                time.sleep(BATCH_MESSAGE_TIMEOUT)
                if user.get('tg_id'):
                    suggests = make_standard_suggests(database=database, user_object=user)
                    r = 'Добрый вечер! Поскольку вы месяц ничего не писали в бота, ' \
                        'я не могу определить, получаете ли вы мои сообщения.' \
                        '\nПоэтому на этой неделе я не стал ставить вас в пару Random Coffee.' \
                        'Чтобы снова начать участвовать в Random Coffee со следующей неделе, ' \
                        'нажмите "хочу участвовать в кофе" заново.\n'
                    if space.text_after_messages:
                        r += space.text_after_messages
                    sender(user_id=user.get('tg_id'), text=r, database=database, suggests=suggests,
                           reset_intent=True, intent='turn_coffee_off_by_timeout')

    # exit if the random coffee feature is currently off
    if not space.supports(FeatureName.COFFEE):
        return

    if force_restart or datetime.today().weekday() == 5:  # on saturday, we recalculate the matches
        now = datetime.utcnow()
        user_to_matches = generate_good_pairs(database, space=space, now=now)
        # in case of a single active user, "user_to_matches" is expected to be empty
        database.mongo_coffee_pairs.insert_one(
            {'date': str(now), 'matches': user_to_matches, 'space': space.key}
        )
    last_matches = database.mongo_coffee_pairs.find_one({'space': space.key}, sort=[('_id', pymongo.DESCENDING)])

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
        # sender(
        #     text='вот какие матчи сегодня: {}'.format(converted_matches),
        #     user_id=ADMIN_UID, database=database, notify_on_error=False
        # )
        for username, matches in converted_matches.items():
            user_obj = database.mongo_users.find_one({'username': username, 'space': space.key})
            if user_obj is None:
                sender(
                    text='юзер {} не был найден!'.format(username),
                    user_id=ADMIN_UID, database=database, notify_on_error=False
                )
            else:
                remind_about_coffee(
                    user_obj, matches, database=database, sender=sender, force_restart=force_restart, space=space
                )
                time.sleep(BATCH_MESSAGE_TIMEOUT)


def remind_about_coffee(
        user_obj, matches, database: Database, sender: BaseSender, space: SpaceConfig, force_restart=False
):
    # avoiding circular imports
    from peoplebot.scenarios.suggests import make_standard_suggests
    user_id = user_obj['tg_id']
    match_texts = []
    for m in matches:
        in_pb = database.find_peoplebook_profile(space_name=space.key, username=m, tg_id=m)
        # todo: find page by tg_id if it is not found by username
        if in_pb:
            match_texts.append('@{} (<a href="{}">пиплбук</a>)'.format(
                m, make_pb_url('/{}/person/{}'.format(space.key, m), user_id)
            ))
        else:
            match_texts.append('@{}'.format(m))

    first_day_condition = force_restart or datetime.today().weekday() == 5   # saturday

    if len(match_texts) == 0:  # found no matches
        if first_day_condition:
            response = "Привет! К сожалению, на этой неделе для вас не нашлось собеседника random coffee." \
                       "\nПопробуйте обратиться в сообщество и привлечь больше участников в эту игру."
            intent = INTENT_COFFEE_PUSH_ALONE
            suggests = make_standard_suggests(database=database, user_object=user_obj)
            sender(user_id=user_id, text=response, database=database, suggests=suggests,
                   reset_intent=True, intent=intent)
        return

    with_whom = 'с {}'.format(match_texts[0])
    for next_match in match_texts[1:]:
        with_whom = with_whom + ' и c {}'.format(next_match)

    response = None
    intent = None
    if first_day_condition:  # saturday
        response = 'На этой неделе вы пьёте кофе {}. {}'.format(with_whom, space.text_after_messages)
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
        user_in_pb = database.find_peoplebook_profile(
            space_name=space.key,
            username=user_obj.get('username'),
            tg_id=user_obj.get('tg_id'),
        )
        if not user_in_pb:
            response = response + '\n\nКстати, кажется, вас нет в пиплбуке, а жаль: ' \
                                  'с пиплбуком даже незнакомому собеседнику проще будет начать с вами общение.' \
                                  '\nПожалуйста, когда будет время, напишите мне "мой пиплбук" ' \
                                  'и заполните свою страничку.{}'.format(space.text_after_messages)
        suggests = make_standard_suggests(database=database, user_object=user_obj)
        sender(user_id=user_id, text=response, database=database, suggests=suggests,
               reset_intent=True, intent=intent)


def try_coffee_management(ctx: Context, database: Database):
    if not database.has_at_least_level(user_object=ctx.user_object, level=ctx.space.who_can_use_random_coffee):
        return ctx
    coffee_score = get_coffee_score(ctx.text)
    if ctx.text == TAKE_PART or coffee_score == 1:
        if ctx.user_object.get('username') is None:
            ctx.intent = 'COFFEE_NO_USERNAME'
            ctx.response = 'Чтобы участвовать в random coffee, нужно иметь имя пользователя в Телеграме.' \
                           '\nПожалуйста, создайте себе юзернейм (ТГ > настройки > изменить профиль > ' \
                           'имя пользователя) и попробуйте снова.\nВ случае ошибки напишите @{}.' \
                           '\n{}!'.format(ctx.space.owner_username, ctx.space.text_after_messages)
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
    if not database.has_at_least_level(user_object=ctx.user_object, level=ctx.space.who_can_use_random_coffee):
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
                'Спасибо, что делитесь своими впечатлениями. {}'.format(ctx.space.text_after_messages)
            ])
    return ctx
