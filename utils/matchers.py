import os
import re
import pymorphy2
import yaml

morph = pymorphy2.MorphAnalyzer()
with open(os.path.join(os.path.dirname(__file__), 're_mat.yaml'), 'r', encoding='utf-8') as f:
    obscenities = yaml.safe_load(f)


POSITIVE = re.compile(
    '((было|ваще|супер|вс[её]) )*'
    '(хорошо|отлично|ч[её]тко|[ао]хуенно|классно|замечательно|кайф|класс|супер|огонь|офигенно|топово)'
)


def inflect_first_word(text, case):
    words = text.split()
    first_word = morph.parse(words[0])[0].inflect({case}).word
    return ' '.join([first_word] + words[1:])


def fast_normalize(text):
    text = re.sub('[^a-zа-яё0-9]+', ' ', text.lower())
    text = re.sub('\\s+', ' ', text).strip()
    text = re.sub('ё', 'е', text)
    return text


def is_like_telegram_login(text):
    return bool(re.match('[a-z0-9_]{5,}', text))


def is_like_yes(text):
    return bool(re.match('да|ага|конечно|yes|ес', text))


def is_like_no(text):
    return bool(re.match('нет|no|nope', text))


def normalize_username(username):
    if not isinstance(username, str):
        return username
    if username is not None:
        username = username.lower().strip().strip('@')
        for prefix in ['https://t.me/', 't.me/']:
            if username.startswith(prefix):
                username = username[len(prefix):]
        return username
    return None


assert normalize_username(' https://t.me/KOTIK   ') == 'kotik'


def is_obscene(text):
    for word in text.split():
        for pattern in obscenities:
            if re.match(pattern, word):
                return True
    return False


def like_positive_feedback(text):
    return re.match(POSITIVE, text)


def like_did_not_meet(text):
    if re.match('(.+ )?не (было|пил[аи]?|виделись|встретились|встречал(ись|ся|ась)|получилось|прошло)', text):
        return True
    if re.match('(никак|ничего не было)', text):
        return True
    return False


def like_will_meet(text):
    if re.match('.*след(ующ..)? недел', text):
        return True
    if re.match('.*завтра', text):
        return True
    if re.match('.*(будем пить|встретимся)', text):
        return True
    if re.match('перенес(ли|ти)', text):
        return True
    if 'еще' in text.split():
        return True
    return False


def like_positive_emoji(text):
    s = set(text)
    smileys = set('👍🏼🤗✊😋😂😅🤘🔥👍✌️')
    return s and s.intersection(smileys)


def like_did_not_agree(text):
    return 'не ответил' in text or 'не договорились' in text
