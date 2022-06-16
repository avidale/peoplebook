import logging
import time
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
from utils import wachter_utils


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    require_whois = fill_none(chat_data.require_whois, space_cfg.require_whois)
    if adding_policy == MembershipStatus.NONE and not require_whois:
        logger.info('this space|chat does not add chat members to community and does not require whois; '
                    'skipping wachter')
        return
    logger.info(
        f'starting trying wachter check for chat {chat_data.title} '
        f'and user {user_object.get("username")} with status {database.get_top_status(user_object)}'
    )
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
                logger.info('asking user for whois')
                sender(
                    text=get_public_chat_greeting_text(space=space_cfg, chat_data=chat_data),
                    reply_to=message,
                    database=database,
                    intent='ask_whois',
                )
                database.mongo_chat_waiting_list.insert_one(waiting_filter)
            else:
                logger.info('not asking user for whois because alredy asked')
                # the bot has already greeted this user
                pass
        elif not validate_whois_text(message.text):
            logger.info('failed whois')
            sender(
                text=get_public_chat_failed_greeting_text(space=space_cfg, chat_data=chat_data),
                reply_to=message,
                database=database,
                intent='reply_whois_failed'
            )
        else:
            logger.info('processing the whois')
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
                logger.info('trying adding to peoplebook from whois (if it is empty)')
                add_peoplebook_from_whois(
                    message=message,
                    database=database,
                    space_cfg=space_cfg,
                    bot=bot,
                )
            if adding_policy == MembershipStatus.NONE:
                logger.info('do not add user of the chat to the club due to empty adding policy')
                pass
            elif adding_policy == MembershipStatus.GUEST:
                database.add_guest(tg_id=message.from_user.id, space_name=space_cfg.key)
                logger.info('make user of the chat a guest due to adding policy')
            elif adding_policy == MembershipStatus.FRIEND:
                database.add_friend(tg_id=message.from_user.id, space_name=space_cfg.key)
                logger.info('make user of the chat a "friend" (unprivileged member) due to adding policy')
            else:
                # member or admin or owner => just member
                database.add_member(tg_id=message.from_user.id, space_name=space_cfg.key)
                logger.info('make user of the chat a member due to adding policy')
            sender(
                text=get_public_chat_intro_text(space=space_cfg, chat_data=chat_data),
                reply_to=message,
                database=database,
                intent='reply_whois'
            )
    else:
        # todo: don't print it
        pass
        logger.info('user {} is already a member of community {}'.format(user_object.get('username'), space_cfg.key))


def kick_all_space(
        db: Database,
        space_cfg: SpaceConfig,
        sender: BaseSender,
        bot: TeleBot,
):
    for record in db.mongo_chats.find({'space': space_cfg.key}):
        chat_data = ChatData.from_record(
            record=record,
            chat_id=None,
            space=space_cfg.key,
        )
        kick_timeout = wachter_utils.get_kick_timeout(space=space_cfg, chat_data=chat_data)
        if not kick_timeout:
            continue
        for item in db.mongo_chat_waiting_list.find({
            'space': space_cfg.key,
            'chat_id': chat_data.chat_id,
            'active': True,
        }):
            now = datetime.utcnow()
            prev = datetime.fromisoformat(item.get('timestamp', str(now)))
            diff = (now-prev).total_seconds() / 60
            if diff < kick_timeout:
                continue
            user_id = item['tg_id']
            chat_membership = bot.get_chat_member(chat_id=chat_data.chat_id, user_id=user_id)
            status = chat_membership.status
            # Can be “creator”, “administrator”, “member”, “restricted”, “left” or “kicked”
            if chat_membership in {'member', 'restricted'}:
                sender(
                    user_id=chat_data.chat_id,
                    text='Удаляю вас из чата из-за отсутствия представления.',
                    database=db,
                    intent='kick',
                )
                bot.kick_chat_member(
                    chat_id=chat_data.chat_id,
                    user_id=user_id,
                    until_date=int(time.time()) + 60 * 5  # after 5 minutes the user can retry
                )
            else:
                print(f'cannot kick {item}, because their chat status is {status}')
            db.mongo_chat_waiting_list.update_many(
                {
                    'space': space_cfg.key,
                    'chat_id': chat_data.chat_id,
                    'active': True,
                }, {
                    '$set': {'active': False}
                }
            )
