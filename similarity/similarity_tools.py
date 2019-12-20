import pandas as pd
import numpy as np
from tqdm.auto import tqdm
from scipy.optimize import linear_sum_assignment


def deduplicate(facts, max_number=3, threshold=0.5):
    lhs = set()
    rhs = set()
    facts = sorted(facts, key=lambda x: x['score'], reverse=True)
    result = []
    for fact in facts:
        if fact['first'] not in lhs and fact['second'] not in rhs and fact['score'] >= threshold:
            result.append(fact)
        lhs.add(fact['first'])
        rhs.add(fact['second'])
    return result[:max_number]


class FallbackW2V:
    def __init__(self, first, second):
        self.first = first
        self.second = second

    def __getitem__(self, item):
        if item in self.first:
            return self.first[item]
        return self.second[item]

    def __contains__(self, item):
        return True


def rank_similarities(one, owner2texts, matcher, score_decay=0.75, num_scores=3):
    # takes 3 to 20 seconds to calculate for a single person
    others = []
    others_scores = []
    others_results = []

    for another in tqdm(list(owner2texts.keys())):
        if another != one:
            results = []
            for i, (t1, p1) in enumerate(owner2texts[one]):
                for j, (t2, p2) in enumerate(owner2texts[another]):
                    score = matcher.compare(p1, p2)
                    results.append({'score': round(score, 2), 'first': t1, 'second': t2})
            results = deduplicate(results, threshold=0.0)
            assert len(results) > 0

            rscores = [r['score'] for r in results[:num_scores]]
            while len(rscores) < num_scores:
                rscores.append(rscores[-1] * score_decay)

            results_score = np.mean(rscores)

            others.append(another)
            others_scores.append(results_score)
            others_results.append(results)

    rating = pd.DataFrame(
        {'who': others, 'score': others_scores, 'res': others_results}
    ).sort_values('score', ascending=False)
    return rating


def assign_pairs(sims, n_pairs=10):
    """ Take a square matrix `sims` as input;
        for each its row returns 10 its columns in such a way that total sum of weights is minimized.
        It's a special case of transportation problem.
    """
    sims = np.copy(sims)
    for i in range(sims.shape[0]):
        sims[i, i] = 100500
    seconds = []
    for k in range(n_pairs):
        first, second = linear_sum_assignment(sims)
        # print(sims[first, second].sum(), end=', ')
        for i, j in enumerate(second):
            sims[i, j] = 100500
            sims[j, i] = 100500
        seconds.append(second)
    seconds = np.stack(seconds).T
    return seconds
