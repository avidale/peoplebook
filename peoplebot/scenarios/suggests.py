from peoplebot.scenarios.coffee import TAKE_PART, NOT_TAKE_PART

from utils.database import Database
from utils.spaces import FeatureName


def make_standard_suggests(database: Database, user_object):
    suggests = []
    space = database.get_space_for_user(user_object)

    if database.is_at_least_guest(user_object):
        if space.supports(FeatureName.EVENTS):
            suggests.append('Покажи встречи')
        if space.supports(FeatureName.PEOPLEBOOK):
            suggests.append('Мой пиплбук')
        if space.supports(FeatureName.COFFEE):
            suggests.append(TAKE_PART if not user_object.get('wants_next_coffee') else NOT_TAKE_PART)

    if database.is_admin(user_object):
        if space.supports(FeatureName.EVENTS):
            suggests.append('Создать встречу')
        suggests.append('Добавить членов клуба')
        if space.key == 'kv':
            # todo: make it configurable
            suggests.append('Добавить членов сообщества')

    return suggests
