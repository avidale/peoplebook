import random
import datetime

import config as cfg

from peoplebook.profile_searcher import ProfileSearcher
from similarity import basic_nlu, similarity_tools

from flask import render_template, request, Blueprint, current_app
from flask_login import login_required, current_user

from peoplebook.web_flask import mongo_peoplebook, get_current_username

from peoplebook.web import SPACE_NOT_FOUND, get_space_config, mongo_db, check_space


itinder_bp = Blueprint('itinder', __name__)


def get_pb_dict(space=cfg.DEFAULT_SPACE):
    # todo: start using tg_id instead
    return {p['username']: p for p in mongo_peoplebook.find({'space': space}) if p['username']}


@itinder_bp.route('/similarity', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/similarity', methods=['POST', 'GET'])
@login_required
def similarity_page(one=None, another=None, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)

    if not hasattr(current_app, 'profile_searcher'):
        return 'Feature not supported', 400
    ps: ProfileSearcher = current_app.profile_searcher.get(space)
    if not ps:
        return 'Feature not supported', 400
    pb_list = sorted(
        list(get_pb_dict(space=space).values()),
        key=lambda x: '{}_{}'.format(x.get('first_name'), x.get('last_name'))
    )
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
                score = ps.matcher.compare_two(c1, c2)
                results.append({'score': round(score, 2), 'first': text1[i], 'second': text2[j]})
        results = similarity_tools.deduplicate(results, threshold=0.3)  # 0.05 for tfidf
    else:
        if not u1:
            u1 = random.choice(pb_list)['username']
        if not u2:
            u2 = random.choice(pb_list)['username']
        results = None
    return render_template(
        'similarity.html',
        persons=pb_list,
        results=results,
        first_default=u1,
        second_default=u2,
        first_person=p1,
        second_person=p2,
        space=space,
        space_cfg=space_cfg,
    )


@itinder_bp.route('/similarity/<one>/<another>', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/similarity/<one>/<another>', methods=['POST', 'GET'])
@login_required
def similarity_page_parametrized(one, another, space=cfg.DEFAULT_SPACE):
    return similarity_page(one=one, another=another, space=space)


@itinder_bp.route('/itinder_search', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/itinder_search', methods=['POST', 'GET'])
@login_required
def search_page(text=None, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)

    if not hasattr(current_app, 'profile_searcher'):
        return 'Feature not supported', 400
    ps: ProfileSearcher = current_app.profile_searcher.get(space)
    if not ps:
        return 'Feature not supported', 400

    if request.form and request.form.get('req_text'):
        req_text = request.form['req_text']
        results = ps.lookup(req_text)
        pb_dict = get_pb_dict(space=space)
        for r in results:
            r['profile'] = pb_dict.get(r['username'], {})
    else:
        req_text = None
        results = None
    return render_template(
        'itinder_search.html',
        req_text=req_text,
        results=results,
        space=space,
        space_cfg=space_cfg,
    )


@itinder_bp.route('/itinder')
@itinder_bp.route('/<space>/itinder')
@login_required
def itinder(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)

    return render_template(
        'itinder.html',
        space=space,
        space_cfg=space_cfg,
    )


@itinder_bp.route('/most_similar', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/most_similar', methods=['POST', 'GET'])
@login_required
def most_similar_page(username=None, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)

    if not hasattr(current_app, 'profile_searcher'):
        return 'Feature not supported', 400
    ps: ProfileSearcher = current_app.profile_searcher.get(space)
    if not ps:
        return 'Feature not supported', 400

    if username is None:
        username = get_current_username()
    if username not in ps.owner2texts:
        return 'Your peoplebook profile was not found', 404
    rating = similarity_tools.rank_similarities(one=username, owner2texts=ps.owner2texts, matcher=ps.matcher)
    top = rating.head(10).to_dict('records')
    pb_dict = get_pb_dict(space=space)
    for result in top:
        result['other_profile'] = pb_dict.get(result['who'])
    profile = pb_dict.get(username)
    return render_template(
        'most_similar.html',
        results=top,
        profile=profile,
        space=space,
        space_cfg=space_cfg,
    )


@itinder_bp.route('/most_similar/<username>', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/most_similar/<username>', methods=['POST', 'GET'])
def most_similar_page_parametrized(username, space=cfg.DEFAULT_SPACE):
    return most_similar_page(username=username, space=space)


@itinder_bp.route('/least_similar', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/least_similar', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/least_similar/<username>', methods=['POST', 'GET'])
@login_required
def least_similar_page(username=None, space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)

    if not hasattr(current_app, 'profile_searcher'):
        return 'Feature not supported', 400
    ps: ProfileSearcher = current_app.profile_searcher.get(space)
    if not ps:
        return 'Feature not supported', 400

    if username is None:
        username = get_current_username()

    top = ps.get_top_dissimilar(username=username)

    pb_dict = get_pb_dict(space=space)
    for result in top:
        result['other_profile'] = pb_dict.get(result['who'])
    profile = pb_dict.get(username)
    return render_template(
        'least_similar.html',
        results=top,
        profile=profile,
        space=space,
        space_cfg=space_cfg,
    )


@itinder_bp.route('/least_similar/<username>', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/least_similar/<username>', methods=['POST', 'GET'])
def least_similar_page_parametrized(username, space=cfg.DEFAULT_SPACE):
    return least_similar_page(username=username, space=space)


@itinder_bp.route('/search', methods=['POST', 'GET'])
@itinder_bp.route('/<space>/search', methods=['POST', 'GET'])
@login_required
def search(space=cfg.DEFAULT_SPACE):
    if not check_space(space):
        return SPACE_NOT_FOUND
    space_cfg = get_space_config(mongo_db=mongo_db, space_name=space)

    if not hasattr(current_app, 'profile_searcher'):
        return 'Feature not supported', 400
    ps: ProfileSearcher = current_app.profile_searcher.get(space)
    if not ps:
        return 'Feature not supported', 400

    if not check_space(space):
        return SPACE_NOT_FOUND
    if request.form and request.form.get('req_text'):
        req_text = request.form['req_text']
        req_logs = mongo_db.get_collection('search_requests')
        req_logs.insert_one({
            'text': req_text,
            'space': space,
            'time': datetime.datetime.now(),
            'username': get_current_username(),
        })
        results = ps.lookup(req_text)
        pb_dict = get_pb_dict(space=space)
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
        space_cfg=space_cfg,
        user=current_user,
        space=space,
    )
