import os

from utils.database import Database
from peoplebot.response_logic import NewMultiverse


BASE_URL = os.environ.get('BASE_URL', 'https://kappa-vedi-bot.herokuapp.com/')
MONGO_URL = os.environ.get('MONGODB_URI')

DATABASE = Database(MONGO_URL)

MULTIVERSE = NewMultiverse(db=DATABASE, base_url=BASE_URL)

MULTIVERSE.init_spaces()
MULTIVERSE.create_bots()
