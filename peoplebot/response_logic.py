import logging
import os
import random

from collections import defaultdict
from datetime import datetime

from utils.database import Database, LoggedMessage, get_or_insert_user
from utils.dialogue_management import Context
from utils.messaging import BaseSender
from utils.multiverse import Multiverse
from utils.spaces import SpaceConfig, MembershipStatus


from peoplebot.scenarios.events import try_invitation, try_event_usage, try_event_creation, try_event_edition
from peoplebot.scenarios.peoplebook import try_peoplebook_management
from peoplebot.scenarios.peoplebook_from_whois import add_peoplebook_from_whois
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


def respond(message, database: Database, sender: BaseSender, space_cfg: SpaceConfig, bot=None):
    # todo: make it less dependent on telebot Message class structure
    logger.info('Got message {} in space {} with type {} and text {}'.format(
        message.message_id, space_cfg.key, message.content_type, message.text
    ))
    # avoid duplicate response to some Telegram messages
    if message.message_id in PROCESSED_MESSAGES[space_cfg.key]:
        return
    PROCESSED_MESSAGES[space_cfg.key].add(message.message_id)

    if message.chat.type != 'private':
        print('got a message from public chat', message.chat)
        if not message.from_user or not message.chat.id:
            return
        uo = get_or_insert_user(tg_user=message.from_user, space_name=space_cfg.key, database=database)
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
        elif space_cfg.add_chat_members_to_community != MembershipStatus.NONE:
            if not database.is_at_least_guest(user_object=uo):  # todo: check status properly
                # todo: do the right thing if the bot itself was added to the chat (new_chat_members)
                if not message.text or '#whois' not in message.text:
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
                            # todo: edit the text
                            text='Приветствую вас! Представьтесь с тегом `#whois`, иначе я вас кикну.',
                            reply_to=message,
                            database=database,
                            intent='ask_whois',
                        )
                        database.mongo_chat_waiting_list.insert_one(waiting_filter)
                    else:
                        print('not asking user for whois because alredy asked')
                        # the bot has already greeted this user
                        pass
                else:
                    # todo: validate the whois message
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
                    if space_cfg.add_chat_members_to_community == MembershipStatus.GUEST:
                        database.add_guest(username=message.from_user.username, space_name=space_cfg.key)
                    else:
                        # member or admin or owner => just member
                        database.add_member(username=message.from_user.username, space_name=space_cfg.key)
                    sender(
                        # todo: edit the reply text
                        text='Ура! Ваш хуиз прочитан!',
                        reply_to=message,
                        database=database,
                        intent='reply_whois'
                    )
            else:
                # todo: dont' print it
                print('user {} is already a member of community {}'.format(uo.get('username'), space_cfg.key))
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
    def respond(self, message, space: SpaceConfig):
        bot = self.bots_dict[space.key]
        sender = self.senders_dict[space.key]
        return respond(
            message=message,
            space_cfg=space,
            bot=bot,
            sender=sender,
            database=self.db,
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
