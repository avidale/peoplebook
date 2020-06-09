import os
import telebot

from utils.multiverse import ALL_CONTENT_TYPES
from utils.photo import load_photo_from_message, load_user_profile_photo

bot = telebot.TeleBot(os.environ['TOKEN'])


@bot.message_handler(func=lambda message: True, content_types=ALL_CONTENT_TYPES)
def process_message(message: telebot.types.Message):
    bot.reply_to(message, text='ok')
    print(message.chat)
    print(message.from_user)
    print(load_user_profile_photo(user_id=message.from_user.id, bot=bot))
    print('message photo', load_photo_from_message(message=message, bot=bot))


bot.polling()
