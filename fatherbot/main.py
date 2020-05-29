import os
import telebot

from flask import Blueprint, Flask, request

from utils.database import Database, get_or_insert_user, LoggedMessage
from utils.dialogue_management import Context
from utils.messaging import BaseSender, TelegramSender
from utils.spaces import SpaceConfig

from peoplebot.new_main import DATABASE

from fatherbot.space_creation import CREATE_A_SPACE, space_creation


FATHER_BOT_USERNAME = 'the_peoplebot'
FATHER_BOT_TOKEN = os.getenv('FATHER_BOT_TOKEN', '')


space = SpaceConfig(key='main', title='The meta space')
father_bot = telebot.TeleBot(FATHER_BOT_TOKEN)
sender = TelegramSender(bot=father_bot, space=space, timeout=0.3)

father_bot_bp = Blueprint('father_bot', __name__)


MAIN_HELP = """Привет, человек!
Я - главный пиплбот. 

Я умею создавать пиплбуки и пиплботов для ваших сообществ и помогаю вам управлять ими.

Пиплбук - это сайт со списком членов вашего сообщества, их фотографиями и краткими представлениями.

Пипблот - это бот, который знает участников сообщества, 
собирает их случайные пары для random coffee и сообщает им о мероприятиях. 

Подробнее вы можете почитать на сайте http://main.peoplebook.space/about.

Чтобы зарегистрировать новое сообщество или управлять имеющимися, воспользуйтесь кнопками.
"""


def first_respond(ctx: Context, database: Database):
    if ctx.text in {'/help', '/start'} or not ctx.text:
        ctx.intent = 'intro'
        ctx.response = MAIN_HELP
        ctx.suggests = [CREATE_A_SPACE]
    return ctx


def fallback_respond(ctx: Context, database: Database):
    ctx.intent = 'fallback'
    ctx.response = MAIN_HELP
    ctx.suggests = [CREATE_A_SPACE]
    return ctx


def respond(message, database: Database, sender: BaseSender, space_cfg: SpaceConfig, bot=None):
    if message.chat.type != 'private':
        print('father peoplebot got a message from public chat', message.chat)
        return
    if bot is not None:
        bot.send_chat_action(message.chat.id, 'typing')

    uo = get_or_insert_user(tg_user=message.from_user, space_name=space_cfg.key, database=database)
    user_id = message.chat.id
    LoggedMessage(
        text=message.text, user_id=user_id, from_user=True, database=database, username=uo.get('username'),
        space_name=space_cfg.key,
    ).save()
    ctx = Context(
        space=space_cfg,
        text=message.text, user_object=uo, sender=sender, message=message, bot=bot,
    )

    for handler in [
        first_respond,
        space_creation,
        fallback_respond,
    ]:
        ctx = handler(ctx, database=database)
        if ctx.intent is not None:
            break

    database.update_user_object(
        username_or_id=message.from_user.id,
        space_name=space_cfg.key,
        use_id=True,
        change=ctx.make_update(),
    )
    sender(
        text=ctx.response, reply_to=message, suggests=ctx.suggests, database=database, intent=ctx.intent,
        file_to_send=ctx.file_to_send,
    )


@father_bot.message_handler(func=lambda message: True)
def process_message(message: telebot.types.Message):
    respond(message=message, database=DATABASE, bot=father_bot, sender=sender, space_cfg=space)


@father_bot_bp.route('/telebot_webhook/' + FATHER_BOT_TOKEN, methods=['POST'])
def get_message():
    father_bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


if __name__ == '__main__':
    app = Flask(__name__)
    app.register_blueprint(father_bot_bp)
    print('running the bot in the polling mode')
    father_bot.polling()

