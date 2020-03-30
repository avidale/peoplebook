"""
This script is used with Heroku scheduler.
It intends to call a wakeup function in the main.py (if necessary, restart the main web dyno)
"""
import os
import requests


BASE_URL = os.environ.get('BASE_URL', 'https://kappa-vedi-bot.herokuapp.com/')


if __name__ == '__main__':
    requests.get(os.path.join(BASE_URL, "wakeup/"))
