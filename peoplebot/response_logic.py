import logging
import os
import random

from collections import defaultdict
from telebot.types import Message

from utils.database import Database, LoggedMessage, get_or_insert_user
from utils.dialogue_management import Context
from utils.messaging import BaseSender
from utils.multiverse import Multiverse
from utils.spaces import SpaceConfig, MembershipStatus


from peoplebot.scenarios.chat_stats import update_chat_stats, tag_everyone
from peoplebot.scenarios.events import try_invitation, try_event_usage, try_event_creation, try_event_edition
from peoplebot.scenarios.peoplebook import try_peoplebook_management
from peoplebot.scenarios.wachter import do_wachter_check
from peoplebot.scenarios.conversation import try_conversation, fallback
from peoplebot.scenarios.dog_mode import doggy_style
from peoplebot.scenarios.push import try_queued_messages
from peoplebot.scenarios.membership import try_membership_management
from peoplebot.scenarios.coffee import try_coffee_management, try_coffee_feedback_collection
from peoplebot.scenarios.suggests import make_standard_suggests

from peoplebot.scenarios.coffee import daily_random_coffee
from peoplebot.scenarios.events import daily_event_management

ADMIN_URL_PREFIX = os.environ.get('ADMIN_URL_PREFIX') or str(random.random())
PROCESSED_MESSAGES = defaultdict(set)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def respond(message: Message, database: Database, sender: BaseSender, space_cfg: SpaceConfig, bot=None, edited=False):
    # todo: make it less dependent on telebot Message class structure
    logger.info('Got message {} in space {} with type {} and text {}'.format(
        message.message_id, space_cfg.key, message.content_type, message.text
    ))
    # avoid duplicate response to some Telegram messages
    if message.message_id in PROCESSED_MESSAGES[space_cfg.key] and not edited:
        print('ignoring a repeated message')
        return
    elif edited:
        print('processing an edited message')
    PROCESSED_MESSAGES[space_cfg.key].add(message.message_id)

    if message.chat.type != 'private':
        print('got a message from public chat', message.chat)
        if not message.from_user or not message.chat.id:
            return
        uo = get_or_insert_user(tg_user=message.from_user, space_name=space_cfg.key, database=database)
        update_chat_stats(user_object=uo, db=database, chat_id=message.chat.id)

        # tage everyone in the chat
        if message.text and (
                message.text.startswith('/all@{}'.format(space_cfg.bot_username))
                or message.text == '/all'
        ):
            sender(
                text=tag_everyone(db=database, chat_id=message.chat.id),
                reply_to=message,
                database=database,
                intent='tag_all',
            )

        if not uo.get('username'):
            # todo: ask new users to provide usernames
            return

        user_filter = {'username': uo['username'], 'space': space_cfg.key}
        if space_cfg.member_chat_id and message.chat.id == space_cfg.member_chat_id:
            print('adding user {} to the community members'.format(user_filter))
            database.mongo_membership.update_one(user_filter, {'$set': {'is_member': True}}, upsert=True)
        elif space_cfg.guest_chat_id and message.chat.id == space_cfg.guest_chat_id:
            database.mongo_membership.update_one(user_filter, {'$set': {'is_guest': True}}, upsert=True)
            print('adding user {} to the community guests'.format(user_filter))
        elif space_cfg.add_chat_members_to_community != MembershipStatus.NONE or space_cfg.require_whois:
            do_wachter_check(
                user_object=uo,
                database=database,
                space_cfg=space_cfg,
                message=message,
                bot=bot,
                sender=sender,
            )
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
        try_queued_messages,
        try_invitation,
        try_event_creation,
        try_event_usage,
        try_peoplebook_management,
        try_coffee_management,
        try_membership_management,
        try_event_edition,
        try_conversation,
        try_coffee_feedback_collection,
        doggy_style,
        fallback,
    ]:
        ctx = handler(ctx, database=database)
        if ctx.intent is not None:
            break

    assert ctx.intent is not None
    assert ctx.response is not None
    database.update_user_object(
        username_or_id=message.from_user.id,
        space_name=space_cfg.key,
        use_id=True,
        change=ctx.make_update(),
    )
    user_object = get_or_insert_user(tg_uid=message.from_user.id, space_name=space_cfg.key, database=database)

    # context-independent suggests (they are always below the dependent ones)
    ctx.suggests.extend(make_standard_suggests(database=database, user_object=user_object))

    logger.info('Start sending an already prepared reply to {}'.format(message.message_id))
    sender(
        text=ctx.response, reply_to=message, suggests=ctx.suggests, database=database, intent=ctx.intent,
        file_to_send=ctx.file_to_send,
    )
    logger.info('Sent message with text {} as reply to {}'.format(ctx.response, message.message_id))


class NewMultiverse(Multiverse):
    def respond(self, message, space: SpaceConfig, edited: bool = False):
        bot = self.bots_dict[space.key]
        sender = self.senders_dict[space.key]
        return respond(
            message=message,
            space_cfg=space,
            bot=bot,
            sender=sender,
            database=self.db,
            edited=edited,
        )

    def add_custom_handlers(self):
        self.app.route("/{}/restart-coffee/".format(ADMIN_URL_PREFIX))(self.force_restart_coffee)
        self.app.route("/{}/send-events/".format(ADMIN_URL_PREFIX))(self.do_event_management)
        self.app.route("/{}/wakeup/".format(ADMIN_URL_PREFIX))(self.wake_up)

    def wake_up(self):
        self.all_random_coffee()
        self.all_event_management()
        return "Ежедневная встряска произошла!", 200

    def do_event_management(self):
        self.all_event_management()
        return "Сделал со встречами всё, что хотел!", 200

    def force_restart_coffee(self):
        self.all_random_coffee(force_restart=True)
        return "Кофе перезапущен!", 200

    def all_random_coffee(self, force_restart=False):
        self.init_spaces()
        for space_name, space in self.spaces_dict.items():
            if space_name not in self.senders_dict:
                continue
            daily_random_coffee(
                database=self.db,
                sender=self.senders_dict[space_name],
                space=space,
                force_restart=force_restart,
            )

    def all_event_management(self):
        self.init_spaces()
        for space_name, space in self.spaces_dict.items():
            if space_name not in self.senders_dict:
                continue
            daily_event_management(
                database=self.db,
                sender=self.senders_dict[space_name],
                space=space,
            )
