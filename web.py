import json
from flask import Flask, render_template, abort
from uploader import update_people, update_if_needed

app = Flask(__name__)

with open('history_config.json', 'r', encoding='utf-8') as f:
    history_config = json.load(f)


@app.route('/')
def home():
    update_if_needed()
    return render_template(
        'peoplebook.html', period=history_config['current'], period_text=history_config['current_text']
    )


@app.route('/updater')
def updater():
    message = update_people()
    return message


@app.route('/history/<period>')
def history(period):
    if period in history_config['history']:
        update_if_needed()
        return render_template('peoplebook.html', period=period, period_text=history_config['history'][period])
    abort(404)
