import gensim
import pickle
import numpy as np
import pandas as pd
import time

from tqdm.auto import tqdm
from collections import defaultdict

from similarity.semantic_search import SemanticSearcher, get_searcher_data, extract_all_chunks
from similarity import matchers, basic_nlu, similarity_tools
from similarity.simple_searcher import SimpleSearcher


class ProfileSearcher:
    def __init__(self, w2v, records):
        self.w2v = w2v
        if not records:
            self.fitted = False
            return
        self.fitted = True
        self.prepare_matchers(records=records)
        self.prepare_df(records=records)

    def prepare_matchers(self, records):
        self.weighter = basic_nlu.Weighter(custom_weights=basic_nlu.NOISE_WORDS)
        self.matcher = matchers.WMDMatcher(
            text_normalization='fast_lemmatize_filter_pos',
            w2v=self.w2v,
            weighter=self.weighter
        )
        texts = [p.get('activity', '') + '\n' + p.get('topics', '') for p in records]
        texts = [t for text in texts for t in basic_nlu.split(text)]
        self.matcher.fit(texts, ['' for _ in texts])

        self.w2vmatcher = matchers.W2VMatcher(
            w2v=self.w2v,
            weighter=self.weighter,
            text_normalization='fast_lemmatize_filter_pos'
        )

    def prepare_df(self, records):
        t = time.time()
        print('start getting searcher data')
        df = pd.DataFrame(records)
        for c in ['first_name', 'last_name', 'activity', 'topics', 'fulltext', 'username']:
            if c not in df.columns:
                df[c] = ''
        df.topics.fillna('', inplace=True)
        df.activity.fillna('', inplace=True)
        self.df = df

        parts, owners, normals = extract_all_chunks(df)
        searcher_data = get_searcher_data(parts, owners, vectorizer=self.text2vec)

        # searcher
        self.searcher = SemanticSearcher()
        self.searcher.setup(**searcher_data, vectorizer=self.text2vec)

        # simple searcher
        self.simple_searcher = SimpleSearcher()
        self.simple_searcher.setup(texts=parts, owners=owners)

        # most similar people
        # todo: make it updateable
        preprocessed = [self.matcher.preprocess(p) for p in tqdm(searcher_data['texts'])]
        self.owner2texts = defaultdict(list)
        for prep, owner, text in zip(preprocessed, searcher_data['owners'], searcher_data['texts']):
            self.owner2texts[owner].append((text, prep))

        # least similar people
        df['fulltext'] = ' '
        for i, row in df.iterrows():
            df.loc[i, 'fulltext'] = '{} {}\n{}\n{}'.format(row.first_name, row.last_name, row.activity, row.topics)
        self.new_matcher = matchers.W2VMatcher(w2v=self.w2v, weighter=self.weighter)
        self.new_matcher.fit(df.fulltext.tolist(), df.username.tolist())
        self.user_vecs = np.stack(self.new_matcher._texts)
        self.sims = np.dot(self.user_vecs, self.user_vecs.T)
        self.dissimilar_pairs = similarity_tools.assign_pairs(self.sims, n_pairs=20)

    def lookup(self, req_text, unicalize=True):
        if not self.fitted:
            return []
        smart_results = self.searcher.lookup(req_text)
        simple_results = self.simple_searcher.lookup(req_text, normalize_scores=False)

        total_results = smart_results + simple_results
        total_results = sorted(total_results, key=lambda x: x['score'], reverse=True)

        if unicalize:
            unique_people = []
            unique_people_id = set()
            for item in total_results:
                if item['username'] not in unique_people_id:
                    unique_people.append(item)
                    unique_people_id.add(item['username'])
            total_results = unique_people

        return total_results

    def text2vec(self, t):
        v = self.w2vmatcher.preprocess(t)
        if v is None:
            return np.zeros(300)
        return v

    def get_top_dissimilar(self, username):
        for user_idx, un in enumerate(self.df.username):
            if un == username:
                break
        who = self.dissimilar_pairs[user_idx]
        how = self.sims[user_idx, who]
        top = [{
            'username': username,
            'score': score,
            'who': self.df.username.iloc[other_id],
        } for score, other_id in zip(how, who)]
        return top


def load_ft(
        exact_path='similarity/fasttext_extract.pkl',
        model_path='similarity/araneum_new_compressed.model',
):
    with open(exact_path, 'rb') as f:
        main_w2v = pickle.load(f)

    ft_small = gensim.models.fasttext.FastTextKeyedVectors.load(model_path)

    w2v = similarity_tools.FallbackW2V(main_w2v, ft_small)
    return w2v
