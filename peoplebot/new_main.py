import os
import random

from utils.database import Database
from peoplebot.response_logic import NewMultiverse


BASE_URL = os.environ.get('BASE_URL')
MONGO_URL = os.environ.get('MONGODB_URI')
ADMIN_URL_PREFIX = os.environ.get('ADMIN_URL_PREFIX') or str(random.random())

DATABASE = Database(MONGO_URL, admins={
    # todo: make admins space-level
    'cointegrated', 'stepan_ivanov', 'jonibekortikov', 'dkkharlm', 'helmeton', 'kolikovnikita',
})

MULTIVERSE = NewMultiverse(db=DATABASE, base_url=BASE_URL)

MULTIVERSE.init_spaces()
MULTIVERSE.create_bots()
