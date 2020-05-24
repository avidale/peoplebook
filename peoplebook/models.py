from flask_login import UserMixin


# silly user model
class User(UserMixin):

    def __init__(self, id, username=None, data=None):
        self.id = id
        self.username = username  # todo: make sure it is passed -> use in web pages
        self.data = data
        self.password = str(self.id) + "_secret"

    def __repr__(self):
        return str(self.id)
