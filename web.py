from flask import Flask
from uploader import update_people

app = Flask(__name__)
app.config["CACHE_TYPE"] = "null"


@app.route('/')
def home():
    return app.send_static_file('index.html')


@app.route('/updater')
def updater():
    message = update_people()
    return message
