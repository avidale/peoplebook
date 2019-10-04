from flask_login import UserMixin


# silly user model
class User(UserMixin):

    def __init__(self, id):
        self.id = id
        self.password = self.id + "_secret"

    def __repr__(self):
        return "{}/{}".format(self.id, self.password)

