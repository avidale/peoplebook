from utils.database import Database
from utils.dialogue_management import Context

import random
import re


class Intents:
    OTHER = 'OTHER'
    UNAUTHORIZED = 'UNAUTHORIZED'


def try_conversation(ctx: Context, database: Database):
    if re.match('привет|хай', ctx.text_normalized):
        ctx.intent = 'HELLO'
        ctx.response = random.choice([
            'Приветствую! \U0001f60a',
            'Дратути!\U0001f643',
            'Привет!',
            'Привет-привет',
            'Рад вас видеть!',
            'Здравствуйте, сударь! \U0001f60e'
        ])
    if re.match('благодарю|спасибо|ты супер', ctx.text_normalized):
        ctx.intent = 'GC_THANKS'
        ctx.response = random.choice([
            'И вам спасибо!\U0001F60A',
            'Это моя работа \U0001F60E',
            'Мне тоже очень приятно работать с вами \U0000263A',
            'Ну что вы; не стоит благодарности! \U0001F917',
        ])
    if re.match('ничоси|ничего себе|да ладно|ясно|понятно', ctx.text_normalized):
        ctx.intent = 'GC_SURPRISE'
        ctx.response = random.choice([
            'Да, такие дела \U0000261D',
            'Невероятно, но факт!',
        ])
    return ctx


def fallback(ctx: Context, database: Database):
    if not database.is_at_least_guest(ctx.user_object):
        ctx.intent = Intents.UNAUTHORIZED
        ctx.response = ctx.space.get_text_help_unauthorized()
    else:
        ctx.intent = Intents.OTHER
        ctx.response = ctx.space.get_text_help_authorized()
    return ctx
