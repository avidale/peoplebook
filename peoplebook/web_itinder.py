import gensim
import numpy as np
import pandas as pd
import pickle
import random
import time

from tqdm.auto import tqdm
from collections import defaultdict

import config as cfg

from similarity import matchers, basic_nlu, similarity_tools
from similarity.semantic_search import SemanticSearcher, get_searcher_data, extract_all_chunks

from flask import render_template, request
from flask_login import login_required

from peoplebook.web_flask import app, get_profiles_for_event
from peoplebook.web_flask import mongo_peoplebook, get_current_username

CURRENT_EVENT = 'newyear2019'
pb_list = list(mongo_peoplebook.find({'space': cfg.DEFAULT_SPACE}))  # get_profiles_for_event(CURRENT_EVENT)


with open('similarity/fasttext_extract.pkl', 'rb') as f:
    main_w2v = pickle.load(f)

ft_small = gensim.models.fasttext.FastTextKeyedVectors.load(
    'similarity/araneum_new_compressed.model'
)

w2v = similarity_tools.FallbackW2V(main_w2v, ft_small)


weighter = basic_nlu.Weighter(custom_weights=basic_nlu.NOISE_WORDS)
matcher = matchers.WMDMatcher(text_normalization='fast_lemmatize_filter_pos', w2v=w2v, weighter=weighter)
texts = [p.get('activity', '') + '\n' + p.get('topics', '') for p in pb_list]
texts = [t for text in texts for t in basic_nlu.split(text)]
matcher.fit(texts, ['' for _ in texts])


w2vmatcher = matchers.W2VMatcher(w2v=w2v, weighter=weighter, text_normalization='fast_lemmatize_filter_pos')


def text2vec(t):
    v = w2vmatcher.preprocess(t)
    if v is None:
        return np.zeros(300)
    return v


def get_pb_dict():
    #  return {p['username']: p for p in get_profiles_for_event(CURRENT_EVENT) if p['username']}
    return {p['username']: p for p in mongo_peoplebook.find({'space': cfg.DEFAULT_SPACE}) if p['username']}


# searcher
t = time.time()
print('start getting searcher data')
df = pd.DataFrame(list(get_pb_dict().values()))
df.topics.fillna('', inplace=True)
df.activity.fillna('', inplace=True)
parts, owners, normals = extract_all_chunks(df)
searcher_data = get_searcher_data(parts, owners, vectorizer=text2vec)
print('got searcher data, spent {}'.format(time.time() - t))

searcher = SemanticSearcher()
searcher.setup(**searcher_data, vectorizer=text2vec)

# most similar people
# todo: make it updateable
preprocessed = [matcher.preprocess(p) for p in tqdm(searcher_data['texts'])]
owner2texts = defaultdict(list)
for prep, owner, text in zip(preprocessed, searcher_data['owners'], searcher_data['texts']):
    owner2texts[owner].append((text, prep))


# least similar people
df['fulltext'] = ' '
for i, row in df.iterrows():
    df.loc[i, 'fulltext'] = '{} {}\n{}\n{}'.format(row.first_name, row.last_name, row.activity, row.topics)
new_matcher = matchers.W2VMatcher(w2v=w2v, weighter=weighter)
new_matcher.fit(df.fulltext.tolist(), df.username.tolist())
user_vecs = np.stack(new_matcher._texts)
sims = np.dot(user_vecs, user_vecs.T)
dissimilar_pairs = similarity_tools.assign_pairs(sims, n_pairs=20)


@app.route('/similarity', methods=['POST', 'GET'])
@login_required
def similarity_page(one=None, another=None):
    pb_list = sorted(
        get_profiles_for_event(CURRENT_EVENT),
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
                score = matcher.compare_two(c1, c2)
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
    )


@app.route('/similarity/<one>/<another>', methods=['POST', 'GET'])
@login_required
def similarity_page_parametrized(one, another):
    return similarity_page(one=one, another=another)


@app.route('/itinder_search', methods=['POST', 'GET'])
@login_required
def search_page(text=None):
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
        'itinder_search.html',
        req_text=req_text,
        results=results,
    )


@app.route('/itinder')
@login_required
def itinder():
    return render_template('itinder.html')


@app.route('/most_similar', methods=['POST', 'GET'])
@login_required
def most_similar_page(username=None):
    if username is None:
        username = get_current_username()
    rating = similarity_tools.rank_similarities(one=username, owner2texts=owner2texts, matcher=matcher)
    top = rating.head(10).to_dict('records')
    pb_dict = get_pb_dict()
    for result in top:
        result['other_profile'] = pb_dict.get(result['who'])
    profile = pb_dict.get(username)
    return render_template('most_similar.html', results=top, profile=profile)


@app.route('/most_similar/<username>', methods=['POST', 'GET'])
def most_similar_page_parametrized(username):
    return most_similar_page(username=username)


@app.route('/least_similar', methods=['POST', 'GET'])
@login_required
def least_similar_page(username=None):
    if username is None:
        username = get_current_username()

    for user_idx, un in enumerate(df.username):
        if un == username:
            break
    who = dissimilar_pairs[user_idx]
    how = sims[user_idx, who]
    top = [{
        'username': username,
        'score': score,
        'who': df.username.iloc[other_id],
    } for score, other_id in zip(how, who)]

    pb_dict = get_pb_dict()
    for result in top:
        result['other_profile'] = pb_dict.get(result['who'])
    profile = pb_dict.get(username)
    return render_template('least_similar.html', results=top, profile=profile)


@app.route('/least_similar/<username>', methods=['POST', 'GET'])
def least_similar_page_parametrized(username):
    return least_similar_page(username=username)
