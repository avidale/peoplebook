import json
from flask import Flask, url_for, redirect
from read_sheet import get_creds, get_rows, rows_to_json

app = Flask(__name__)


@app.route('/')
def home():
    return redirect(url_for('static', filename='index.html'))
    # return app.send_static_file('index.html') # todo: maybe fix the relative links and really send it


@app.route('/updater')
def updater():
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    creds = get_creds()
    rows = get_rows(creds, config['sheet_id'], config['sheet_range'])
    result = rows_to_json(config, rows)
    #return '\n'.join(['<div>{}</div>'.format(row[1]) for row in rows])
    return json.dumps(result, ensure_ascii=False, indent=2)
