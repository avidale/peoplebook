from sklearn.neighbors import KDTree
from similarity import basic_nlu
from tqdm.auto import tqdm

import numpy as np
import pickle


class SemanticSearcher:
    def __init__(self):
        pass

    def setup(self, texts, owners, vectors, vectorizer):
        self.texts = texts
        self.owners = owners
        self.vectors = vectors
        self.vectorizer = vectorizer
        self.knn = KDTree(self.vectors)
        return self

    def lookup(self, text):
        results = []
        dist, idx = [x[0] for x in self.knn.query(self.vectorizer(text).reshape(1, -1), k=20)]
        for i, d in zip(idx, dist):
            results.append({
                'username': self.owners[i],
                'text': self.texts[i],
                'score': d,
            })
        return results


def extract_all_chunks(df):
    parts = []
    owners = []
    normals = []
    indexes = []

    idx = 0
    for i, row in tqdm(df.iterrows()):
        texts = basic_nlu.split(row.activity + '\n' + row.topics)
        for text in texts:
            normalized = basic_nlu.fast_normalize(text, lemmatize=True, filter_pos=True)
            if normalized:
                parts.append(text)
                normals.append(normalized)
                owners.append(row.username)
                indexes.append(idx)
                idx += 1
    return parts, owners, normals, indexes


def save_searcher_data(parts, owners, vectorizer):
    vecs = np.stack([vectorizer(t) for t in parts])

    searcher_data = {
        'texts': parts,
        'owners': owners,
        'vectors': vecs,
    }

    with open('C:/Users/ddale/YandexDisk/code/peoplebook/similarity/searcher_data.pkl', 'wb') as f:
        pickle.dump(searcher_data, f)
