from flask import Flask, url_for, redirect
app = Flask(__name__)


@app.route('/')
def home():
    return redirect('/site/index.html')
