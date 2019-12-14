import math

from collections import Counter, defaultdict
from functools import lru_cache
from nltk import wordpunct_tokenize, SnowballStemmer


class Searcher:
    def __init__(self, k=1.5, b=0.75):
        self.k = k
        self.b = b
        self.stemmer = SnowballStemmer(language='russian')

    @lru_cache(10000)
    def stem(self, word):
        return self.stemmer.stem(word)

    def tokenize(self, text, stem=True):
        words = [w.lower() for w in wordpunct_tokenize(text)]
        if stem:
            words = [self.stem(w) for w in words]
        return words

    def fit(self, paragraphs):
        inverse_index = defaultdict(set)
        text_frequencies = Counter()
        text_lengths = Counter()
        for p_id, p in paragraphs.items():
            tokens = self.tokenize(p)
            text_lengths[p_id] = len(tokens)
            for w in tokens:
                inverse_index[w].add(p_id)
                text_frequencies[(p_id, w)] += 1
        self.inverse_index = inverse_index
        self.text_frequencies = text_frequencies
        self.text_lengths = text_lengths
        self.avg_len = sum(text_lengths.values()) / len(text_lengths)
        self.n_docs = len(paragraphs)

    def get_okapi_idf(self, w):
        n = len(self.inverse_index[w])
        return math.log((self.n_docs - n + 0.5) / (n + 0.5))

    def get_okapi_tf(self, w, p_id):
        f = self.text_frequencies[(p_id, w)]
        return f * (self.k + 1) / (f + self.k * (1 - self.b + self.b * self.text_lengths[p_id] / self.avg_len))

    def get_tf_idfs(self, query):
        words = self.tokenize(query)
        matches = [(w, d) for w in words for d in self.inverse_index[w]]

        tfidfs = Counter()
        for w, d in matches:
            tfidfs[d] += self.text_frequencies[(d, w)] / len(self.inverse_index[w])

        return tfidfs

    def get_okapis(self, query):
        words = self.tokenize(query)
        matches = [(w, d) for w in words for d in self.inverse_index[w]]

        tfidfs = Counter()
        for w, d in matches:
            tfidfs[d] += self.get_okapi_idf(w) * self.get_okapi_tf(w, d)

        return tfidfs


def make_bigrams(words):
    return {'{}__{}'.format(w1, w2) for w1, w2 in zip(words[:-1], words[1:])}


def common_fraction(a, b, prepare=None):
    if prepare is not None:
        a = prepare(a)
        b = prepare(b)
    a = set(a)
    b = set(b)
    if len(a) == 0:
        return 0
    return len(a.intersection(b)) / len(a)


def rerank(query, tfidfs, searcher, paragraphs, n=10, min_mult_from_top=0.9):
    pairs = tfidfs.most_common(n)
    new_rank = []
    query_stems = searcher.tokenize(query, stem=True)
    query_words = searcher.tokenize(query, stem=False)

    for doc_id, score in pairs:
        doc = paragraphs[doc_id]

        doc_stems = searcher.tokenize(doc, stem=True)
        doc_words = searcher.tokenize(doc, stem=False)

        match_scores = [
            common_fraction(query_stems, doc_stems),
            common_fraction(query_stems, doc_stems, prepare=make_bigrams),
            common_fraction(query_words, doc_words),
            common_fraction(query_words, doc_words, prepare=make_bigrams),
        ]
        new_rank.append({
            'id': doc_id,
            'old_score': score,
            'recall': sum(match_scores) / len(match_scores),
            'new_score': score + sum(match_scores) * 10
        })
    new_rank = sorted(new_rank, key=lambda x: -x['new_score'])
    best_recall = new_rank[0]['recall']
    min_recall = best_recall * (min_mult_from_top or 0)
    filtered = [r for r in new_rank if r['recall'] >= min_recall]
    return filtered
