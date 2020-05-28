import pymongo
from peoplebook.models import User

import config as cfg

from flask import render_template, abort, request, redirect, url_for, current_app
from flask_login import login_required, login_user, logout_user, current_user

from peoplebook.web_flask import app, get_users, get_profiles_for_event, get_current_username
from peoplebook.web_flask import mongo_events, mongo_participations, mongo_membership, mongo_peoplebook, mongo_db
from peoplebook.web_flask import history_config

from peoplebook.web_itinder import get_pb_dict, searcher

from utils.database import Database
from utils.spaces import get_space_config

SPACE_NOT_FOUND = 'Сообщество не найдено', 404


def check_space(space_name):
    """ Check whether the current user is a member of the space """
    db: Database = current_app.database
    username = get_current_username()
    if not username:
        return False
    uo = {'username': username, 'space': space_name}
    if not db.is_at_least_guest(uo):
        return False
    return True


@app.route('/')
@app.route('/<space>')
@login_required
def home(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    all_events = mongo_events.find({'space': space}).sort('date', pymongo.DESCENDING)
    for event in all_events:
        who_comes = list(mongo_participations.find({'code': event['code'], 'status': 'ACCEPT', 'space': space}))
        if len(who_comes) >= 1:  # one participant is enough to show the event - but this may be revised
            return peoplebook_for_event(event['code'])
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    return render_template(
        'peoplebook.html',
        period=history_config['current'],
        period_text=history_config['current_text'],
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/history/<period>')
@app.route('/<space>/history/<period>')
@login_required
def history(period, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    if period in history_config['history']:
        return render_template(
            'peoplebook.html',
            period=period,
            period_text=history_config['history'][period],
            space_cfg=space_cfg,
            user=current_user,
        )
    abort(404)


@app.route('/event/<event_code>')
@app.route('/<space>/event/<event_code>')
@login_required
def peoplebook_for_event(event_code, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    the_event = mongo_events.find_one({'code': event_code, 'space': space_cfg.key})
    if the_event is None:
        return 'Такого события не найдено!'
    profiles = get_profiles_for_event(event_code)
    # profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
    return render_template(
        'backend_peoplebook.html',
        title=the_event.get('title', 'Пиплбук встречи'),
        profiles=profiles,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/members')
@app.route('/<space>/members')
@login_required
def peoplebook_for_all_members(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
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
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    return render_template(
        'backend_peoplebook.html',
        title='Члены клуба {}'.format(space_cfg.title),
        profiles=profiles,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/members_and_guests')
@app.route('/<space>/members_and_guests')
@app.route('/all')
@app.route('/<space>/all')
def peoplebook_for_all_members_and_guests(space=cfg.DEFAULT_SPACE):
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    if not space_cfg:
        return SPACE_NOT_FOUND
    if not space_cfg.peoplebook_is_public and not check_space(space):
        return SPACE_NOT_FOUND
    if not current_user.is_authenticated and not space_cfg.peoplebook_is_public:
        return redirect(url_for('login', next=request.path))
    if space == cfg.DEFAULT_SPACE:
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
        profiles = [p for rp in raw_profiles for p in rp.get('profiles', []) if p.get('space') == space]
    else:
        profiles = list(mongo_peoplebook.find({'space': space}))

    return render_template(
        'backend_peoplebook.html',
        title='Сообщество {}'.format(space_cfg.title),
        profiles=profiles,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/person/<username>')
@app.route('/<space>/person/<username>')
@login_required
def peoplebook_for_person(username, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    the_profile = mongo_peoplebook.find_one({'username': username, 'space': space_cfg.key})
    if the_profile is None:
        return 'Такого профиля не найдено!'
    return render_template(
        'single_person.html',
        profile=the_profile,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/me')
@app.route('/<space>/me')
@login_required
def my_profile(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    return peoplebook_for_person(
        username=get_current_username(),
        space=space,
    )


@app.route('/search', methods=['POST', 'GET'])
@app.route('/<space>/search', methods=['POST', 'GET'])
@login_required
def search(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    if request.form and request.form.get('req_text'):
        req_text = request.form['req_text']
        results = searcher.lookup(req_text)
        pb_dict = get_pb_dict()
        for r in results:
            r['profile'] = pb_dict.get(r['username'], {})
    else:
        req_text = None
        results = None
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    return render_template(
        'search.html',
        req_text=req_text,
        results=results,
        title='',
        space_cfg=space_cfg,
        user=current_user,
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
