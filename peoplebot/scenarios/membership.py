
import re

from config import DEFAULT_SPACE
from utils import matchers

from utils.database import Database
from utils.dialogue_management import Context


def _add_member(ctx: Context, database: Database, club_name='сообщества'):
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


def _add_guest(ctx: Context, database: Database):
    logins = [matchers.normalize_username(c.strip(',').strip('@').lower()) for c in ctx.text.split()]
    resp = 'Вот что получилось:'
    for login in logins:
        if not matchers.is_like_telegram_login(login):
            resp = resp + '\nСлово "{}" не очень похоже на логин, пропускаю.'.format(login)
            continue
        existing = database.mongo_membership.find_one({'username': login, 'space': ctx.space.key})
        if existing is not None and existing.get('is_member'):
            resp = resp + '\n@{} уже является членом СООБЩЕСТВА и даже КЛУБА.'.format(login)
        elif existing is not None and existing.get('is_guest'):
            resp = resp + '\n@{} уже является членом СООБЩЕСТВА (но не КЛУБА).'.format(login)
        else:
            database.mongo_membership.update_one(
                {'username': login, 'space': ctx.space.key},
                {'$set': {'is_guest': True}},
                upsert=True
            )
            resp = resp + '\n@{} успешно добавлен(а) в список членов СООБЩЕСТВА (но не КЛУБА).'.format(login)
    ctx.response = resp


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
            _add_guest(ctx=ctx, database=database)
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
    return ctx
