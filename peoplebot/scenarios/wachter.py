from datetime import datetime
from telebot import TeleBot
from telebot.types import Message

from peoplebot.scenarios.peoplebook_from_whois import add_peoplebook_from_whois, validate_whois_text
from utils.database import Database
from utils.messaging import BaseSender
from utils.spaces import SpaceConfig, MembershipStatus


def do_wachter_check(
        user_object,
        database: Database,
        space_cfg: SpaceConfig,
        message: Message,
        sender: BaseSender,
        bot: TeleBot,
):
    if not database.is_at_least_guest(user_object=user_object):
        # todo: do the right thing if the bot itself was added to the chat (new_chat_members)
        if not message.text or space_cfg.whois_tag not in message.text:
            waiting_filter = {
                'tg_id': message.from_user.id,
                'space': space_cfg.key,
                'chat_id': message.chat.id,
                'active': True,
            }
            waiting = database.mongo_chat_waiting_list.find_one(waiting_filter)
            if waiting is None:
                print('asking user for whois')
                sender(
                    text=space_cfg.get_public_chat_intro_text(),
                    reply_to=message,
                    database=database,
                    intent='ask_whois',
                )
                database.mongo_chat_waiting_list.insert_one(waiting_filter)
            else:
                print('not asking user for whois because alredy asked')
                # the bot has already greeted this user
                pass
        elif not validate_whois_text(message.text):
            print('failed whois')
            sender(
                text=space_cfg.get_public_chat_failed_greeting_text(),
                reply_to=message,
                database=database,
                intent='reply_whois_failed'
            )
        else:
            print('processing the whois')
            database.mongo_whois.insert_one({
                'text': message.text,
                'tg_id': message.from_user.id,
                'username': message.from_user.username,
                'timestamp': str(datetime.utcnow()),
                'chat_id': message.chat.id,
                'space': space_cfg.key,
            })
            database.mongo_chat_waiting_list.update_many(
                {
                    'tg_id': message.from_user.id,
                    'space': space_cfg.key,
                },
                {
                    '$set': {'active': False},
                }
            )
            add_peoplebook_from_whois(
                message=message,
                database=database,
                space_cfg=space_cfg,
                bot=bot,
            )
            if space_cfg.add_chat_members_to_community == MembershipStatus.NONE:
                pass
            elif space_cfg.add_chat_members_to_community == MembershipStatus.GUEST:
                database.add_guest(username=message.from_user.username, space_name=space_cfg.key)
            else:
                # member or admin or owner => just member
                database.add_member(username=message.from_user.username, space_name=space_cfg.key)
            sender(
                text=space_cfg.get_public_chat_greeting_text(),
                reply_to=message,
                database=database,
                intent='reply_whois'
            )
    else:
        # todo: don't print it
        pass
        print('user {} is already a member of community {}'.format(user_object.get('username'), space_cfg.key))
