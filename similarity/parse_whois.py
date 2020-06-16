import os
import pandas as pd
import pickle
import razdel

from collections import defaultdict
from utils.database import Database

from sklearn.model_selection import cross_validate
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline


def sentenize(text):
    return [
        t.text for
        par in text.split('\n')
        for t in razdel.sentenize(par)
        if t.text and t.text != '#whois'
    ]


def prepare_data(db: Database):
    pbdf = pd.DataFrame(db.mongo_peoplebook.find())
    data = []
    for i, row in pbdf.iterrows():
        for label in ['activity', 'topics', 'contacts']:
            value = row[label]
            if not value or not isinstance(value, str):
                continue
            for sent in sentenize(value):
                data.append({'text': sent, 'label': label})
    df = pd.DataFrame(data)
    return df


def train(df_train):
    model = make_pipeline(
        TfidfVectorizer(min_df=3, analyzer='char_wb', ngram_range=(3, 5)),
        LogisticRegression()
    )
    print(pd.DataFrame(cross_validate(
        model,
        df_train.text,
        df_train.label,
        cv=3,
        scoring=['accuracy', 'f1_macro']))
    )
    model.fit(df_train.text, df_train.label)
    return model


def load_model(path='similarity/whois_parser.pkl'):
    with open(path, 'rb') as f:
        return pickle.load(f)


def segmentize(model, text):
    results = defaultdict(list)
    texts = sentenize(text)
    proba = pd.DataFrame(model.predict_proba(texts), columns=model.classes_)
    proba['activity'] *= 0.5
    preds = proba.idxmax(axis=1)

    for p, label in zip(texts, preds):
        results[label].append(p)

    results = {k: ' '.join(v) for k, v in results.items() if v}

    for key, default_value in {
        'first_name': 'Anonymous',
        'last_name': 'Anonymous',
        'activity': '',
        'topics': '',
        'contacts': '',
    }.items():
        if key not in results:
            results[key] = default_value
    return results


def main():
    print('Training whois segmenter...')
    MONGO_URL = os.environ['MONGODB_URI']
    db = Database(MONGO_URL)
    data = prepare_data(db=db)
    model = train(df_train=data)
    with open('similarity/whois_parser.pkl', 'wb') as f:
        pickle.dump(model, f)
    print('Whois segmenter training completed!')


WHOIS_SEGMENTER_MODEL = load_model()
