from flask import render_template, session


def login_required(func):
    def decorated_view(*args, **kwargs):
        if not session.get('logged_in'):
            return render_template('login.html')
        return func(*args, **kwargs)

    decorated_view.__name__ = func.__name__
    return decorated_view
