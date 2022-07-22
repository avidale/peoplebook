import pymongo
from peoplebook.models import User

import logging
import config as cfg

from flask import render_template, abort, request, redirect, url_for
from flask_login import login_required, login_user, logout_user, current_user

from peoplebook.web_flask import app, get_users, get_profiles_for_event, get_current_username, check_space, \
    get_default_space
from peoplebook.web_flask import mongo_events, mongo_participations, mongo_membership, mongo_peoplebook, mongo_db
from peoplebook.web_flask import DATABASE
from peoplebook.web_flask import history_configs


from utils.spaces import get_space_config

logger = logging.getLogger(__name__)

SPACE_NOT_FOUND = 'Сообщество не найдено', 404


@app.route('/about')
def about_peoplebook():
    return render_template('about.html')


@app.route('/')  # todo: stop serving the links without space
@app.route('/<space>')
@app.route('/<space>/')
@app.route('/', subdomain='<space>')
@login_required
def home(space=None):
    if space is None:
        default_space, user_spaces = get_default_space()
        if default_space:
            space = default_space.key
        elif user_spaces:
            return render_template(
                'spaces_choice.html',
                spaces_to_names={s.key: s.title for s in user_spaces},
                user=current_user,
            )
    if space is None:
        space = cfg.DEFAULT_SPACE
    if not check_space(space):
        return redirect(url_for('about_peoplebook'))
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)

    # if the space supports events, show the peoplebook for the last non-empty event
    all_events = mongo_events.find({'space': space}).sort('date', pymongo.DESCENDING)
    for event in all_events:
        who_comes = list(mongo_participations.find({'code': event['code'], 'status': 'ACCEPT', 'space': space}))
        if len(who_comes) >= 3:  # one participant is enough to show the event - but this may be revised
            return peoplebook_for_event(event_code=event['code'], space=space)

    # if there is a special "current" event, show it (DEPRECATED)
    history_config = history_configs.get(space_cfg.key)
    if history_config and history_config.get('current'):
        return render_template(
            'peoplebook.html',
            period=history_config['current'],
            period_text=history_config['current_text'],
            space_cfg=space_cfg,
            user=current_user,
        )

    # otherwise, show the fullest peoplebook
    if space_cfg.web_show_pb_all:
        return peoplebook_for_all_members_and_guests(space=space)
    else:
        return peoplebook_for_community(space=space)


@app.route('/history/<period>')
@app.route('/<space>/history/<period>')
@app.route('/history/<period>', subdomain='<space>')
@login_required
def history(period, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    history_config = history_configs.get(space)

    if history_config and period in history_config['history']:
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
@app.route('/event/<event_code>', subdomain='<space>')
@login_required
def peoplebook_for_event(event_code, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    the_event = mongo_events.find_one({'code': event_code, 'space': space_cfg.key})
    if the_event is None:
        return 'Такого события не найдено!'
    profiles = get_profiles_for_event(event_code, space_id=space_cfg.key)
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
@app.route('/members', subdomain='<space>')
@login_required
def peoplebook_for_all_members(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    raw_profiles = list(mongo_membership.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'tg_id',
                'foreignField': 'tg_id',
                'as': 'profiles'
            }
        }, {
            '$match': {'is_member': True, 'space': space_cfg.key}
        }
    ]))
    profiles = [
        p for rp in raw_profiles for p in rp.get('profiles', [])
        if p.get('space') == space_cfg.key and rp.get('tg_id')
    ]
    return render_template(
        'backend_peoplebook.html',
        title='Члены клуба {}'.format(space_cfg.title),
        profiles=profiles,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/community')
@app.route('/<space>/community')
@app.route('/community', subdomain='<space>')
@login_required
def peoplebook_for_community(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    raw_profiles = list(mongo_membership.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'tg_id',
                'foreignField': 'tg_id',
                'as': 'profiles'
            }
        }, {
            '$match': {'space': space_cfg.key}
        }
    ]))
    profiles = [
        p for rp in raw_profiles for p in rp.get('profiles', [])
        if p.get('space') == space_cfg.key and rp.get('tg_id') and (rp.get('is_member') or rp.get('is_friend'))
    ]
    return render_template(
        'backend_peoplebook.html',
        title='Члены Сообщества {}'.format(space_cfg.title),
        profiles=profiles,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/members_and_guests')
@app.route('/<space>/members_and_guests')
@app.route('/all')
@app.route('/<space>/all')
@app.route('/all', subdomain='<space>')
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
                    'localField': 'tg_id',
                    'foreignField': 'tg_id',
                    'as': 'profiles'
                },
            },
            {
                '$match': {'space': space_cfg.key},
            },
        ]))
        profiles = [
            p for rp in raw_profiles for p in rp.get('profiles', [])
            if p.get('space') == space and rp.get('tg_id')
        ]
    else:
        profiles = list(mongo_peoplebook.find({'space': space}))

    return render_template(
        'backend_peoplebook.html',
        title='Сообщество и гости {}'.format(space_cfg.title),
        profiles=profiles,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/person/<username>')
@app.route('/<space>/person/<username>')
@app.route('/person/<username>', subdomain='<space>')
@login_required
def peoplebook_for_person(username, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)
    if username and username.isnumeric():
        tg_id = int(username)
    else:
        tg_id = None
    the_profile = DATABASE.find_peoplebook_profile(
        username=username, tg_id=tg_id, space_name=space_cfg.key
    )
    if the_profile is None:
        return 'Такого профиля в пиплбуке не найдено!\n' \
               'Можно написать https://t.me/{} и предложить заполнить его!'.format(username)
    return render_template(
        'single_person.html',
        profile=the_profile,
        space_cfg=space_cfg,
        user=current_user,
    )


@app.route('/me')
@app.route('/<space>/me')
@app.route('/me', subdomain='<space>')
@login_required
def my_profile(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    return peoplebook_for_person(
        username=get_current_username(),
        space=space,
    )


# вход по ссылке
@app.route("/login_link")
@app.route('/login_link', subdomain='<space>')
def login_link(space=None):
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
@app.route('/login', subdomain='<space>')
def login():
    if not current_user.is_authenticated:
        return render_template('login.html')
    else:
        return redirect(request.args.get('next'))


@app.route("/logout")
@app.route('/logout', subdomain='<space>')
def logout():
    logout_user()
    return redirect(request.referrer)
