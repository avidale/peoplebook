from flask import Flask, url_for, redirect
from read_sheet import get_creds, get_rows

app = Flask(__name__)


@app.route('/')
def home():
    return redirect(url_for('static', filename='index.html'))
    # return app.send_static_file('index.html') # todo: maybe fix the relative links and really send it


@app.route('/updater')
def updater():
    creds = get_creds()
    rows = get_rows(creds, '1srgTgCU1mhOiqV90DVb8_GVi0GBTivbhuj21jxr65Pk', 'Ответы на форму (1)!A2:F')
    return '\n'.join(['<div>{}</div>'.format(row[1])  for row in rows])
