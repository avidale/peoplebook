from flask_login import UserMixin
import hashlib


# silly user model
class User(UserMixin):

    def __init__(self, id):
        self.id = id
        self.password = str(self.id) + "_secret"

    def __repr__(self):
        return hashlib.md5(self.id.encode('utf-8'))

