"""
This script is used with Heroku scheduler.
It intends to call a wakeup function in the main.py (if necessary, restart the main web dyno)
"""
import os
import random
import requests


ADMIN_URL_PREFIX = os.environ.get('ADMIN_URL_PREFIX') or str(random.random())
BASE_URL = os.environ.get('BASE_URL', 'https://kappa-vedi-bot.herokuapp.com/')


def do_frequent_wakeup():
    print('DOING THE FREQUENT WAKEUP')
    requests.get(os.path.join(BASE_URL, "{}/frequent-wakeup/".format(ADMIN_URL_PREFIX)), )


if __name__ == '__main__':
    do_frequent_wakeup()
