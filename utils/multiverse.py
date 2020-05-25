import telebot

from flask import Blueprint, request
from typing import Dict

from utils.spaces import SpaceConfig
from utils.database import Database


class Multiverse:
    """ This class handles multiple spaces and multiple bot instances for them """
    # todo: move some code from response_logic, main and messaging - to here.
    # но вообще над реально подумать, как должна выглядеть самая простая архитектура тут.

    def __init__(self, db: Database, base_url, bot_url_prefix='telebot_webhook/'):
        self.db: Database = db
        self.base_url = base_url
        self.spaces_dict: Dict[str, SpaceConfig] = {}
        self.bots_dict: Dict[str, telebot.TeleBot] = {}

        self.app = Blueprint('bot_app', __name__)
        self.bot_url_prefix = bot_url_prefix  # todo: move it into the blueprint

    def init_spaces(self):
        """ Create/update a config for each space """
        self.spaces_dict = {}
        for raw_config in self.db.mongo_spaces.find({}):
            space = SpaceConfig.from_record(raw_config)
            self.spaces_dict[space.key] = space

    def bot_url_suffix(self, space_name):
        space = self.spaces_dict[space_name]
        return '/' + self.bot_url_prefix + space.bot_token

    def respond(self, message, space: SpaceConfig):
        # respond(message=msg, database=self.db, sender=SENDER, bot=bot, space_cfg=space)
        raise NotImplementedError()

    def create_bots(self):
        """ Setup a telegram bot for each space """
        for space_name, space in self.spaces_dict.items():
            if not space.bot_token:
                continue
            bot = telebot.TeleBot(token=space.bot_token)
            self.bots_dict[space_name] = bot

            def process_message(msg):
                self.respond(message=msg, space=space)

            bot.message_handler(func=lambda message: True)(process_message)

            def get_message():
                bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
                return "!", 200

            self.app.route(self.bot_url_suffix(space_name), methods=['POST'])(get_message)
            # self.app.route("/" + self.restart_webhook_url)(self.telegram_web_hook)

    def set_web_hooks(self):
        for space_name, bot in self.bots_dict.items():
            bot.remove_webhook()
            bot.set_webhook(self.base_url + self.bot_url_suffix(space_name))
