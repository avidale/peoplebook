import os

from peoplebot.response_logic import NewMultiverse
from utils.global_database import DATABASE, MONGO_URL

BASE_URL = os.environ.get('BASE_URL', 'https://kappa-vedi-bot.herokuapp.com/')

MULTIVERSE = NewMultiverse(db=DATABASE, base_url=BASE_URL)

MULTIVERSE.init_spaces()
MULTIVERSE.create_bots()
