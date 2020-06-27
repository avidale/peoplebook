import hashlib
import os

from config import PEOPLEBOOK_ROOT


def make_pb_url(relative_path, user_tg_id):
    if relative_path.startswith('/'):
        relative_path = relative_path[1:]
    new_id = str(user_tg_id) + os.environ.get('login_salt', 'no_free_salt')
    auth_token = hashlib.md5(str(new_id).encode('utf-8')).hexdigest()
    return '{}/login_link?bot_info={}&next={}'.format(
        PEOPLEBOOK_ROOT,
        auth_token,
        relative_path,
    )
