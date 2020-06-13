from datetime import datetime
from telebot import TeleBot
from telebot.types import Message

from peoplebot.scenarios.peoplebook_from_whois import add_peoplebook_from_whois, validate_whois_text
from utils.chat_data import ChatData
from utils.database import Database
from utils.messaging import BaseSender
from utils.spaces import SpaceConfig, MembershipStatus
from utils.sugar import fill_none
from utils.wachter_utils import get_public_chat_intro_text, get_public_chat_greeting_text, \
    get_public_chat_failed_greeting_text


def do_wachter_check(
        user_object,
        database: Database,
        space_cfg: SpaceConfig,
        message: Message,
        sender: BaseSender,
        bot: TeleBot,
        chat_data: ChatData,
):
    whois_tag = fill_none(chat_data.whois_tag, space_cfg.whois_tag)
    adding_policy = fill_none(chat_data.add_chat_members_to_community, space_cfg.add_chat_members_to_community)

    if not database.is_at_least_guest(user_object=user_object):
        # todo: do the right thing if the bot itself was added to the chat (new_chat_members)
        if not message.text or whois_tag not in message.text:
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
                    text=get_public_chat_intro_text(space=space_cfg, chat_data=chat_data),
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
                text=get_public_chat_failed_greeting_text(space=space_cfg, chat_data=chat_data),
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
            if fill_none(chat_data.add_whois_to_peoplebook, space_cfg.add_whois_to_peoplebook):
                add_peoplebook_from_whois(
                    message=message,
                    database=database,
                    space_cfg=space_cfg,
                    bot=bot,
                )
            if adding_policy == MembershipStatus.NONE:
                pass
            elif adding_policy == MembershipStatus.GUEST:
                database.add_guest(username=message.from_user.username, space_name=space_cfg.key)
            else:
                # member or admin or owner => just member
                database.add_member(username=message.from_user.username, space_name=space_cfg.key)
            sender(
                text=get_public_chat_greeting_text(space=space_cfg, chat_data=chat_data),
                reply_to=message,
                database=database,
                intent='reply_whois'
            )
    else:
        # todo: don't print it
        pass
        print('user {} is already a member of community {}'.format(user_object.get('username'), space_cfg.key))
