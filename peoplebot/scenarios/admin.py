from utils.database import Database
from utils.dialogue_management import Context
from config import DEMIURGE
from utils.multiverse import Multiverse

SUPERPUSH_COMMAND = "/superpush"


def superpush_message_handler(ctx: Context, database: Database):
    if ctx.text.startswith(SUPERPUSH_COMMAND):
        ctx.intent = 'SUPERPUSH'
        if DEMIURGE is not None and ctx.username == DEMIURGE:
            from peoplebot.new_main import MULTIVERSE
            to_send = ctx.text[len(SUPERPUSH_COMMAND) + 1:]
            if len(to_send) >= 5:
                warning = 'Ваше сообщение поставлено в очередь на отправку ВСЕМ пользователям. ' \
                          'Надеюсь, вы этого хотели!'
                ctx.sender(text=warning, database=database, suggests=[], user_id=ctx.user_object['tg_id'])
                result_text = do_superpush(database=database, message=to_send, multiverse=MULTIVERSE)
                ctx.response = "Ваш суперпуш отправлен! Результаты вот:\n" + str(result_text)
            else:
                ctx.response = 'Ваше сообщение слишком короткое. Непохоже на глобальный пуш, поэтому я его не отправил.'
        else:
            ctx.response = f"Вы не являетесь суперадмином, и не можете отправлять такие пуши. "\
                           f"Извините. Все вопросы к @{DEMIURGE}."

    return ctx


def do_superpush(database: Database, message: str, multiverse: Multiverse) -> str:
    results = []
    for space_key, space in multiverse.spaces_dict.items():
        sender = multiverse.senders_dict[space_key]
        users = list(database.mongo_users.find({"space": space_key}))
        n = 0
        for user_account in users:
            intent = 'GET_BROADCASTED_MESSAGE'
            outcome = sender(
                text=message, database=database, suggests=["Ок"], user_id=user_account['tg_id'],
                reset_intent=True, intent=intent,
            )
            n += int(outcome)
        results.append([space_key, len(users), n])

    result = "\n".join([
        f"space: {x[0]}, total users: {x[1]}, sent successfully: {x[2]}"
        for x in results
    ])
    return result
