from peoplebot.scenarios.coffee import TAKE_PART, NOT_TAKE_PART

from utils.database import Database
from utils.spaces import FeatureName


def make_standard_suggests(database: Database, user_object):
    suggests = []
    space = database.get_space_for_user(user_object)

    if database.is_at_least_guest(user_object) or space.anyone_can_enter:
        if space.supports(FeatureName.EVENTS):
            suggests.append('Покажи встречи')
        if space.supports(FeatureName.PEOPLEBOOK):
            suggests.append('Мой пиплбук')

    if space.supports(FeatureName.COFFEE):
        if database.has_at_least_level(user_object=user_object, level=space.who_can_use_random_coffee):
            suggests.append(TAKE_PART if not user_object.get('wants_next_coffee') else NOT_TAKE_PART)

    if space.supports(FeatureName.EVENTS):
        if database.has_at_least_level(user_object=user_object, level=space.who_can_create_events):
            suggests.append('Создать встречу')

    if database.is_admin(user_object):
        suggests.append('Добавить членов сообщества')
        if space.community_is_split:
            suggests.append('Добавить членов клуба')
        suggests.append('Выгрузить список членов')

    return suggests
