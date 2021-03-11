import os

from utils.database import Database

MONGO_URL = os.environ.get('MONGODB_URI')
DATABASE = Database(MONGO_URL)
