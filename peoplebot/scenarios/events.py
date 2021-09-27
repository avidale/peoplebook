import pandas as pd
import random
import re
import time

from collections import Counter
from datetime import datetime, timedelta

from peoplebot.scenarios.suggests import make_standard_suggests
from peoplebot.scenarios.peoplebook_auth import make_pb_url
from utils.database import Database
from utils.dialogue_management import Context
from utils.events import InvitationStatuses
from utils.messaging import BaseSender
from utils.spaces import SpaceConfig
from utils import matchers

from config import BATCH_MESSAGE_TIMEOUT, DEFAULT_SPACE

DETAILED_HEAD_SIZE = 3


class EventIntents:
    INVITE = 'INVITE'
    DID_NOT_PARSE = 'DID_NOT_PARSE'
    ON_HOLD = 'ON_HOLD'
    ACCEPT = 'ACCEPT'
    REJECT = 'REJECT'
    NORMAL_REMINDER = 'NORMAL_REMINDER'
    PAYMENT_REMINDER = 'NORMAL_REMINDER'


def is_future_event(event, may_be_today=True):
    return datetime.strptime(event['date'], '%Y.%m.%d') + timedelta(days=bool(may_be_today)) > datetime.utcnow()


def render_full_event(ctx: Context, database: Database, the_event):
    response = format_event_description(the_event, user_tg_id=ctx.user_object['tg_id'], space_name=ctx.space.key)
    the_participation = database.mongo_participations.find_one(
        {'tg_id': ctx.user_object['tg_id'], 'code': the_event['code'], 'space': ctx.space.key}
    )
    if not the_participation:
        the_participation = database.mongo_participations.find_one(
            {'username': ctx.user_object['username'], 'code': the_event['code'], 'space': ctx.space.key}
        )
    is_future = is_future_event(the_event)
    if the_participation is None or the_participation.get('status') != InvitationStatuses.ACCEPT:
        response = response + '\nВы не участвуете.'
        if is_future:
            response = response + '\n /engage - участвовать'
    else:
        response = response + '\nВы участвуете.'
        if is_future:
            response = response + '\n /unengage - отказаться от участия'
    if database.is_at_least_member(user_object=ctx.user_object) and is_future:
        response = response + '\n /invite - пригласить гостя'
    if the_participation is None or the_participation.get('payment_status') != InvitationStatuses.PAYMENT_PAID:
        response = response + '\n /report_payment - сообщить об оплате мероприятия'
    if database.is_admin(user_object=ctx.user_object):
        response = response + EVENT_EDITION_COMMANDS
    return response


def make_invitation(invitation, database: Database, user_tg_id, space: SpaceConfig):
    r = 'Здравствуйте! Вы были приглашены пользователем @{} на встречу {}.\n'.format(invitation['invitor'], space.title)
    event_code = invitation.get('code', '')
    the_event = database.mongo_events.find_one({'code': event_code, 'space': space.key})
    if event_code == '' or the_event is None:
        return 'Я не смог найти встречу, напишите @{} пожалуйста.'.format(space.owner_username), 'ERROR', []
    r = r + format_event_description(the_event, user_tg_id=user_tg_id, space_name=space.key)
    r = r + '\nВы сможете участвовать в этой встрече?'
    suggests = ['Да', 'Нет', 'Пока не знаю']
    intent = EventIntents.INVITE
    database.update_user_object(
        username_or_id=invitation.get('tg_id') or invitation.get('username'),
        space_name=space.key,
        change={'$set': {'event_code': event_code}},
    )
    return r, intent, suggests


def try_invitation(ctx: Context, database: Database):
    user_tg_id = ctx.user_object.get('tg_id', '')

    # todo: check if the event is in the future
    deferred_invitation = database.mongo_participations.find_one(
        {'username': ctx.username, 'status': InvitationStatuses.NOT_SENT, 'space': ctx.space.key}
    )
    if not deferred_invitation:
        deferred_invitation = database.mongo_participations.find_one(
            {'tg_id': ctx.tg_id, 'status': InvitationStatuses.NOT_SENT, 'space': ctx.space.key}
        )

    if ctx.last_intent in {EventIntents.INVITE, EventIntents.DID_NOT_PARSE}:
        new_status = None
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'Почему-то не удалось получить код встречи, сообщите @{}'.format(ctx.space.owner_username)
        elif matchers.is_like_yes(ctx.text_normalized):
            new_status = InvitationStatuses.ACCEPT
            ctx.intent = EventIntents.ACCEPT
            ctx.response = 'Ура! Я очень рад, что вы согласились прийти!'
            the_peoplebook = database.find_peoplebook_profile(
                space_name=ctx.space.key,
                username=ctx.username,
                tg_id=ctx.user_object['tg_id']
            )
            event_url = make_pb_url('/{}/event/{}'.format(ctx.space.key, event_code), user_tg_id)
            if the_peoplebook is None:
                t = '\nЧтобы встреча прошла продуктивнее, пожалуйста, заполните свою страничку в ' \
                    + '<a href="{}">пиплбуке встречи</a>.'.format(event_url) \
                    + '\nДля этого, когда будете готовы, напишите мне "мой пиплбук"' \
                    + ' и ответьте на пару вопросов о себе.'\
                    + ctx.space.text_after_messages
            else:
                t = '\nВозможно, вы хотите обновить свою страничку в ' \
                    + '<a href="{}">пиплбуке встречи</a>.'.format(event_url) \
                    + '\nДля этого, когда будете готовы, напишите мне "мой пиплбук"' \
                    + ' и ответьте на пару вопросов о себе.' \
                    + ctx.space.text_after_messages
            ctx.response = ctx.response + t
            # todo: tell the details and remind about money
        elif matchers.is_like_no(ctx.text_normalized):
            new_status = InvitationStatuses.REJECT
            ctx.intent = EventIntents.REJECT
            ctx.response = 'Мне очень жаль, что у вас не получается. ' \
                           'Но, видимо, такова жизнь.' + ctx.space.text_after_messages
            # todo: ask why the user rejects it
        elif re.match('пока не знаю', ctx.text_normalized):
            new_status = InvitationStatuses.ON_HOLD
            ctx.intent = EventIntents.ON_HOLD
            ctx.response = 'Хорошо, я спрошу попозже ещё.'
        else:
            ctx.intent = EventIntents.DID_NOT_PARSE
            ctx.response = 'Я не понял. Ответьте, пожалуйста, на приглашение: "Да", "Нет", или "Пока не знаю".'
            ctx.suggests.extend(['Да', 'Нет', 'Пока не знаю'])
        if new_status is not None:
            database.mongo_participations.update_one(
                {'username': ctx.username, 'code': event_code, 'space': ctx.space.key},
                {'$set': {'status': new_status}}
            )
    elif deferred_invitation is not None:
        resp, intent, suggests = make_invitation(
            deferred_invitation, database=database, user_tg_id=user_tg_id, space=ctx.space,
        )
        if not deferred_invitation.get('tg_id'):
            # when inviting the user, tg_id was not known, so we insert it now
            database.mongo_participations.update_many(
                {'username': ctx.username},
                {'$set': {'tg_id': ctx.tg_id}}
            )
        ctx.response = resp
        ctx.intent = intent
        ctx.suggests.extend(suggests)
        ctx.the_update = {'$set': {'event_code': deferred_invitation.get('code')}}
    return ctx


def add_admin_invite_buttons(ctx: Context, database: Database):
    if database.is_admin(ctx.user_object):
        ctx.suggests.append('Пригласить всех членов клуба')
        ctx.suggests.append('Пригласить всех членов сообщества')
        ctx.suggests.append('Пригласить всех членов и гостей сообщества')


def try_event_usage(ctx: Context, database: Database):
    if not database.is_at_least_guest(ctx.user_object):
        return ctx
    event_code = ctx.user_object.get('event_code')
    event_user_filter = {'username': ctx.user_object.get('username'), 'code': event_code, 'space': ctx.space.key}
    if re.match('(най[тд]и|пока(жи|зать))( мои| все)? (встреч[уи]|событи[ея]|мероприяти[ея])', ctx.text_normalized):
        ctx.intent = 'EVENT_GET_LIST'
        all_events = list(database.mongo_events.find({'space': ctx.space.key}))
        # future_events = [
        #     e for e in all_events if is_future_event(e)
        # ]
        # todo: filter future events if requested so
        if database.is_at_least_member(user_object=ctx.user_object):
            available_events = all_events
        else:
            available_events = [
                c['the_event'][0] for c in database.mongo_participations.aggregate([
                    {
                        '$match': {'username': ctx.username}
                    }, {
                        '$lookup': {
                            'from': 'events',
                            'localField': 'code',
                            'foreignField': 'code',
                            'as': 'the_event'
                        }
                    }
                ])
            ]
        available_events.sort(key=lambda evt: evt['date'], reverse=True)
        first_events = available_events[:DETAILED_HEAD_SIZE]
        last_events = available_events[DETAILED_HEAD_SIZE:]
        if len(available_events) > 0:
            ctx.response = 'Найдены события:\n'
            for e in first_events:
                ctx.response = ctx.response + '/{}: "{}", {}\n'.format(e['code'], e['title'], e['date'])
                invitation = database.mongo_participations.find_one(
                    {'username': ctx.username, 'code': e['code'], 'space': ctx.space.key}
                )
                if invitation is None or 'status' not in invitation:
                    status = 'Вы не участвуете'
                else:
                    status = InvitationStatuses.translate_second_person(invitation['status'])
                ctx.response = ctx.response + '{}\n\n'.format(status)
            if len(last_events) > 0:
                last_events_links = ', '.join(['/{}'.format(e['code']) for e in last_events])
                ctx.response = ctx.response + 'Более старые встречи: {}\n\n'.format(last_events_links)
            ctx.response = ctx.response + 'Кликните по нужной ссылке, чтобы выбрать встречу.'
        elif len(all_events) > 0:
            ctx.response = 'Доступных вам событий не найдено.'
        else:
            ctx.response = 'Событий не найдено'
    elif ctx.last_intent == 'EVENT_GET_LIST':
        event_code = ctx.text.lstrip('/')
        the_event = database.mongo_events.find_one({'code': event_code, 'space': ctx.space.key})
        if the_event is not None:
            ctx.intent = 'EVENT_CHOOSE_SUCCESS'
            ctx.the_update = {'$set': {'event_code': event_code}}
            ctx.response = render_full_event(ctx, database, the_event)
            add_admin_invite_buttons(ctx=ctx, database=database)
    elif event_code is not None and (
            ctx.text == '/engage' or re.match('^(участвовать|принять участие)( в этой встрече)?$', ctx.text_normalized)
    ):
        ctx.intent = 'EVENT_ENGAGE'
        database.mongo_participations.update_one(
            event_user_filter,
            {'$set': {'status': InvitationStatuses.ACCEPT}}, upsert=True
        )
        ctx.response = 'Теперь вы участвуете в мероприятии {}!'.format(event_code)
    elif event_code is not None and (
            ctx.text == '/unengage' or re.match('^(не участвовать|покинуть встречу)$', ctx.text_normalized)
    ):
        ctx.intent = 'EVENT_UNENGAGE'
        database.mongo_participations.update_one(
            event_user_filter,
            {'$set': {'status': InvitationStatuses.REJECT}}, upsert=True
        )
        ctx.response = 'Теперь вы не участвуете в мероприятии {}!'.format(event_code)
    elif event_code is not None and (
            ctx.text == '/report_payment' or re.match('^сообщить об оплате$', ctx.text_normalized)
    ):
        participation = database.mongo_participations.find_one(event_user_filter)
        if participation is None or participation.get('status') != InvitationStatuses.ACCEPT:
            ctx.intent = 'EVENT_REPORT_PAYMENT_NOT_ACCEPTED'
            ctx.response = 'Кажется, вы ещё не подтвердили участие в событии {}.' \
                           '\nНадо сначала подтвердить участие, а потом сообщить об оплате'.format(event_code)
        elif participation.get('payment_status') == InvitationStatuses.PAYMENT_PAID:
            ctx.intent = 'EVENT_REPORT_PAYMENT_ALREADY_PAID'
            ctx.response = 'Кажется, вы уже оплатили своё участие в событии {}. ' \
                           'Больше платить не нужно! :)'.format(event_code)
        else:
            ctx.intent = 'EVENT_REPORT_PAYMENT_CONFIRM'
            ctx.expected_intent = 'EVENT_REPORT_PAYMENT_DETAILS'
            ctx.response = 'Спасибо за своевременную оплату участия! ' \
                           '\nПожалуйста, кратко опишите в следующем сообщении свой способ оплаты ' \
                           '(на какую карту; сколько; кто оплатил, если не вы):'
            database.mongo_participations.update_one(
                event_user_filter,
                {'$set': {'payment_status': InvitationStatuses.PAYMENT_PAID}},
                upsert=True
            )
    elif ctx.last_expected_intent == 'EVENT_REPORT_PAYMENT_DETAILS':
        ctx.response = 'Спасибо за предоставленную информацию.' + ctx.space.text_after_messages
        ctx.intent = 'EVENT_REPORT_PAYMENT_DETAILS'
        database.mongo_participations.update_one(
            event_user_filter,
            {'$set': {'payment_details': ctx.text}},
            upsert=True
        )
        # todo: add a button "return to the event"
    elif ctx.text == '/invite':
        if event_code is None:
            ctx.intent = 'EVENT_INVITE_WITHOUT_EVENT'
            ctx.response = 'Чтобы пригласить гостя, сначала нужно выбрать встречу'
        elif database.is_at_least_member(user_object=ctx.user_object):
            the_event = database.mongo_events.find_one({'code': event_code, 'space': ctx.space.key})
            if the_event is None:
                ctx.intent = 'EVENT_INVITE_NOT_FOUND'
                ctx.response = 'Извините, события "{}" не найдено. Выберите другое.'.format(event_code)
            elif not is_future_event(the_event):
                ctx.intent = 'EVENT_INVITE_IN_THE_PAST'
                ctx.response = 'Событие "{}" уже состоялось, вы не можете приглашать гостей.'.format(event_code)
            else:
                ctx.intent = 'EVENT_INVITE'
                ctx.expected_intent = 'EVENT_INVITE_LOGIN'
                ctx.response = 'Хорошо! Сейчас пригласим гостя на встречу "{}".'.format(event_code)
                ctx.response = ctx.response + '\nВведите Telegram логин человека, которого хотите пригласить.'
        else:
            ctx.response = 'Вы не являетесь членом клуба, и поэтому не можете приглашать гостей. Сорян.'
            ctx.intent = 'EVENT_INVITE_UNAUTHORIZED'
    elif ctx.last_expected_intent == 'EVENT_INVITE_LOGIN':
        ctx.intent = 'EVENT_INVITE_LOGIN'
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'Почему-то не удалось получить код события, сообщите @{}'.format(ctx.space.owner_username)

        response_lines = []
        for the_login in re.split('[\\s,;]+', ctx.text.strip()):
            the_login = the_login.strip().strip('@').lower()
            if not the_login:
                continue

            if not matchers.is_like_telegram_login(the_login):
                f = 'Текст "{}" не похож на логин в телеграме. Если хотите попробовать снова, нажмите /invite опять.'
                response_lines.append(f.format(the_login))
            else:
                user_account = database.mongo_users.find_one({'username': the_login, 'space': ctx.space.key})

                status = add_invitation_to_a_user(
                    database=database,
                    tg_id=(user_account or {}).get('tg_id'),
                    username=the_login,
                    event_code=event_code,
                    space=ctx.space,
                    invitor=ctx.username,
                    sender=ctx.sender,
                )

                if status == 'приглашение уже было сделано':
                    response_lines.append('Пользователь @{} уже получал приглашение на эту встречу!'.format(the_login))
                else:
                    r = 'Юзер @{} был добавлен в список участников встречи!'.format(the_login)
                    if status == 'не в боте':
                        r = r + '\nПередайте ему/ей ссылку на меня (@{}), '.format(ctx.space.bot_username) + \
                            'чтобы подтвердить участие и заполнить пиплбук (увы, бот не может писать первым).'
                    elif status == 'не получилось':
                        r = r + '\nНе получилось отправить ему/ей сообщение с приглашением. ' \
                                'Пожалуйста, сделайте это самостоятельно и попросите написать мне. Спасибо!'
                    response_lines.append(r)
        if len(response_lines) == 0:
            ctx.response = 'Не удалось найти логинов в тексте, который вы отправили. ' \
                           'Пожалуйста, попробуйте ещё раз с другим текстом.'
        else:
            ctx.response = '\n\n'.join(response_lines)

    return ctx


def add_invitation_to_a_user(
        username, tg_id, event_code,
        database: Database,
        space: SpaceConfig,
        sender: BaseSender,
        invitor: str,
) -> str:
    """ Add an invitation to mongo_participations and try sending the invitation
    resulting status is: one of
    - 'не удалось идентифицировать пользователя' (нет логина или айди)
    - 'приглашение уже было сделано'
    - 'нет в боте' (приглашение создано, но не отправлено, т.к. юзера пока нет в боте)
    - 'не получилось' (приглашение создано, но не отправлено по какой-то другой причине)
    - 'успех' (sent_invitation_to_user called successfully)
    """
    if not username and not tg_id:
        return 'не удалось идентифицировать пользователя'

    user_account = None
    if username:
        user_account = database.mongo_users.find_one({'username': username, 'space': space.key})
    if tg_id and not user_account:
        user_account = database.mongo_users.find_one({'tg_id': tg_id, 'space': space.key})
    if user_account and user_account.get('tg_id') and not tg_id:
        tg_id = user_account.get('tg_id')

    existing_membership = database.find_membership(username=username, tg_id=tg_id, space_name=space.key)
    if existing_membership is None:
        # maybe it is not right to make user a guest just on sending the invitation
        o = {'username': username, 'space': space.key, 'tg_id': tg_id, 'is_guest': True}
        if username:
            o['username'] = username
        if tg_id:
            o['tg_id'] = tg_id
        database.mongo_membership.insert_one(o)

    the_invitation = database.find_invitation(
        space_name=space.key, username=username, tg_id=tg_id, event_code=event_code
    )
    if the_invitation is not None:
        status = 'приглашение уже было сделано'
    else:
        key = {'code': event_code, 'space': space.key}
        if username:
            key['username'] = username
        if tg_id:
            key['tg_id'] = tg_id
        database.mongo_participations.update_one(
            key,
            {'$set': {'status': InvitationStatuses.NOT_SENT, 'invitor': invitor, 'tg_id': tg_id}},
            upsert=True
        )
        never_used_this_bot = user_account is None
        if never_used_this_bot:
            status = 'нет в боте'
        else:
            success = sent_invitation_to_user(
                username=username, tg_id=tg_id,
                event_code=event_code, database=database, sender=sender,
                space=space,
            )
            status = 'успех' if success else 'не получилось'
    return status


def sent_invitation_to_user(
        username, tg_id, event_code, database: Database, sender: BaseSender, space: SpaceConfig
) -> bool:
    """ Try to send an existing invitation to a user, and return status """
    invitation = database.find_invitation(space_name=space.key, username=username, tg_id=tg_id, event_code=event_code)
    if invitation is None:
        return False

    user_account = database.find_user(space_name=space.key, username=username, tg_id=tg_id)
    if user_account is None:
        return False

    if user_account.get('deactivated'):
        print('user {} is deactivated, skipping it'.format(user_account))
        return False
    text, intent, suggests = make_invitation(
        invitation=invitation, database=database, user_tg_id=user_account['tg_id'], space=space
    )
    if sender(text=text, database=database, suggests=suggests, user_id=user_account['tg_id']):
        database.update_user_object(
            username_or_id=username,
            space_name=space.key,
            change={'$set': {'last_intent': intent, 'event_code': event_code, 'last_expected_intent': None}},
        )
        if invitation.get('status') == InvitationStatuses.NOT_SENT:
            database.mongo_participations.update_one(
                {'_id': invitation.get('_id')},
                {'$set': {'status': InvitationStatuses.NOT_ANSWERED}}
            )
        return True
    else:
        return False


class EventCreationIntents:
    INIT = 'EVENT_CREATE_INIT'
    CANCEL = 'EVENT_CREATE_CANCEL'
    SET_TITLE = 'EVENT_CREATE_SET_TITLE'
    SET_CODE = 'EVENT_CREATE_SET_CODE'
    SET_DATE = 'EVENT_CREATE_SET_DATE'


def try_parse_date(text):
    try:
        return datetime.strptime(text, '%Y.%m.%d')
    except ValueError:
        return None
    except TypeError:
        return None


def try_event_creation(ctx: Context, database: Database):
    if not database.is_admin(ctx.user_object):
        return ctx
    event_code = ctx.user_object.get('event_code')
    if re.match('созда(ть|й) встречу', ctx.text_normalized):
        ctx.intent = EventCreationIntents.INIT
        ctx.expected_intent = EventCreationIntents.SET_TITLE
        ctx.response = 'Придумайте название встречи (например, Встреча {} 27 апреля):'.format(ctx.space.title)
        ctx.the_update = {'$set': {'event_to_create': {'space': ctx.space.key}}}
        ctx.suggests.append('Отменить создание встречи')
    elif re.match('отменить создание встречи', ctx.text_normalized):
        ctx.intent = EventCreationIntents.CANCEL
        ctx.response = 'Хорошо, пока не будем создавать встречу'
    elif ctx.last_expected_intent == EventCreationIntents.SET_TITLE:
        ctx.intent = EventCreationIntents.SET_TITLE
        if len(ctx.text_normalized) < 3:
            ctx.expected_intent = EventCreationIntents.SET_TITLE
            ctx.response = 'Это название слишком странное. Пожалуйста, попробуйте другое.'
        elif database.mongo_events.find_one({'title': ctx.text, 'space': ctx.space.key}) is not None:
            ctx.expected_intent = EventCreationIntents.SET_TITLE
            ctx.response = 'Такое название уже существует. Пожалуйста, попробуйте другое.'
        else:
            event_to_create = ctx.user_object.get('event_to_create', {})
            event_to_create['title'] = ctx.text
            ctx.the_update = {'$set': {'event_to_create': event_to_create}}
            ctx.response = (
                'Хорошо, назовём встречу "{}".'.format(ctx.text) +
                '\nТеперь придумайте код встречи из латинских букв и цифр ' +
                '(например, april2019):'
            )
            ctx.expected_intent = EventCreationIntents.SET_CODE
        ctx.suggests.append('Отменить создание встречи')
    elif ctx.last_expected_intent == EventCreationIntents.SET_CODE:
        ctx.intent = EventCreationIntents.SET_CODE
        if len(ctx.text) < 3:
            ctx.expected_intent = EventCreationIntents.SET_CODE
            ctx.response = 'Этот код слишком короткий. Пожалуйста, попробуйте другой.'
        elif not re.match('^[a-z0-9_]+$', ctx.text):
            ctx.expected_intent = EventCreationIntents.SET_CODE
            ctx.response = 'Код должен состоять из цифр и латинских букв в нижнем регистре. ' \
                           'Пожалуйста, попробуйте ещё раз.'
        elif database.mongo_events.find_one({'code': ctx.text, 'space': ctx.space.key}) is not None:
            ctx.expected_intent = EventCreationIntents.SET_CODE
            ctx.response = 'Событие с таким кодом уже есть. Пожалуйста, придумайте другой код.'
        else:
            event_to_create = ctx.user_object.get('event_to_create', {})
            event_to_create['code'] = ctx.text
            ctx.the_update = {'$set': {'event_to_create': event_to_create}}
            ctx.response = (
                    'Хорошо, код встречи будет "{}". '.format(ctx.text) +
                    '\nТеперь введите дату встречи в формате ГГГГ.ММ.ДД:'
            )
            ctx.expected_intent = EventCreationIntents.SET_DATE
        ctx.suggests.append('Отменить создание встречи')
    elif ctx.last_expected_intent == EventCreationIntents.SET_DATE:
        ctx.intent = EventCreationIntents.SET_DATE
        if not re.match(r'^20\d\d\.[01]\d\.[0123]\d$', ctx.text):
            ctx.expected_intent = EventCreationIntents.SET_DATE
            ctx.response = 'Дата должна быть в формате ГГГГ.ММ.ДД (типа 2020.03.05). Попробуйте ещё раз!'
            ctx.suggests.append('Отменить создание встречи')
        elif try_parse_date(ctx.text) is None:
            ctx.expected_intent = EventCreationIntents.SET_DATE
            ctx.response = 'Не получилось разобрать такую дату. Попробуйте, пожалуйста, ещё раз.'
            ctx.suggests.append('Отменить создание встречи')
        elif try_parse_date(ctx.text) + timedelta(days=1) < datetime.utcnow():
            ctx.expected_intent = EventCreationIntents.SET_DATE
            ctx.response = 'Кажется, эта дата уже в прошлом. Попробуйте, пожалуйста, ввести дату из будущего.'
            ctx.suggests.append('Отменить создание встречи')
        else:
            event_to_create = ctx.user_object.get('event_to_create', {})
            event_to_create['date'] = ctx.text
            database.mongo_events.insert_one(event_to_create)
            ctx.the_update = {'$set': {'event_code': event_to_create['code']}}
            ctx.response = 'Хорошо, дата встречи будет "{}". '.format(ctx.text) + '\nВстреча успешно создана!'
            add_admin_invite_buttons(ctx=ctx, database=database)
    elif event_code is not None:  # this event is context-independent, triggers at any time just by text
        if re.match('пригласить (всех|весь).*', ctx.text_normalized) \
                or ctx.text in {'/invite_club', '/invite_community', '/invite_community_and_guests'}:
            # todo: deduplicate this as well
            the_event = database.mongo_events.find_one({'code': event_code, 'space': ctx.space.key})
            community = 'сообществ' in ctx.text_normalized or 'community' in ctx.text
            large = 'членов и гостей сообщества' in ctx.text_normalized or 'community_and_guests' in ctx.text
            if the_event is None:
                ctx.intent = 'EVENT_INVITE_NOT_FOUND'
                ctx.response = 'Извините, события "{}" не найдено. Выберите другое.'.format(event_code)
            elif not is_future_event(the_event):
                ctx.intent = 'EVENT_INVITE_IN_THE_PAST'
                ctx.response = 'Событие "{}" уже состоялось, вы не можете приглашать гостей.'.format(event_code)
            else:
                if large:
                    ctx.intent = 'INVITE_EVERYONE_GUESTS'
                    who = 'и гостей Сообщества'
                elif community:
                    ctx.intent = 'INVITE_EVERYONE_COMMUNITY'
                    who = 'Сообщества'
                else:
                    ctx.intent = 'INVITE_EVERYONE'
                    who = 'Клуба'
                ctx.response = f'Действительно пригласить всех членов {who} на встречу "{event_code}"?'
                ctx.suggests.extend(['Да', 'Нет'])
        elif ctx.last_intent in {'INVITE_EVERYONE', 'INVITE_EVERYONE_COMMUNITY', 'INVITE_EVERYONE_GUESTS'} \
                and matchers.is_like_no(ctx.text_normalized):
            ctx.intent = 'INVITE_EVERYONE_NOT_CONFIRM'
            ctx.response = 'Ладно.'
        elif ctx.last_intent in {'INVITE_EVERYONE', 'INVITE_EVERYONE_COMMUNITY', 'INVITE_EVERYONE_GUESTS'} \
                and matchers.is_like_yes(ctx.text_normalized):
            ctx.intent = 'INVITE_EVERYONE_CONFIRM'
            community = (ctx.last_intent == 'INVITE_EVERYONE_COMMUNITY')
            large = (ctx.last_intent == 'INVITE_EVERYONE_GUESTS')
            r = 'Приглашаю всех членов {}...\n'.format('Сообщества' if community else 'Клуба')
            for member in database.mongo_membership.find({'space': ctx.space.key}):

                if large:
                    if not member.get('is_member') and not member.get('is_friend') and not member.get('is_guest'):
                        continue
                elif community:
                    if not member.get('is_member') and not member.get('is_friend'):
                        continue
                else:
                    if not member.get('is_member'):
                        continue
                status = add_invitation_to_a_user(
                    database=database,
                    tg_id=member.get('tg_id'),
                    username=member.get('username'),
                    event_code=event_code,
                    space=ctx.space,
                    invitor=ctx.username,
                    sender=ctx.sender,
                )
                r = r + '\n  @{}: {}'.format(member.get('username') or member.get('tg_id'), status)
            ctx.response = r
    return ctx


class EventField:
    def __init__(self, code: str, name: str, validator):
        self.code = code
        self.command = '/set_e_' + code
        self.intent = 'EVENT_EDIT_' + code.upper()
        self.name = name
        self.name_accs = matchers.inflect_first_word(self.name, 'accs')
        self.validator = validator

    def validate(self, text):
        if self.validator is None:
            return True
        elif isinstance(self.validator, str):
            return bool(re.match(self.validator, text))
        else:
            return bool(self.validator(text))


EVENT_FIELDS = [
    EventField(*r) for r in [
        ['title', 'название', '.{3,}'],
        ['date', 'дата', lambda text: (try_parse_date(text) is not None)],
        ['time', 'время', '.{3,}'],
        ['place', 'адрес', '.{3,}'],
        ['program', 'программа', '.{3,}'],
        ['cost', 'размер взноса', '.{3,}'],
        ['chat', 'чат встречи', '.{3,}'],
        ['materials', 'ссылка на архив материалов', '.{3,}'],
    ]
]

EVENT_FIELD_BY_COMMAND = {e.command: e for e in EVENT_FIELDS}
EVENT_FIELD_BY_INTENT = {e.intent: e for e in EVENT_FIELDS}

EVENT_EDITION_COMMANDS = '\n'.join(
    [""] +
    ['{} - задать {}'.format(e.command, e.name_accs) for e in EVENT_FIELDS] +
    [
        "/remove_event - удалить событие и отменить все приглашения",
        "/invite_club - пригласить всех членов КЛУБА",
        "/invite_community - пригласить всех членов СООБЩЕСТВА",
        "/invite_community_and_guests - пригласить всех членов СООБЩЕСТВА и его прежних ГОСТЕЙ",
        "/invitation_statuses - посмотреть статусы приглашений",
        "/invitation_statuses_excel - выгрузить статусы приглашений",
        "/report_others_payment - сообщить о статусе оплаты участника",
        "/broadcast - разослать сообщение всем участникам встречи",
        "/random_wine - соединить участников встречи в пары и разослать сообщения",
    ]
)


def format_event_description(event_dict, user_tg_id, space_name):
    result = 'Мероприятие:'
    for field in EVENT_FIELDS:
        if event_dict.get(field.code, '') != '':
            result = result + '\n\t<b>{}</b>: \t{}'.format(field.name, event_dict.get(field.code))
    result = result + '\n\t<b>пиплбук встречи</b>: <a href="{}">ссылка</a>\n'.format(
        make_pb_url('/{}/event/{}'.format(space_name, event_dict.get('code')), user_tg_id)
    )
    return result


def try_event_edition(ctx: Context, database: Database):
    if not database.is_admin(ctx.user_object):
        return ctx
    event_code = ctx.user_object.get('event_code')
    the_event = database.mongo_events.find_one({'code': event_code, 'space': ctx.space.key})
    if event_code is None:
        return ctx
    if ctx.text in EVENT_FIELD_BY_COMMAND:
        field = EVENT_FIELD_BY_COMMAND[ctx.text]
        ctx.intent = field.intent
        ctx.expected_intent = field.intent
        ctx.response = 'Пожалуйста, введите {} мероприятия.'.format(field.name_accs)
        ctx.suggests.append('Отменить редактирование события')
    elif ctx.text == 'Отменить редактирование события':
        ctx.intent = 'EVENT_EDIT_CANCEL'
        ctx.response = 'Ладно\n\n' + render_full_event(ctx, database, the_event)
    elif ctx.last_expected_intent in EVENT_FIELD_BY_INTENT:
        field = EVENT_FIELD_BY_INTENT[ctx.last_expected_intent]
        ctx.intent = ctx.last_expected_intent
        if field.validate(ctx.text):
            database.mongo_events.update_one(
                {'code': event_code, 'space': ctx.space.key},
                {'$set': {field.code: ctx.text}}
            )
            the_event = database.mongo_events.find_one({'code': event_code, 'space': ctx.space.key})
            ctx.response = 'Вы успешно изменили {}!\n\n'.format(field.name_accs)
            ctx.response = ctx.response + render_full_event(ctx, database, the_event)
        else:
            ctx.expected_intent = field.intent
            ctx.response = 'Кажется, формат не подходит. Пожалуйста, введите {} ещё раз.'.format(field.name_accs)
            ctx.suggests.append('Отменить редактирование')
    elif ctx.text == '/invitation_statuses':
        ctx.intent = 'EVENT_GET_INVITATION_STATUSES'
        event_members = list(database.mongo_participations.find({'code': event_code, 'space': ctx.space.key}))
        if len(event_members) == 0:
            ctx.response = 'Пока в этой встрече совсем нет участников.'
            if ctx.space.key == DEFAULT_SPACE:
                ctx.response = ctx.response + '\nЕсли вы есть, будьте первыми!!!'
        else:
            statuses = [InvitationStatuses.translate(em['status'], em.get('payment_status')) for em in event_members]
            # todo: use uid when checking for members
            descriptions = '\n'.join([
                '@{} - {}'.format(em['username'], st) +
                ('' if 'invitor' not in em or database.is_at_least_member({'username': em['username']})
                 else ' (гость @{})'.format(em['invitor']))
                for em, st in zip(event_members, statuses)
            ])
            cntr = Counter(statuses)
            summary = '\n'.join(['{} - {}'.format(k, cntr[k]) for k in sorted(cntr.keys())])
            ctx.response = 'Вот какие статусы участников встречи {}:\n{}\n\n{}'.format(
                event_code, summary, descriptions
            )
        ctx.response = ctx.response
    elif ctx.text == '/invitation_statuses_excel':
        ctx.intent = 'EVENT_GET_INVITATION_STATUSES_EXCEL'
        ctx.response = 'Формирую выгрузку...'
        ctx.file_to_send = event_to_file(event_code, database=database, space=ctx.space)
    elif ctx.text == '/broadcast':
        ctx.intent = 'EVENT_BROADCAST'
        ctx.response = 'Вы точно хотите отправить сообщение всем людям, подтвердившим участие во встрече {}?' \
                       '\nПожалуйста, ответьте "Да" или "Нет".'.format(event_code)
        ctx.suggests.insert(0, 'Нет')
        ctx.suggests.insert(0, 'Да')
        ctx.expected_intent = 'EVENT_BROADCAST_CONFIRM'
    elif ctx.last_expected_intent == 'EVENT_BROADCAST_CONFIRM':
        if matchers.is_like_yes(ctx.text_normalized):
            ctx.intent = 'EVENT_BROADCAST_CONFIRM_YES'
            ctx.response = 'Ладно! Введите сообщение, которое получат все люди, подтвердившие участие во встрече.'
            ctx.expected_intent = 'EVENT_BROADCAST_MESSAGE'
        elif matchers.is_like_no(ctx.text_normalized):
            ctx.intent = 'EVENT_BROADCAST_CONFIRM_NO'
            ctx.response = 'Ну и правильно! Нечего людей зря беспокоить!'
    elif ctx.last_expected_intent == 'EVENT_BROADCAST_MESSAGE':
        ctx.intent = 'EVENT_BROADCAST_MESSAGE'
        broadcast_warning = 'Окей, я начинаю рассылку вашего текста. Это может занять пару минут, придётся подождать.' \
                            '\nПрошу вас, не трогайте ничего и молчите, пока я не закончу.' \
                            '\nКогда я завершу рассылку, я отпишусь.'
        database.update_user_object(
            username_or_id=ctx.user_object.get('username'),
            space_name=ctx.space.key,
            change={'$set': {'last_expected_intent': None}},
        )  # without this update, the next message from this user may get broadcasted as well
        ctx.sender(text=broadcast_warning, database=database, suggests=[], user_id=ctx.user_object['tg_id'])
        participants = list(database.mongo_participations.find(
            {'code': event_code, 'status': InvitationStatuses.ACCEPT, 'space': ctx.space.key}
        ))
        not_sent = []
        for p in participants:
            receiver_username = p['username']
            text = ctx.text
            intent = 'GET_BROADCASTED_MESSAGE'
            suggests = ['Ясно', 'Понятно', 'Ничоси', 'Кто ты ваще?']
            user_account = database.mongo_users.find_one({'username': receiver_username, 'space': ctx.space.key})
            if user_account is None:
                not_sent.append(receiver_username)
            else:
                if ctx.sender(text=text, database=database, suggests=suggests, user_id=user_account['tg_id'],
                              reset_intent=True, intent=intent):
                    pass
                else:
                    not_sent.append(receiver_username)
        n = len(participants)
        if len(not_sent) == 0:
            ctx.response = 'Окей. Я отправил это сообщение всем {} подтвержденным участникам встречи. ' \
                           'Вы сами напросились!'.format(n)
        else:
            ctx.response = 'Ладно. Я попробовал послать это всем {} подтвержденным участникам, ' \
                           'но в итоге {} не получили сообщение. Им придется написать отдельно'.format(
                            n, ', '.join(['@' + u for u in not_sent])
                            )
    elif ctx.text == '/random_wine':
        ctx.intent = 'EVENT_RANDOMWINE'
        participants = list(database.mongo_participations.find(
            {'code': event_code, 'status': InvitationStatuses.ACCEPT, 'space': ctx.space.key}
        ))
        match_warning = 'Окей, начинаю собирать {} участников в пары, ждите'.format(len(participants))
        ctx.sender(text=match_warning, database=database, suggests=[], user_id=ctx.user_object['tg_id'])
        # create the pairs
        random.shuffle(participants)
        pairs = []
        for i in range(0, len(participants), 2):
            pairs.append((participants[i], participants[i-1]))
            pairs.append((participants[i-1], participants[i]))
        if len(participants) % 2 == 1 and len(participants) > 1:
            # it's a triple!
            pairs.append((participants[0], participants[-1]))
            pairs.append((participants[-1], participants[0]))
            pairs.append((participants[1], participants[-1]))
            pairs.append((participants[-1], participants[1]))
        # send everything
        not_sent = []
        for one, another in pairs:
            receiver_username = one['username']
            usr = database.mongo_users.find_one({'username': receiver_username, 'space': ctx.space.key})

            text = 'Привет! Вы участвуете в игре (not) Random talk\n' \
                   'Ваша случайная пара на этот раунд - @{}\n' \
                   'Темы для разговора <a href="{}">смотреть</a>\n' \
                   'Пиплбук: <a href="{}">смотреть</a>\n' \
                   'У вас есть 5 минут на разговор :)\n' \
                   'Приятного общения!\n' \
                   '\n' \
                   'P.S. Если вам пришло два сообщения про пары сразу - вы словили редкую удачу, ' \
                   'и вам предстоит собраться сразу в тройку (:'.format(
                    another['username'],
                    make_pb_url('/{}/person/{}'.format(ctx.space.key, another['username']), user_tg_id=usr['tg_id']),
                    make_pb_url(
                        '/{}/similarity/{}/{}'.format(ctx.space.key, one['username'], another['username']),
                        user_tg_id=usr['tg_id']
                    ),
                    )
            intent = 'GET_RANDOMWINE_MESSAGE'
            suggests = ['Ясно', 'Спасибо']
            if usr is None:
                not_sent.append(receiver_username)
            else:
                if ctx.sender(text=text, database=database, suggests=suggests, user_id=usr['tg_id'],
                              reset_intent=True, intent=intent):
                    pass
                else:
                    not_sent.append(receiver_username)
        # report
        n = len(participants)
        if len(not_sent) == 0:
            ctx.response = 'Окей. Я позвал на randm wine всех {} подтвержденных участников встречи. ' \
                           'Вы сами напросились!'.format(n)
        else:
            ctx.response = 'Ладно. Я попробовал заматчить всех {} подтвержденных участников, ' \
                           'но в итоге {} не получили сообщение. Им придется написать отдельно'.format(
                                n, ', '.join(['@' + u for u in not_sent])
                            )
    elif ctx.text == '/remove_event':
        ctx.intent = 'EVENT_REMOVE'
        ctx.expected_intent = 'EVENT_REMOVE_CONFIRM'
        ctx.response = 'Вы уверены, что хотите удалить событие "{}"? Это безвозвратно!'.format(the_event['title'])
        ctx.suggests.extend(['Да', 'Нет'])
    elif ctx.last_expected_intent == 'EVENT_REMOVE_CONFIRM':
        if matchers.is_like_yes(ctx.text_normalized):
            database.mongo_events.delete_one({'code': event_code})
            database.mongo_participations.delete_many({'code': event_code})
            ctx.the_update = {'$unset': {'event_code': ""}}
            ctx.intent = 'EVENT_REMOVE_CONFIRM'
            ctx.response = 'Хорошо. Событие "{}" было удалено.'.format(the_event['title'])
        elif matchers.is_like_no(ctx.text_normalized):
            ctx.intent = 'EVENT_REMOVE_NOT_CONFIRM'
            ctx.response = 'Ладно, не буду удалять это событие.'
    elif ctx.text == '/report_others_payment':
        ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_INIT'
        ctx.expected_intent = 'EVENT_OTHER_PAYMENT_STATUS_USERNAME'
        ctx.response = 'Введите логин участника, оплатившего встречу, о котором вы хотите сделать запись:'
        ctx.suggests.append('Отмена')
    elif ctx.last_expected_intent == 'EVENT_OTHER_PAYMENT_STATUS_USERNAME':
        if ctx.text_normalized == 'отмена':
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_CANCELED'
            ctx.response = 'Окей, не будем делать запись об оплате\n' + render_full_event(ctx, database, the_event)
        else:
            extracted_username = matchers.normalize_username(ctx.text)
            participation = database.find_invitation(
                space_name=ctx.space.key, event_code=event_code, username=extracted_username, tg_id=None
            )
            if participation is None:
                ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_USER_NOT_FOUND'
                ctx.response = 'Пользователь @{} не найден либо не приглашен на событие /{}'.format(
                    extracted_username, event_code
                )
            elif participation.get('status') != InvitationStatuses.ACCEPT:
                ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_USER_NOT_ACCEPTED'
                ctx.response = 'Пользователь @{} не участвует в событии /{}'.format(
                    extracted_username, event_code
                )
            else:
                ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_USER_FOUND'
                ctx.expected_intent = 'EVENT_OTHER_PAYMENT_STATUS_ASK_STATUS'
                ctx.response = 'Пользователь @{} найден и участвует в событии /{}!' \
                               '\nОплатил(а) ли он(а) участие? ' \
                               '\nОтветьте "Да" или "Нет":'.format(extracted_username, event_code)
                ctx.suggests.extend(['Да', 'Нет', 'Отмена'])
                ctx.the_update = {'$set': {'target_username': extracted_username}}
    elif ctx.last_expected_intent == 'EVENT_OTHER_PAYMENT_STATUS_ASK_STATUS':
        target_username = ctx.user_object.get('target_username')
        if target_username is None:
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_USERNAME_ERROR'
            ctx.response = 'Я забыл, о ком мы говорим, простите.\n\n' + render_full_event(ctx, database, the_event)
        if ctx.text_normalized == 'да':
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_SET_YES'
            ctx.response = 'Отлично, записали, что @{} оплатил(а) встречу. ' \
                           'Пожалуйста, следующим сообщением опишите способ оплаты: ' \
                           'сумма, карта, и т.п.'.format(target_username)
            ctx.expected_intent = 'EVENT_OTHER_PAYMENT_STATUS_SET_INFO'
            database.update_participation(
                space_name=ctx.space.key, username=target_username, event_code=event_code,
                the_update={'payment_status': InvitationStatuses.PAYMENT_PAID},
                tg_id=None,  # it will be recovered automatically
            )
        elif ctx.text_normalized == 'нет':
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_SET_NO'
            ctx.response = 'Отлично, записали, что @{} не оплатил(а) встречу.\n'.format(target_username) \
                           + render_full_event(ctx, database, the_event)
            database.update_participation(
                space_name=ctx.space.key, username=target_username, event_code=event_code,
                the_update={'payment_status': InvitationStatuses.PAYMENT_NOT_PAID},
                tg_id=None,  # it will be recovered automatically
            )
        elif ctx.text_normalized == 'отмена':
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_CANCEL'
            ctx.response = 'Хорошо, забьём.\n' + render_full_event(ctx, database, the_event)
        else:
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_REASK'
            ctx.expected_intent = 'EVENT_OTHER_PAYMENT_STATUS_ASK_STATUS'
            ctx.response = 'Пожалуйста, ответьте "Да", "Нет" или "Отмена".'
    elif ctx.last_expected_intent == 'EVENT_OTHER_PAYMENT_STATUS_SET_INFO':
        target_username = ctx.user_object.get('target_username')
        if target_username is None:
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_USERNAME_ERROR'
            ctx.response = 'Я забыл, о ком мы говорим, простите.\n\n' + render_full_event(ctx, database, the_event)
        else:
            ctx.intent = 'EVENT_OTHER_PAYMENT_STATUS_SET_INFO'
            ctx.response = 'Хорошо, запомню эту информацию. Спасибо!'
            database.update_participation(
                space_name=ctx.space.key, username=target_username, event_code=event_code,
                the_update={'payment_details': ctx.text},
                tg_id=None,  # it will be recovered automatically
            )
    return ctx


def daily_event_management(database: Database, sender: BaseSender, space: SpaceConfig):
    users = list(database.mongo_users.find({'space': space.key}))
    username2user = {
        u['username']: u
        for u in users
        if u.get('username') is not None
    }
    id2user = {
        u['tg_id']: u
        for u in users
        if u.get('tg_id') is not None
    }
    # find all the future events
    future_events = []
    today_events = []
    past_events = []
    yesterday_events = []
    for e in database.mongo_events.find({'space': space.key}):
        days_to = (datetime.strptime(e['date'], '%Y.%m.%d') - datetime.utcnow()) / timedelta(days=1)
        if days_to >= 0:
            e['days_to'] = int(days_to)
            future_events.append(e)
        elif -1 <= days_to < 0:
            today_events.append(e)
        elif days_to < -1:
            past_events.append(e)
        if -2 < days_to < -1:
            yesterday_events.append(e)
    # find all open invitations for the future events
    for event in future_events:
        hold_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.ON_HOLD, 'space': space.key}
        )
        not_sent_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.NOT_SENT, 'space': space.key}
        )
        not_answered_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.NOT_ANSWERED, 'space': space.key}
        )
        sure_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.ACCEPT, 'space': space.key}
        )
        open_invitations = [
            inv for inv in (list(hold_invitations) + list(not_sent_invitations) + list(not_answered_invitations))
            if inv.get('username') is not None and inv['username'] in username2user
            or inv.get('tg_id') is not None and inv['tg_id'] in id2user  # if not, we just cannot send anything
        ]
        # for every open invitation, decide whether to remind (soon-ness -> reminder probability)
        for inv in open_invitations:
            if event['days_to'] > 14:
                remind_probability = 0.1
            elif event['days_to'] > 7:
                remind_probability = 0.3
            elif event['days_to'] > 3:
                remind_probability = 0.7
            else:
                remind_probability = 1
            if random.random() <= remind_probability:
                # todo: make a custom header (with days to event)
                sent_invitation_to_user(
                    username=inv.get('username'),
                    tg_id=inv.get('tg_id'),
                    event_code=event['code'], database=database, sender=sender,
                    space=space,
                )
                time.sleep(BATCH_MESSAGE_TIMEOUT)
        for invitation in sure_invitations:
            user_account = database.find_user(
                space_name=space.key, username=invitation.get('username'), tg_id=invitation.get('tg_id')
            )
            if user_account is None:
                continue
            if user_account.get('deactivated'):
                print('user {} is deactivated, skipping it'.format(user_account))
                continue
            if invitation.get('payment_status') != InvitationStatuses.PAYMENT_PAID and \
                    event['days_to'] in {0, 1, 3, 5, 7, 14, 21}:
                name = user_account.get('first_name', 'товарищ ' + user_account.get('username', 'Анонимус'))
                text = f'Здравствуйте, {name}! Осталось всего {event["days_to"] + 1} ' \
                       f'дней до очередной встречи {space.title} - /{invitation["code"]}.' \
                       '\nКажется, вы всё ещё не оплатили своё участие во встрече. ' \
                       'Пожалуйста, сделайте это заранее!' \
                       '\n Если вы уже оплатили, пожалуйста, сообщите об этом, ' \
                       'нажав кнопку "Сообщить об оплате".' \
                       f'{space.text_after_messages}'
                intent = EventIntents.PAYMENT_REMINDER
                suggests = ['Сообщить об оплате'] + make_standard_suggests(database=database, user_object=user_account)
                if sender(text=text, database=database, suggests=suggests, user_id=user_account['tg_id']):
                    database.update_user_object(
                        username_or_id=invitation.get('tg_id') or invitation.get('username'),
                        space_name=space.key,
                        change={
                            '$set': {
                                'last_intent': intent, 'event_code': invitation['code'],
                                'last_expected_intent': None,
                            }
                        },
                    )
                time.sleep(BATCH_MESSAGE_TIMEOUT)
            elif event['days_to'] in {0, 5}:
                name = user_account.get('first_name', 'товарищ ' + user_account.get('username', 'Анонимус'))
                days_to = event['days_to'] + 1
                text = f'Здравствуйте, {name}! Осталось всего {days_to} дней до очередной встречи {space.title}\n'
                text = text + format_event_description(event, user_tg_id=user_account['tg_id'], space_name=space.key)
                text = text + '\nСоветую вам полистать пиплбук встречи заранее, чтобы нетворкаться на ней эффективнее.'
                text = text + '\n' + space.text_after_messages + '\U0001f60e'
                intent = EventIntents.NORMAL_REMINDER
                suggests = make_standard_suggests(database=database, user_object=user_account)
                if sender(text=text, database=database, suggests=suggests, user_id=user_account['tg_id']):
                    database.update_user_object(
                        username_or_id=invitation.get('tg_id') or invitation.get('username'),
                        space_name=space.key,
                        change={
                            '$set': {
                                'last_intent': intent, 'event_code': invitation['code'],
                                'last_expected_intent': None,
                            }
                        },
                    )
                time.sleep(BATCH_MESSAGE_TIMEOUT)
    for event in yesterday_events:
        sure_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.ACCEPT, 'space': space.key}
        )
        # todo: unlock it after we change the text
        # for invitation in sure_invitations:
        #    user_account = database.mongo_users.find_one({'username': invitation['username'], 'space': space.key})
        #    if user_account is None:
        #        continue
        #    if database.is_at_least_member(user_object=user_account):
        #        # we send notifications only to guests of an event.
        #        continue
        #    text = "Привет!\n" \
        #           "Надеюсь, тебе понравилась вчерашняя встреча Каппа Веди?\n" \
        #           "В любом случае, мы будем рады, если ты оставишь свою обратную связь о встрече." \
        #           "Для этого мы сделали небольшую анкету, минут на 3-5: http://bit.ly/kvfeedback.\n" \
        #           "Если ты хочешь присоединиться клубу, ты можешь заполнить заявку на вступление" \
        #           "по ссылке http://bit.ly/welcome2kv. Мы рассмотрим её на ближайшей оргвстрече клуба.\n" \
        #           "Спасибо за участие во встрече клуба. Если вы есть, будьте первыми!"
        #    sender(text=text, database=database, user_id=user_account['tg_id'], reset_intent=True,
        #           intent='event_feedback_push')
        #            time.sleep(BATCH_MESSAGE_TIMEOUT)
    for event in past_events:
        undecided_invitations = database.mongo_participations.find(
            {
                'code': event['code'],
                'space': space.key,
                'status': {'$in': list(InvitationStatuses.undecided_states())}
            }
        )
        for invitation in undecided_invitations:
            new_status = InvitationStatuses.make_overdue(invitation.get('status', 'unknown'))
            database.mongo_participations.update_one(
                {'_id': invitation['_id']},
                {'$set': {
                    'status': new_status
                }}
            )


def get_name(username, tg_id, database: Database, space: SpaceConfig):
    uo = database.find_user(space_name=space.key, username=username, tg_id=tg_id)
    if uo is None:
        return 'не в боте'
    return '{} {}'.format(uo.get('first_name', '-'), uo.get('last_name', '-'))


def get_membership(username, tg_id, database, invitor=None):
    if database.is_at_least_member({'username': username, 'tg_id': tg_id}):
        return 'Член клуба'
    else:
        if invitor is None:
            return 'Гость'
        else:
            return 'Гость @{}'.format(invitor)


def event_to_df(event_code, database, space: SpaceConfig):
    event_members = list(database.mongo_participations.find({'code': event_code, 'space': space.key}))
    rows = [
        [
            get_name(username=em.get('username'), tg_id=em.get('tg_id'), database=database, space=space),
            get_membership(
                username=em.get('username'), tg_id=em.get('tg_id'), database=database, invitor=em.get('invitor')
            ),
            'Да',
            InvitationStatuses.translate(em['status'], em.get('payment_status')),
            em.get('payment_details', '-'),
            em.get('username'),
            em.get('tg_id')
        ]
        for em in event_members
    ]
    columns = ['Имя Фамилия', 'Статус', 'Приглашен', 'Согласился', 'Оплата', 'Контакт', 'User ID']

    df = pd.DataFrame(rows, columns=columns).sort_values('Имя Фамилия')
    return df


def event_to_file(event_code, database, space):
    df = event_to_df(event_code, database, space=space)
    filename = 'data_{}.xlsx'.format(event_code)
    df.to_excel(filename)
    return filename
