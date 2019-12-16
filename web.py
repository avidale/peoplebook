import json
import os
import pymongo
import random
from autolink import linkify
from models import User
import hashlib

from flask import Flask, render_template, abort, request, redirect
from flask_login import LoginManager, login_required, login_user, logout_user, current_user

from similarity import matchers, basic_nlu

app = Flask(__name__)
app.secret_key = os.environ.get('APP_KEY')

# flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = None

with open('history_config.json', 'r', encoding='utf-8') as f:
    history_config = json.load(f)

MONGO_URL = os.environ.get('MONGODB_URI')
mongo_client = pymongo.MongoClient(MONGO_URL)
mongo_db = mongo_client.get_default_database()
mongo_events = mongo_db.get_collection('events')
mongo_participations = mongo_db.get_collection('event_participations')
mongo_peoplebook = mongo_db.get_collection('peoplebook')
mongo_membership = mongo_db.get_collection('membership')
mongo_peoplebook_users = mongo_db.get_collection('users')

user_list = [document['tg_id'] for document in mongo_peoplebook_users.find({})]
users = [User(document) for document in user_list]
users_hshd_dict = {hashlib.md5((str(x) +
                                os.environ.get('login_salt')).encode('utf-8')).hexdigest(): x for x in user_list}


@app.template_filter('linkify_filter')
def linkify_filter(s):
    return linkify(s)


MEANINGFUL_FIELDS = {'first_name', 'last_name', 'photo', 'activity', 'topics', 'contacts'}


@app.template_filter('preprocess_profiles')
def preprocess_profiles(profiles):
    # we omit the profiles with too few fields set
    filtered = [p for p in profiles if len(set(p.keys()).intersection(MEANINGFUL_FIELDS)) >= 3]
    random.shuffle(filtered)
    return filtered


@app.route('/')
@login_required
def home():
    all_events = mongo_events.find().sort('date', pymongo.DESCENDING)
    for event in all_events:
        who_comes = list(mongo_participations.find({'code': event['code'], 'status': 'ACCEPT'}))
        if len(who_comes) >= 1: # one participant is enough to show the event - but this may be revised
            return peoplebook_for_event(event['code'])
    return render_template(
        'peoplebook.html', period=history_config['current'], period_text=history_config['current_text']
    )


@app.route('/history/<period>')
@login_required
def history(period):
    if period in history_config['history']:
        return render_template('peoplebook.html', period=period, period_text=history_config['history'][period])
    abort(404)


@app.route('/event/<event_code>')
@login_required
def peoplebook_for_event(event_code):
    the_event = mongo_events.find_one({'code': event_code})
    if the_event is None:
        return 'Такого события не найдено!'
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
    return render_template(
        'backend_peoplebook.html',
        title=the_event.get('title', 'Пиплбук встречи'),
        profiles=profiles
    )


@app.route('/members')
@login_required
def peoplebook_for_all_members():
    raw_profiles = list(mongo_membership.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'username',
                'foreignField': 'username',
                'as': 'profiles'
            }
        }, {
            '$match': {'is_member': True}
        }
    ]))
    profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
    return render_template(
        'backend_peoplebook.html',
        title='Члены клуба Каппа Веди',
        profiles=profiles
    )


@app.route('/members_and_guests')
@app.route('/all')
@login_required
def peoplebook_for_all_members_and_guests():
    raw_profiles = list(mongo_membership.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'username',
                'foreignField': 'username',
                'as': 'profiles'
            }
        }
    ]))
    profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
    return render_template(
        'backend_peoplebook.html',
        title='Сообщество Каппа Веди',
        profiles=profiles
    )


@app.route('/person/<username>')
@login_required
def peoplebook_for_person(username):
    the_profile = mongo_peoplebook.find_one({'username': username})
    if the_profile is None:
        return 'Такого профиля не найдено!'
    return render_template('single_person.html', profile=the_profile)


# вход по ссылке
@app.route("/login_link")
def login_link():
    try:
        user_id = get_users()[1][request.args.get('bot_info')]
    except KeyError:
        return 'Создайте профиль пиплбуке'

    user = User(user_id)
    login_user(user, remember=True)
    if request.args.get('next'):
        return redirect('{}?bot_info={}'.format(request.args.get('next'), request.args.get('bot_info')))
    else:
        return 'Вход выполнен'


# заглушка для неавторизавнных пользователей
@app.route("/login")
def login():
    if not current_user.is_authenticated:
        return render_template('login.html')
    else:
        return redirect(request.args.get('next'))


@app.route("/logout")
def logout():
    logout_user()
    return redirect(request.referrer)


# используется для перезаписи объекта идентификатора пользователя сессии
@login_manager.user_loader
def load_user(userid):
    return User(userid)


def get_users():
    user_list = [document['tg_id'] for document in mongo_peoplebook_users.find({})]
    global users
    users = [User(document) for document in user_list]
    users_hshd_dict = {hashlib.md5((str(x) +
                                    os.environ.get('login_salt')).encode('utf-8')).hexdigest(): x for x in user_list}
    return user_list, users_hshd_dict


pb_list = list(mongo_peoplebook.find({}))
matcher = matchers.TFIDFMatcher(text_normalization='fast_lemmatize_filter_pos')
texts = [p.get('activity', '') + '\n' + p.get('topics', '') for p in pb_list]
texts = [t for text in texts for t in basic_nlu.split(text)]
matcher.fit(texts, ['' for _ in texts])


def deduplicate(facts):
    lhs = set()
    rhs = set()
    facts = sorted(facts, key=lambda x: x['score'], reverse=True)
    result = []
    for fact in facts:
        if fact['first'] not in lhs and fact['second'] not in rhs:
            result.append(fact)
        lhs.add(fact['first'])
        rhs.add(fact['second'])
    return result


@app.route('/similarity', methods=['POST', 'GET'])
#@login_required
def similarity_page(one=None, another=None):
    pb_list = list(mongo_peoplebook.find({}))
    pb_set = {p['username'] for p in pb_list if p['username']}
    p1 = {}
    p2 = {}
    u1, u2 = None, None
    if request.form and request.form.get('first') and request.form.get('second'):
        u1 = request.form['first']
        u2 = request.form['second']
    if not u1 and one and one in pb_set:
        u1 = one
    if not u2 and another and another in pb_set:
        u2 = another
    if u1 and u2:
        for u in pb_list:
            if u['username'] == u1:
                p1 = u
            if u['username'] == u2:
                p2 = u

        text1 = basic_nlu.split(p1.get('topics', '')) + basic_nlu.split(p1.get('activity', ''))
        text2 = basic_nlu.split(p2.get('topics', '')) + basic_nlu.split(p2.get('activity', ''))

        results = []
        for i, c1 in enumerate(text1):
            for j, c2 in enumerate(text2):
                score = matcher.compare_two(c1, c2)
                if score > 0.05:
                    results.append({'score': round(score, 2), 'first': text1[i], 'second': text2[j]})
        results = deduplicate(results)
    else:
        if not u1:
            u1 = random.choice(pb_list)['username']
        if not u2:
            u2 = random.choice(pb_list)['username']
        results = None
    return render_template(
        'similarity.html',
        persons = pb_list,
        results=results,
        first_default=u1,
        second_default=u2,
        first_person=p1,
        second_person=p2,
    )


@app.route('/similarity/<one>/<another>', methods=['POST', 'GET'])
#@login_required
def similarity_page_parametrized(one, another):
    return similarity_page(one=one, another=another)

get_users()
