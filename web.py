import json
import os
import pymongo

from autolink import linkify

from flask import Flask, render_template, abort

app = Flask(__name__)

with open('history_config.json', 'r', encoding='utf-8') as f:
    history_config = json.load(f)


MONGO_URL = os.environ.get('MONGODB_URI')
mongo_client = pymongo.MongoClient(MONGO_URL)
mongo_db = mongo_client.get_default_database()
mongo_events = mongo_db.get_collection('events')
mongo_participations = mongo_db.get_collection('event_participations')
mongo_peoplebook = mongo_db.get_collection('peoplebook')
mongo_membership = mongo_db.get_collection('membership')


@app.template_filter('linkify_filter')
def linkify_filter(s):
    return linkify(s)


@app.route('/')
def home():
    all_events = mongo_events.find().sort('date', pymongo.DESCENDING)
    for event in all_events:
        who_comes = list(mongo_participations.find({'code': event['code'], 'status': 'ACCEPT'}))
        if len(who_comes) >= 1: # one participant is enough to show the event - but this may be revised
            return peoplebook_for_event(event['code'])
    return render_template(
        'peoplebook.html', period=history_config['current'], period_text=history_config['current_text']
    )


@app.route('/history/<period>')
def history(period):
    if period in history_config['history']:
        return render_template('peoplebook.html', period=period, period_text=history_config['history'][period])
    abort(404)


@app.route('/event/<event_code>')
def peoplebook_for_event(event_code):
    the_event = mongo_events.find_one({'code': event_code})
    if the_event is None:
        return 'Такого события не найдено!'
    raw_profiles = list(mongo_participations.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'username',
                'foreignField': 'username',
                'as': 'profiles'
            }
        }, {
            '$match': {'code': event_code, 'status': 'ACCEPT'}
        }
    ]))
    profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
    return render_template(
        'backend_peoplebook.html',
        title=the_event.get('title', 'Пиплбук встречи'),
        profiles=profiles
    )


@app.route('/members')
def peoplebook_for_all_members():
    raw_profiles = list(mongo_membership.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'username',
                'foreignField': 'username',
                'as': 'profiles'
            }
        }, {
            '$match': {'is_member': True}
        }
    ]))
    profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
    return render_template(
        'backend_peoplebook.html',
        title='Члены клуба Каппа Веди',
        profiles=profiles
    )

@app.route('/members_and_guests')
def peoplebook_for_all_members_and_guests():
    raw_profiles = list(mongo_membership.aggregate([
        {
            '$lookup': {
                'from': 'peoplebook',
                'localField': 'username',
                'foreignField': 'username',
                'as': 'profiles'
            }
        }
    ]))
    profiles = [p for rp in raw_profiles for p in rp.get('profiles', [])]
    return render_template(
        'backend_peoplebook.html',
        title='Члены клуба Каппа Веди и его гости',
        profiles=profiles
    )


@app.route('/person/<username>')
def peoplebook_for_person(username):
    the_profile = mongo_peoplebook.find_one({'username': username})
    if the_profile is None:
        return 'Такого профиля не найдено!'
    return render_template('single_person.html', profile=the_profile)
