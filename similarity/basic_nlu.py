import pymorphy2
import re
import razdel

from functools import lru_cache

MEANINGFUL_POS =  {
    'NOUN', 'ADJF', 'VERB', 'ADJS', 'ADVB', 'INFN', 'PRTS', 'PRTF', 'COMP', 'NUMR', 'PRED', 'GRND',
}
HAS_ALPHA = re.compile('.*[a-zA-Zа-яА-ЯёЁ].*')

PYMORPHY = pymorphy2.MorphAnalyzer()


@lru_cache(maxsize=10000)
def pymorphy_parse(word):
    return PYMORPHY.parse(word)


def word2lemma(word, filter_pos=False):
    hypotheses = pymorphy_parse(word)
    if len(hypotheses) == 0:
        return word
    if filter_pos and hypotheses[0].tag.POS not in MEANINGFUL_POS:
        if str(hypotheses[0].tag) != 'LATN':
            return ''
    return hypotheses[0].normal_form


def fast_normalize(text, lemmatize=False, filter_pos=False):
    text = re.sub('[^a-zа-яё0-9]+', ' ', text.lower())
    # we consider '-' as a delimiter, because it is often missing in results of ASR
    text = re.sub('\s+', ' ', text).strip()
    if lemmatize:
        lemmas = [word2lemma(w, filter_pos=filter_pos) for w in text.split()]
        text = ' '.join([l for l in lemmas if l])
    text = re.sub('ё', 'е', text)
    return text


def split(text, need_alhpa=True, min_len=2):
    sentences = [s.text for s in razdel.sentenize(text)]
    result = []
    for s in sentences:
        result.extend(re.split('[,:\n\(\)]', s))
    result = [r.strip() for r in result]
    result = [r for r in result if r and len(r) >= min_len]
    if need_alhpa:
        result = [r for r in result if re.match(HAS_ALPHA, r)]
    return result


class Weighter:
    def __init__(self, pos_weights=None, default_weight=1, custom_weights=None, lookup_lemma=True):
        self.pos_weights = pos_weights or {}
        self.default_weight = default_weight
        self.custom_weights = custom_weights or {}
        self.lookup_lemma = lookup_lemma

    def __call__(self, words):
        return [self[word] for word in words]

    def __getitem__(self, word):
        if word in self.custom_weights:
            return self.custom_weights[word]
        if self.pos_weights or self.lookup_lemma:
            hypotheses = pymorphy_parse(word)
            if hypotheses:
                tag = hypotheses[0].tag
                lemma = hypotheses[0].lemma
                if self.lookup_lemma and lemma in self.custom_weights:
                    return self.custom_weights[lemma]
                if str(tag) == 'LATN' and 'LATN' in self.pos_weights:
                    return self.pos_weights['LATN']
                if tag.POS in self.pos_weights:
                    return self.pos_weights[tag.POS]
        return self.default_weight


NOISE_WORDS = {
    'сейчас', 'работать', 'заниматься', 'мочь', 'рассказать', 'проект', 'раньше', 'делать', 'работа',
    'интересоваться', 'увлекаться', 'быть', 'досуг', 'поделиться', 'могу', 'развиваю', 'бэкграунд',
}

NOISE_WORDS = {word2lemma(w): 0.2 for w in NOISE_WORDS}
