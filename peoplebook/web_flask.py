import os
import pymongo
import random
from autolink import linkify

from config import DEFAULT_SPACE
from peoplebook.models import User
import hashlib

from flask import Flask
from flask_login import LoginManager, current_user

from flask_wtf import CSRFProtect

from utils.global_database import DATABASE, MONGO_URL


app = Flask(__name__)
app.secret_key = os.environ.get('APP_KEY')

# csrf for forms
csrfp = CSRFProtect()
# csrfp.init_app(app)  # we turn it off because it interferes with Telegram API

# flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = None


history_configs = {
    DEFAULT_SPACE: {
      "current": "apr2019",
      "current_text": "27 апреля 2019",
      "history": {
        "apr2019": "27 апреля 2019",
        "april2019": "27 апреля 2019",
        "march2019": "30 марта 2019",
        "feb2019": "2 марта 2019"
      }
    }
}


mongo_client = pymongo.MongoClient(MONGO_URL)
mongo_db = mongo_client.get_default_database()
mongo_events = mongo_db.get_collection('events')
mongo_participations = mongo_db.get_collection('event_participations')
mongo_peoplebook = mongo_db.get_collection('peoplebook')
mongo_membership = mongo_db.get_collection('membership')
mongo_peoplebook_users = mongo_db.get_collection('users')

users = []  # it will be filled in get_users() function

MEANINGFUL_FIELDS = {'first_name', 'last_name', 'photo', 'activity', 'topics', 'contacts'}


def get_current_username():
    if not hasattr(current_user, 'id'):
        return None
    for u in users:
        if str(u.id) == str(current_user.id):
            return u.username


def get_profiles_for_event(event_code, space_id):
    raw_profiles = list(mongo_participations.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'username',
                'foreignField': 'username',
                'as': 'profiles'
            }
        }, {
            '$match': {'code': event_code, 'status': 'ACCEPT'}
        }
    ]))
    profiles = [p for rp in raw_profiles for p in rp.get('profiles', []) if p.get('space') == space_id]

    # add more profiles by matching them by tg_id
    tg_ids = {p.get('tg_id') for p in profiles if p.get('tg_id') is not None}
    more_profiles = list(mongo_participations.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'tg_id',
                'foreignField': 'tg_id',
                'as': 'profiles'
            }
        }, {
            '$match': {'code': event_code, 'status': 'ACCEPT'}
        }
    ]))
    for rp in more_profiles:
        for p in rp.get('profiles', []):
            if p.get('space') == space_id:
                if p.get('tg_id') and p['tg_id'] not in tg_ids:
                    profiles.append(p)
    return profiles


@app.template_filter('linkify_filter')
def linkify_filter(s):
    return linkify(s)


@app.context_processor
def add_nonempty_text():
    def is_nonempty_text(text, min_len=2) -> bool:
        if not text:
            return False
        text = text.strip().lower()
        if text in {'-', 'нет', '...'}:
            return False
        if text.startswith('/set_pb'):
            return False
        return len(text) >= min_len
    return dict(is_nonempty_text=is_nonempty_text)


@app.template_filter('preprocess_profiles')
def preprocess_profiles(profiles):
    # we omit the profiles with too few fields set
    filtered = [p for p in profiles if len(set(p.keys()).intersection(MEANINGFUL_FIELDS)) >= 3]
    random.shuffle(filtered)
    return filtered


# используется для перезаписи объекта идентификатора пользователя сессии
@login_manager.user_loader
def load_user(userid):
    # todo: make sure that profile details are preserved
    return User(userid)


def get_users():
    user_list = [document for document in mongo_peoplebook_users.find({})]
    global users
    users = [User(document['tg_id'], username=document.get('username'), data=document) for document in user_list]
    users_hshd_dict = {hashlib.md5((str(x['tg_id']) +
                                    os.environ.get('login_salt')).encode('utf-8')).hexdigest(): x for x in user_list}
    return user_list, users_hshd_dict


get_users()
