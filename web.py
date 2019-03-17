from flask import Flask, url_for, redirect
from uploader import update_people

app = Flask(__name__)
app.config["CACHE_TYPE"] = "null"


@app.route('/')
def home():
    return redirect(url_for('static', filename='index.html'))
    # return app.send_static_file('index.html')
    # todo: maybe fix the relative links and really send the static file


@app.route('/updater')
def updater():
    message = update_people()
    return message
