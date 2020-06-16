from telebot.types import Message
from telebot import TeleBot
from utils.database import Database, get_or_insert_user
from utils.spaces import SpaceConfig

from utils.photo import profile_photo_url_from_message

from similarity.parse_whois import WHOIS_SEGMENTER_MODEL, segmentize


def add_peoplebook_from_whois(
        message: Message,
        database: Database,
        space_cfg: SpaceConfig,
        bot: TeleBot,
        rewrite=False,
):
    # todo: find peoplebook proofile by looking at the user_object (username or user id)
    uo = get_or_insert_user(space_name=space_cfg.key, database=database, tg_user=message.from_user)
    fltr = {'username': message.from_user.username, 'space': space_cfg.key}
    existing_page = database.mongo_peoplebook.find_one(fltr)
    if existing_page and not rewrite:
        print('the peoplebook page already exists, not rewriting it')
        return
    if bot:
        user_photo = profile_photo_url_from_message(message=message, bot=bot)
    else:
        user_photo = None
    parsed = parse_whois_text(message.text)
    database.mongo_peoplebook.update_one(
        fltr,
        {'$set': {
            'first_name': uo.get('first_name') or uo.get('username') or parsed['first_name'],
            'last_name': uo.get('last_name') or parsed['last_name'],
            'activity': parsed['activity'],
            'topics': parsed['topics'],
            'photo': user_photo,
            'contacts': parsed['contacts'],
        }},
        upsert=True
    )


def parse_whois_text(text):
    if not WHOIS_SEGMENTER_MODEL:
        return {
            'first_name': 'Anonymous',
            'last_name': 'Anonymous',
            'activity': text,
            'topics': '',
            'contacts': '',
        }
    return segmentize(model=WHOIS_SEGMENTER_MODEL, text=text)


def validate_whois_text(text):
    return len(text) >= 20 and len(set(text)) >= 10
