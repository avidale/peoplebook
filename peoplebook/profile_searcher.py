import gensim
import pickle
import numpy as np
import pandas as pd
import time

from tqdm.auto import tqdm
from collections import defaultdict

from similarity.semantic_search import SemanticSearcher, get_searcher_data, extract_all_chunks
from similarity import matchers, basic_nlu, similarity_tools


class ProfileSearcher:
    def __init__(self, w2v, records):
        self.w2v = w2v
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
        df.topics.fillna('', inplace=True)
        df.activity.fillna('', inplace=True)
        self.df = df

        parts, owners, normals = extract_all_chunks(df)
        searcher_data = get_searcher_data(parts, owners, vectorizer=self.text2vec)

        # searcher
        self.searcher = SemanticSearcher()
        self.searcher.setup(**searcher_data, vectorizer=self.text2vec)

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


def load_ft():
    with open('similarity/fasttext_extract.pkl', 'rb') as f:
        main_w2v = pickle.load(f)

    ft_small = gensim.models.fasttext.FastTextKeyedVectors.load(
        'similarity/araneum_new_compressed.model'
    )

    w2v = similarity_tools.FallbackW2V(main_w2v, ft_small)
    return w2v
