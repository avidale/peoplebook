import argparse
import logging
import os
import sentry_sdk

from fatherbot.main import father_bot, father_bot_bp
from peoplebot.new_main import MULTIVERSE, DATABASE
from peoplebook.web import app

from peoplebook.web_itinder import itinder_bp
from peoplebook.admins import admin_bp

logging.basicConfig(level=logging.INFO)


if os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(os.environ.get('SENTRY_DSN'))


def run_bot_and_book():
    parser = argparse.ArgumentParser(description='Run the bot and peoplebook')
    parser.add_argument('--poll', action='store_true', help='Run one bot in local mode')
    parser.add_argument('--space', type=str, help='The space for which to run the polling bot')
    parser.add_argument('--nobot', action='store_true', help='Do not run the bots (peoplebook only)')
    args = parser.parse_args()
    if args.poll:
        # todo: don't run the searcher here because it is slow
        if not args.space:
            if len(MULTIVERSE.bots_dict) > 1:
                print('There are multiple bots. To run one, provide the --space argument.')
                return
            else:
                bot = list(MULTIVERSE.bots_dict.values())[0]
        elif args.space == 'main':
            bot = father_bot_bp
        else:
            print('I will start the bot for space {}'.format(args.space))
            bot = MULTIVERSE.bots_dict[args.space]
        bot.remove_webhook()
        print('running a bot in the polling mode')
        bot.polling()
    else:
        if not args.nobot:
            MULTIVERSE.set_web_hooks()
            app.register_blueprint(MULTIVERSE.app)
        app.database = DATABASE
        app.register_blueprint(itinder_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(father_bot_bp)
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    run_bot_and_book()
