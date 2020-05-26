import os
import pymongo
import random
from autolink import linkify
from peoplebook.models import User
import hashlib

from flask import Flask
from flask_login import LoginManager, current_user

app = Flask(__name__)
app.secret_key = os.environ.get('APP_KEY')

# flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = None


history_config = {
  "current": "apr2019",
  "current_text": "27 апреля 2019",
  "history": {
    "apr2019": "27 апреля 2019",
    "april2019": "27 апреля 2019",
    "march2019": "30 марта 2019",
    "feb2019": "2 марта 2019"
  }
}


MONGO_URL = os.environ.get('MONGODB_URI')
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


def get_profiles_for_event(event_code):
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
    profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
    return profiles


@app.template_filter('linkify_filter')
def linkify_filter(s):
    return linkify(s)


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
