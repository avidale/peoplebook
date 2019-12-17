from sklearn.neighbors import KDTree


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
