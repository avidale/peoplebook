from flask import Flask, render_template
from uploader import update_people

app = Flask(__name__)
app.config["CACHE_TYPE"] = "null"


@app.route('/')
def home():
    return render_template('peoplebook.html')


@app.route('/updater')
def updater():
    message = update_people()
    return message
