import argparse
import os

from peoplebot.main import bot_app, bot, web_hook
from peoplebook.web import app


def run_bot_and_book():
    parser = argparse.ArgumentParser(description='Run the bot')
    parser.add_argument('--poll', action='store_true')
    parser.add_argument('--nobot', action='store_true')
    args = parser.parse_args()
    if args.poll:
        bot.remove_webhook()
        bot.polling()
    else:
        if not args.nobot:
            web_hook()
        app.register_blueprint(bot_app)
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    run_bot_and_book()
