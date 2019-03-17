from flask import Flask, url_for, redirect, render_template
app = Flask(__name__)


@app.route('/')
def home():
    return redirect(url_for('static', filename='index.html'))
    # return app.send_static_file('index.html')
