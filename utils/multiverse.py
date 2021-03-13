import logging
import telebot

from flask import Blueprint, request
from typing import Dict

from utils.database import Database
from utils.messaging import BaseSender, TelegramSender
from utils.spaces import SpaceConfig


logger = logging.getLogger(__name__)


ALL_CONTENT_TYPES = [
    'audio', 'channel_chat_created', 'contact', 'delete_chat_photo', 'document', 'group_chat_created',
    'left_chat_member',
    'location', 'migrate_from_chat_id', 'migrate_to_chat_id', 'new_chat_members', 'new_chat_photo', 'new_chat_title',
    'photo', 'pinned_message', 'sticker', 'supergroup_chat_created', 'text', 'video', 'video_note', 'voice',
]


class Multiverse:
    """ This class handles multiple spaces and multiple bot instances for them """

    def __init__(self, db: Database, base_url, bot_url_prefix='telebot_webhook/'):
        self.db: Database = db
        self.base_url = base_url
        self.spaces_dict: Dict[str, SpaceConfig] = {}
        self.bots_dict: Dict[str, telebot.TeleBot] = {}
        self.token2bot: Dict[str, telebot.TeleBot] = {}
        self.senders_dict: Dict[str, BaseSender] = {}

        self.app = Blueprint('bot_app', __name__)
        self.bot_url_prefix = bot_url_prefix  # todo: move it into the blueprint
        self.app.route(self.bot_url_prefix + '<bot_token>', methods=['POST'])(
            self.common_updates_processor
        )

    def init_spaces(self):
        """ Create/update a config for each space """
        self.spaces_dict = {}
        for raw_config in self.db.mongo_spaces.find({}):
            space = SpaceConfig.from_record(raw_config)
            self.spaces_dict[space.key] = space
            logger.info(f'creating a space: {space.key}')

    def bot_url_suffix(self, space_name):
        space = self.spaces_dict[space_name]
        return '/' + self.bot_url_prefix + space.bot_token

    def respond(self, message, space: SpaceConfig, edited: bool = False):
        # respond(message=msg, database=self.db, sender=SENDER, bot=bot, space_cfg=space)
        raise NotImplementedError()

    def add_custom_handlers(self):
        pass

    def make_updates_processor(self, bot, function_suffix):
        def updates_processor():
            bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
            return "!", 200
        # this hack is for Flask that uses __name__ as a lookup key
        updates_processor.__name__ = updates_processor.__name__ + '__' + function_suffix
        return updates_processor

    def common_updates_processor(self, bot_token):
        bot = self.token2bot.get(bot_token)
        if not bot:
            return 'bot not found!', 404
        bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
        return "!", 200

    def make_message_handler(self, space_name, edited=False):
        def process_message(msg):
            space = self.db.get_space(space_name)
            self.respond(message=msg, space=space, edited=edited)
        return process_message

    def create_bots(self, timeout_between_messages=0.3):
        """ Setup a telegram bot for each space """
        for space_name, space in self.spaces_dict.items():
            if not space.bot_token:
                logger.info(f'for space {space.key} no bot token exists, skipping it')
                continue
            bot = telebot.TeleBot(token=space.bot_token)
            self.bots_dict[space_name] = bot
            self.token2bot[space.bot_token] = bot
            sender = TelegramSender(space=space, bot=bot, timeout=timeout_between_messages)
            self.senders_dict[space_name] = sender

            bot.message_handler(func=lambda message: True, content_types=ALL_CONTENT_TYPES)(
                self.make_message_handler(space_name=space_name, edited=False)
            )
            bot.edited_message_handler(func=lambda message: True, content_types=ALL_CONTENT_TYPES)(
                self.make_message_handler(space_name=space_name, edited=True)
            )
            self.app.route(self.bot_url_suffix(space_name), methods=['POST'])(
                self.make_updates_processor(bot, function_suffix=space_name)
            )
            logger.info(f'have created a bot for space {space.key}')
            # self.app.route("/" + self.restart_webhook_url)(self.telegram_web_hook)
        self.add_custom_handlers()

    def set_web_hooks(self):
        for space_name, bot in self.bots_dict.items():
            bot.remove_webhook()
            url = self.base_url + self.bot_url_suffix(space_name)
            bot.set_webhook(url)
            logger.info(f'have created a bot webhook for space {space_name} at {url}')
