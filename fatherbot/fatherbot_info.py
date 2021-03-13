from config import PEOPLEBOOK_ROOT
from utils.database import Database
from utils.dialogue_management import Context


MY_CLUBS = 'мои сообщества'


def info_respond(ctx: Context, database: Database) -> Context:
    if ctx.text in {MY_CLUBS}:
        ctx.intent = 'my_clubs'
        spaces = database.where_user_is_admin(username=ctx.username, tg_id=ctx.tg_id)
        if not spaces:
            ctx.response = 'Вы пока не являетесь админом ни в одном сообществе. ' \
                           'Воспользуйтесь моими кнопками, чтобы добавить сообщество!'
            return ctx
        ctx.response = f'Вот ваши сообщества. Для управления, пожалуйста, воспользуйтесь ссылками.'
        for space in spaces:
            url = f'{PEOPLEBOOK_ROOT}/admin/{space.key}/details'
            t = f'\n - {space.title} ({space.key}) {url}'
            ctx.response += t
    return ctx
