import argparse
import logging
import os
import sentry_sdk

from apscheduler.schedulers.background import BackgroundScheduler
from frequent_wakeup import do_frequent_wakeup
from wakeup import do_wakeup

if os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(os.environ['SENTRY_DSN'])

from fatherbot.main import father_bot, father_bot_bp, set_father_webhook
from peoplebot.new_main import MULTIVERSE, BASE_URL
from utils.global_database import DATABASE
from peoplebook.web import app

from peoplebook.web_itinder import itinder_bp, get_pb_dict
from peoplebook.admins import admin_bp

from peoplebook.profile_searcher import ProfileSearcher, load_ft

logging.basicConfig(level=logging.INFO)


def run_bot_and_book():
    parser = argparse.ArgumentParser(description='Run the bot and peoplebook')
    parser.add_argument('--poll', action='store_true', help='Run one bot in local mode')
    parser.add_argument('--space', type=str, help='The space for which to run the polling bot')
    parser.add_argument('--nobot', action='store_true', help='Do not run the bots (peoplebook only)')
    parser.add_argument('--nosearch', action='store_true', help='Do not run the semantic search engine')
    parser.add_argument('--debug', action='store_true', help='Run the server in the debug mode')
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
            set_father_webhook(BASE_URL)

            scheduler = BackgroundScheduler()
            scheduler.add_job(do_wakeup, 'cron', hour=17, minute=00)  # I hope this is UTC
            scheduler.add_job(do_frequent_wakeup, 'interval', minutes=10)
            scheduler.start()

        if not args.nosearch:
            ft = load_ft()
            searchers = {
                space: ProfileSearcher(w2v=ft, records=list(get_pb_dict(space=space).values()))
                for space in MULTIVERSE.spaces_dict
            }
            app.profile_searcher = searchers
        app.database = DATABASE
        app.register_blueprint(itinder_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(father_bot_bp)
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), debug=args.debug)


if __name__ == '__main__':
    run_bot_and_book()
