
import re

from utils import matchers

from utils.database import Database
from utils.dialogue_management import Context


def try_membership_management(ctx: Context, database: Database):
    if not database.is_at_least_member(ctx.user_object):
        return ctx
    # todo: add guest management
    if not database.is_admin(ctx.user_object):
        return ctx
    # member management
    if re.match('(добавь|добавить)( нов(ых|ого))? (члена|членов)( в)? клуба?', ctx.text_normalized):
        ctx.intent = 'MEMBER_ADD_INIT'
        ctx.response = 'Введите телеграмовский логин/логины новых членов КЛУБА через пробел.'
    elif ctx.last_intent == 'MEMBER_ADD_INIT':
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
                resp = resp + '\n@{} успешно добавлен(а) в список членов КЛУБА.'.format(login)
            else:
                resp = resp + '\n@{} уже является членом КЛУБА.'.format(login)
        ctx.response = resp
    elif re.match('(добавь|добавить)( нов(ых|ого))? (члена|членов)( в)? сообществ[оа]', ctx.text_normalized):
        ctx.intent = 'FRIEND_ADD_INIT'
        ctx.response = 'Введите телеграмовский логин/логины новых членов СООБЩЕСТВА через пробел.'
    elif ctx.last_intent == 'FRIEND_ADD_INIT':
        ctx.intent = 'FRIEND_ADD_COMPLETE'
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
    elif re.match('(добавь|добавить)( нов(ых|ого))? (члена|членов)', ctx.text_normalized):
        ctx.intent = 'FRIEND_OR_MEMBER_ADD_TRY'
        ctx.response = 'Напишите "добавить членов клуба", ' \
                       'чтобы добавить членов в Каппа Веди первый (маленькую группу). \n' \
                       'Напишите "добавить членов сообщества", ' \
                       'чтобы добавить членов в Каппа Веди (большую группу).'
    return ctx
