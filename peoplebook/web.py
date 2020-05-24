import pymongo
from peoplebook.models import User

import config as cfg

from flask import render_template, abort, request, redirect
from flask_login import login_required, login_user, logout_user, current_user

from peoplebook.web_flask import app, get_users, get_profiles_for_event, get_current_username
from peoplebook.web_flask import mongo_events, mongo_participations, mongo_membership, mongo_peoplebook
from peoplebook.web_flask import history_config

from peoplebook.web_itinder import get_pb_dict, searcher


@app.route('/')
@login_required
def home():
    all_events = mongo_events.find().sort('date', pymongo.DESCENDING)
    for event in all_events:
        who_comes = list(mongo_participations.find({'code': event['code'], 'status': 'ACCEPT'}))
        if len(who_comes) >= 1:  # one participant is enough to show the event - but this may be revised
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
    profiles = get_profiles_for_event(event_code)
    # profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
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
def peoplebook_for_person(username, space=cfg.DEFAULT_SPACE):
    the_profile = mongo_peoplebook.find_one({'username': username, 'space': space})
    if the_profile is None:
        return 'Такого профиля не найдено!'
    return render_template('single_person.html', profile=the_profile)


@app.route('/me')
@login_required
def my_profile():
    return peoplebook_for_person(username=get_current_username())


@app.route('/search', methods=['POST', 'GET'])
@login_required
def search():
    if request.form and request.form.get('req_text'):
        req_text = request.form['req_text']
        results = searcher.lookup(req_text)
        pb_dict = get_pb_dict()
        for r in results:
            r['profile'] = pb_dict.get(r['username'], {})
    else:
        req_text = None
        results = None
    return render_template(
        'search.html',
        req_text=req_text,
        results=results,
        title='',
    )


# вход по ссылке
@app.route("/login_link")
def login_link():
    try:
        user_object = get_users()[1][request.args.get('bot_info')]
    except KeyError:
        return 'Создайте профиль в пиплбуке'

    user = User(id=user_object['tg_id'], data=user_object)
    login_user(user, remember=True)
    if request.args.get('next'):
        return redirect(request.args.get('next'))
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
