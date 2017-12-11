from flask import Flask, render_template, request, jsonify
import requests
import os
import nltk, re, operator
from stop_words import stops
from collections import Counter
from bs4 import BeautifulSoup
from flask_sqlalchemy import SQLAlchemy

from rq import Queue
from rq.job import Job
from worker import conn
import json

app = Flask(__name__)
app.config.from_object(os.environ['APP_SETTINGS'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
q = Queue(connection=conn)

from models import *

def count_and_save_words(url):
    try:
        r = requests.get(url)
    except:
        errors.append("Unable to get URL")
        return render_template('index.html', errors = errors)
    if r:
        # text processing
        raw = BeautifulSoup(r.text, 'html.parser').get_text()
        nltk.data.path.append('./nltk_data/')
        tokens = nltk.word_tokenize(raw)
        text = nltk.Text(tokens)
        # Remove punctuations, count raw words
        nonPunct = re.compile('.*[A-Za-z].*')
        raw_words = [w for w in text if nonPunct.match(w)]
        raw_word_count = Counter(raw_words)
        
        # stop words
        no_stop_words = [w for w in raw_words if w.lower() not in stops]
        no_stop_words_count = Counter(no_stop_words)
        
        # Save results
        try:
            result = Result(
                    url = url,
                    result_all = raw_word_count,
                    result_no_stop_words = no_stop_words_count
                    )
            db.session.add(result)
            db.session.commit()
        except:
            errors.append('Unable to add item to database')
            return {'errors':errors}

@app.route('/', methods=['GET','POST'])
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def get_counts():
    # get url
    data = json.loads(request.data.decode())
    url = data['url']
    if 'http://' not in url[:7]:
        url = 'http://' + url
    # start job
    job = q.enqueue_call(
        func=count_and_save_words, args=(url,), result_ttl = 5000
    )
    # return job created id
    return job.get_id()

@app.route('/results/<job_id>', methods=['GET'])
def get_results(job_id):
    job = Job.fetch(job_id, connection=conn)
    if job.is_finished:
        result = Result.query.filter_by(id=job.result).first()
        results = sorted(
            result.result_no_stop_words.items(),
            key = operator.itemgetter(1),
            reverse = True
        )[:10]        
        return jsonify(results)
    else:
        return "No", 202

if __name__ == "__main__":
    print('App settings: ', os.environ['APP_SETTINGS'])
    app.run()
