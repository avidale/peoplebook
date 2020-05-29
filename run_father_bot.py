from fatherbot.main import father_bot, Flask, father_bot_bp

if __name__ == '__main__':
    app = Flask(__name__)
    app.register_blueprint(father_bot_bp)
    print('running the bot in the polling mode')
    father_bot.polling()
