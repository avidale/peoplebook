import pandas as pd
import re

from config import DEFAULT_SPACE
from peoplebot.scenarios.suggests import make_standard_suggests
from utils import matchers

from utils.database import Database
from utils.dialogue_management import Context
from utils.matchers import normalize_username
from utils.spaces import SpaceConfig


def _add_member(ctx: Context, database: Database, club_name='сообщества'):
    # todo: add telegram id if it is possible
    ctx.intent = 'MEMBER_ADD_COMPLETE'
    logins = [matchers.normalize_username(c.strip(',').strip('@').lower()) for c in ctx.text.split()]
    resp = 'Вот что получилось:'
    for login in logins:
        if not matchers.is_like_telegram_login(login):
            resp = resp + '\nСлово "{}" не очень похоже на логин, пропускаю.'.format(login)
            continue
        existing = database.mongo_membership.find_one(
            {'username': login, 'is_member': True, 'space': ctx.space.key}
        )
        if existing is None:
            database.mongo_membership.update_one(
                {'username': login, 'space': ctx.space.key},
                {'$set': {'is_member': True}},
                upsert=True
            )
            resp = resp + '\n@{} успешно добавлен(а) в список членов {}.'.format(login, club_name)
        else:
            resp = resp + '\n@{} уже является членом {}.'.format(login, club_name)
    ctx.response = resp


def _add_friend(ctx: Context, database: Database):
    # todo: add telegram id if it is possible
    logins = [matchers.normalize_username(c.strip(',').strip('@').lower()) for c in ctx.text.split()]
    resp = 'Вот что получилось:'
    for login in logins:
        if not matchers.is_like_telegram_login(login):
            resp = resp + '\nСлово "{}" не очень похоже на логин, пропускаю.'.format(login)
            continue
        existing = database.mongo_membership.find_one({'username': login, 'space': ctx.space.key})
        if existing is not None and existing.get('is_member'):
            resp = resp + '\n@{} уже является членом СООБЩЕСТВА и даже КЛУБА.'.format(login)
        elif existing is not None and existing.get('is_friend'):
            resp = resp + '\n@{} уже является членом СООБЩЕСТВА (но не КЛУБА).'.format(login)
        else:
            database.mongo_membership.update_one(
                {'username': login, 'space': ctx.space.key},
                {'$set': {'is_friend': True}},
                upsert=True
            )
            resp = resp + '\n@{} успешно добавлен(а) в список членов СООБЩЕСТВА (но не КЛУБА).'.format(login)
    ctx.response = resp


new_admin = re.compile('(сделай админом|дай админку|добавь в админы) (?P<un>@[a-zA-Z0-9_]+)$')
remove_admin = re.compile('(отними админку|убери из админов) (?P<un>@[a-zA-Z0-9_]+)$')
remove_club_member = re.compile('(удали(ть))( из клуба)? (?P<un>@[a-zA-Z0-9_]+)( из клуба)?$')
remove_community_member = re.compile('(удали(ть))( из сообщества)? (?P<un>@[a-zA-Z0-9_]+)( из сообщества)?$')


def try_membership_management(ctx: Context, database: Database):
    if not database.is_at_least_member(ctx.user_object):
        return ctx

    # todo: add guest management
    if not database.is_admin(ctx.user_object):
        return ctx
    # member management
    if re.match('(добавь|добавить)( нов(ых|ого))? (члена|членов)( в)? клуба?', ctx.text_normalized):
        ctx.intent = 'MEMBER_ADD_INIT'
        if ctx.space.community_is_split:
            ctx.response = 'Введите телеграмовский логин/логины новых членов КЛУБА через пробел.'
        else:
            ctx.response = 'Введите телеграмовский логин/логины новых членов сообщества через пробел.'
    elif ctx.last_intent == 'MEMBER_ADD_INIT':
        if ctx.space.community_is_split:
            _add_member(ctx=ctx, database=database, club_name='КЛУБА')
        else:
            _add_member(ctx=ctx, database=database)
    elif re.match('(добавь|добавить)( нов(ых|ого))? (члена|членов)( в)? сообществ[оа]', ctx.text_normalized):
        ctx.intent = 'FRIEND_ADD_INIT'
        if ctx.space.community_is_split:
            ctx.response = 'Введите телеграмовский логин/логины новых членов СООБЩЕСТВА через пробел.'
        else:
            ctx.response = 'Введите телеграмовский логин/логины новых членов сообщества через пробел.'
    elif ctx.last_intent == 'FRIEND_ADD_INIT':
        ctx.intent = 'FRIEND_ADD_COMPLETE'
        if ctx.space.community_is_split:
            _add_friend(ctx=ctx, database=database)
        else:
            _add_member(ctx=ctx, database=database)
    elif re.match('(добавь|добавить)( нов(ых|ого))? (члена|членов)', ctx.text_normalized):
        ctx.intent = 'FRIEND_OR_MEMBER_ADD_TRY'
        if ctx.space.community_is_split:
            ctx.response = 'Напишите "добавить членов клуба", ' \
                           'чтобы добавить членов в Каппа Веди первый (маленькую группу). \n' \
                           'Напишите "добавить членов сообщества", ' \
                           'чтобы добавить членов в Каппа Веди (большую группу).'
            ctx.suggests.append('Добавить членов клуба')
            ctx.suggests.append('Добавить членов сообщества')
        else:
            ctx.intent = 'MEMBER_ADD_INIT'
            ctx.response = 'Введите телеграмовский логин/логины новых членов сообщества через пробел.'

    elif re.match('.*список (всех )?(участников|членов)', ctx.text_normalized):
        ctx.intent = 'MEMBER_DOWNLOAD_LIST'
        ctx.response = 'Готовлю выгрузку участников сообщества, сейчас пришлю.'
        ctx.file_to_send = members_to_file(database=database, space=ctx.space)

    elif re.match('.*список (всех )?(админов|администраторов)', ctx.text_normalized):
        ctx.intent = 'ADMINS_LIST'
        ctx.response = 'Админы такие: ' + ', '.join(f'@{a}' for a in ctx.space.admins)

    elif re.match(new_admin, ctx.text):
        ctx.intent = 'ADMINS_ADD'
        un = re.match(new_admin, ctx.text).groupdict().get('un')
        if not un:
            ctx.response = 'Не понял, кого сделать админом, простите.'
        else:
            un = normalize_username(un)
            if un in ctx.space.admins:
                ctx.response = f'@{un} уже админ!'
            else:
                ctx.space.admins.append(un)
                database.mongo_spaces.update_one({'key': ctx.space.key}, {'$set': {'admins': ctx.space.admins}})
                ctx.response = f'Окей, делаю @{un} админом данного сообщества!'

    elif re.match(remove_admin, ctx.text):
        ctx.intent = 'ADMINS_REMOVE'
        un = re.match(remove_admin, ctx.text).groupdict().get('un')
        if not un:
            ctx.response = 'Не понял, кого убрать из админов, простите.'
        else:
            un = normalize_username(un)
            if un not in ctx.space.admins:
                ctx.response = f'@{un} уже и так не админ!'
            else:
                ctx.space.admins.remove(un)
                database.mongo_spaces.update_one({'key': ctx.space.key}, {'$set': {'admins': ctx.space.admins}})
                ctx.response = f'Окей, убираю @{un} из админов данного сообщества!'

    elif re.match(remove_club_member, ctx.text) or re.match(remove_community_member, ctx.text):
        from_club = True
        ctx.intent = 'REMOVE_FROM_CLUB'
        if not re.match(remove_club_member, ctx.text) and re.match(remove_community_member, ctx.text):
            from_club = False
            ctx.intent = 'REMOVE_FROM_COMMUNITY'

        un = re.match(remove_club_member, ctx.text).groupdict().get('un')
        if not un:
            ctx.response = 'Не понял, кого вы хотите удалить, простите.'
        else:
            un = normalize_username(un)
            status = database.get_top_status({'username': un})

            if status in {'admin', 'member'} or status == 'friend' and not from_club:
                remove_from = 'из клуба' if from_club else 'из сообщества'
                if status == 'admin':
                    text_status = 'админ'
                elif status == 'member':
                    text_status = 'член клуба'
                else:
                    text_status = 'член сообщества'
                ctx.response = f'У пользователя @{un} статус "{text_status}". ' \
                               f'Вы действительно хотите удалить его {remove_from}?'
                ctx.suggests.insert(0, 'да')
                ctx.expected_intent = ctx.intent + '__CONFIRM'
                ctx.the_update = {'$set': {'removal': {'user': un, 'status': status, 'from_club': from_club}}}
            else:
                ctx.response = 'Не удалось убедиться, что '

    elif ctx.last_expected_intent in {'REMOVE_FROM_CLUB__CONFIRM', 'REMOVE_FROM_COMMUNITY__CONFIRM'} \
            and matchers.is_like_yes(ctx.text_normalized) and ctx.user_object.get('removal'):
        mem = ctx.user_object['removal']
        ctx.intent = ctx.last_expected_intent
        if mem['status'] == 'admin':
            ctx.space.admins = [u for u in ctx.space.admins if u != mem["user"]]
            database.mongo_spaces.update_one({'key': ctx.space.key}, {'$set': {'admins': ctx.space.admins}})

        the_update = {'is_member': False}
        if not mem['from_club']:
            the_update['is_friend'] = False
        database.mongo_membership.update_many(
            {'username': mem['user'], 'space': ctx.space.key},
            {'$set': the_update},
            upsert=False
        )
        ctx.the_update = {'$unset': {'removal': ''}}
        database.update_cache(force=True)
        ctx.response = f'Юзер @{mem["user"]} был успешно удалён. Но сообщить об этом ему/ей вам надо самостоятельно.'

    return ctx


def try_add_new_member_to_open_community(ctx: Context, database: Database):
    if database.is_at_least_member(ctx.user_object):
        # if a user is already a member, no action is required
        return ctx
    if not ctx.space.anyone_can_enter:
        return ctx

    # todo: ask a codeword, if it is provided

    database.mongo_membership.update_one(
        {'username': ctx.username, 'tg_id': ctx.tg_id,  'space': ctx.space.key},
        {'$set': {'is_member': True}},
        upsert=True
    )
    database.update_cache(force=True)

    ctx.intent = 'SELF_ADD_TO_OPEN_MEMBERSHIP'
    ctx.response = 'Вы успешно добавились в сообщество! ' \
                   '\nЕсли у вас есть какие-то вопросы по существу, ' \
                   'задавайте их человеку, который поделился с вами данным ботом. ' \
                   '\nС техническими вопросами по работе бота можно обращаться к @cointegrated.\n\n'
    ctx.response += ctx.space.get_text_help_authorized(user_object=ctx.user_object)
    ctx.suggests.extend(make_standard_suggests(database=database, user_object=ctx.user_object))

    return ctx


def members_to_file(database: Database, space: SpaceConfig):
    users = list(database.mongo_users.find({'space': space.key}))
    pb = {u['username']: u for u in database.mongo_peoplebook.find({'space': space.key})}

    for u in users:
        u['status'] = database.get_top_status(u)
        if not u['username']:
            continue
        uu = pb.get(u['username'])
        if not uu:
            continue
        u['pb_first_name'] = uu.get('first_name')
        u['pb_last_name'] = uu.get('last_name')
        for k in ['activity', 'topics', 'contacts', 'photo']:
            u[k] = uu.get(k)

    df = pd.DataFrame(users)
    columns = [
        'tg_id', 'username', 'first_name', 'last_name',
        'status',
        'pb_first_name', 'pb_last_name',
        'activity', 'topics', 'contacts', 'photo', 'wants_next_coffee',

    ]
    fdf = df[columns]
    filename = f'members_{space.key}.xlsx'
    fdf.to_excel(filename)
    return filename
