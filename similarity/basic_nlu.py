import pymorphy2
import re

from functools import lru_cache

MEANINGFUL_POS =  {
    'NOUN', 'ADJF', 'VERB', 'ADJS', 'ADVB', 'INFN', 'PRTS', 'PRTF', 'COMP', 'NUMR', 'PRED', 'GRND'
}

PYMORPHY = pymorphy2.MorphAnalyzer()


@lru_cache(maxsize=16384)
def word2lemma(word, filter_pos=False):
    hypotheses = PYMORPHY.parse(word)
    if len(hypotheses) == 0:
        return word
    if filter_pos and hypotheses[0].tag.POS not in MEANINGFUL_POS:
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


def split(text):
    result = re.split('[\.,:\n]', text)
    result = [r.strip() for r in result]
    result = [r for r in result if r]
    return result
