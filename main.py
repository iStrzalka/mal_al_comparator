from flask import Flask, render_template, request, redirect, url_for, session, flash
from aniffinity import Aniffinity
import json
import requests
app = Flask(__name__)

from flask_sqlalchemy import SQLAlchemy

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///scores.db'

db = SQLAlchemy(app)

class UserScores(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    service = db.Column(db.String(80), nullable=False)
    scores = db.Column(db.String, nullable=False)


class Anime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    idMal = db.Column(db.Integer, unique=True, nullable=False)
    title = db.Column(db.String(80), nullable=False)
    season = db.Column(db.String(80), nullable=False)
    season_year = db.Column(db.Integer, nullable=False)
    episodes = db.Column(db.Integer, nullable=False)
    link_to_cover = db.Column(db.String(80), nullable=False)

    
ANILIST_QUERY = """
query ($userName: String) {
    MediaListCollection (userName: $userName, status: COMPLETED,
                         type: ANIME, forceSingleCompletedList: true) {
        lists {
            name
            entries {
                score (format: POINT_10) # POINT_10_DECIMAL ?
              	media {
                  	coverImage {
                  	  medium
                  	}
                  	title { romaji }
                  	season
                    seasonYear
                    episodes
                  	id
                  	idMal
                }
            }
        }
    }
}
"""

ERROR = 0
SUCCESS = 1

COMPLETED_LIST_AL = 0
COMPLETED_LIST_MAL = 2


from decimal import Decimal, DivisionByZero, InvalidOperation
from statistics import mean


def pearson(x, y):
    x = [Decimal(str(i)) for i in x]
    y = [Decimal(str(j)) for j in y]

    mx = mean(x)
    my = mean(y)

    xm = [i - mx for i in x]
    ym = [j - my for j in y]

    sx = [i ** 2 for i in xm]
    sy = [j ** 2 for j in ym]

    num = sum(a * b for a, b in zip(xm, ym))
    den = (sum(sx) * sum(sy)).sqrt()

    try:
        return SUCCESS, float(num / den)
    except:
        return ERROR, "division by zero"


def get_affinity(scores):
    scores1, scores2 = zip(*scores)

    result, p = pearson(scores1, scores2)
    if result == ERROR:
        return ERROR, p

    p *= 100
    
    p = round(p, 2)

    return SUCCESS, (p, len(scores))

def get_scores(username, service):
    if service == "ANILIST":
        params = {
            "query": ANILIST_QUERY,
            "variables": {"userName": username}
        }

        resp = requests.post("https://graphql.anilist.co", json=params)

        if resp.status_code == requests.codes.TOO_MANY_REQUESTS:  # pragma: no cover
            return ERROR, "AniList rate limit exceeded"

        mlc = resp.json()["data"]["MediaListCollection"]

        if not mlc:
            # Is this the only reason for not having anything in the MLC?
            return ERROR, "User `{}` does not exist on AniList".format(username)
        
        data = {}
        for lst in mlc["lists"][COMPLETED_LIST_AL]["entries"]:
            id = str(lst["media"]["idMal"])
            if lst["media"]["season"] is None:
                lst["media"]["season"] = "UNKNOWN"
                lst["media"]["seasonYear"] = 4242
            if id == 'None':
                continue
            data[id] = {
                "score": lst["score"],
                "link_to_cover": lst["media"]["coverImage"]["medium"],
                "title": lst["media"]["title"]["romaji"],
                "season": lst["media"]["season"],
                "season_year": lst["media"]["seasonYear"],
                "episodes": lst["media"]["episodes"]
            }        
        return SUCCESS, data

    if service == "MYANIMELIST":
        llist = []

        offset = 0
        while True:
            params = {
                "status": "7",  # all entries
                "offset": offset,
            }
            resp = requests.get(f"https://myanimelist.net/animelist/{username}/load.json", params=params)
            if resp.status_code == requests.codes.TOO_MANY_REQUESTS:
                return ERROR, "MyAnimeList rate limit exceeded"
            if resp.status_code != requests.codes.ok:
                return ERROR, resp.status_code
            
            res = json.loads(resp.text)
            llist.extend(res)
            if len(res) < 300:
                break
            offset += 300

        def get_season_year(date):
            month, _, year = date.split("-")
            month = int(month)
            if month <= 3:
                return "WINTER", year
            elif month <= 6:
                return "SPRING", year
            elif month <= 9:
                return "SUMMER", year
            elif month <= 12:
                return "FALL", year
            return "UNKNOWN", year

        data = {}
        for entry in llist:
            if entry['status'] == COMPLETED_LIST_MAL:
                id = str(entry['anime_id'])
                season, season_year = get_season_year(entry['anime_start_date_string'])
                if season == "UNKNOWN":
                    season = "UNKNOWN"
                    season_year = 4242
                data[id] = {
                    "score": entry['score'],
                    "link_to_cover": entry['anime_image_path'],
                    "title": entry['anime_title'],
                    "season": season,
                    "season_year": season_year,
                    "episodes": entry['anime_num_episodes']
                }
        return SUCCESS, data
    return ERROR, "Invalid service"


@app.route('/')
def index():
    return redirect(url_for('compare'))


@app.route('/add_user', methods=['POST', 'GET'])
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        service = request.form['service']
        scores = None
        try:
            res, scores = get_scores(username, service.upper())
            if res == ERROR:
                return render_template('add_user.html', error="res")
        except:
            return render_template('add_user.html', error="Invalid username or service")
        for score in scores:
            anime = Anime.query.filter_by(idMal=score).first()
            if anime is None:
                anime = Anime(idMal=score, title=scores[score]["title"], season=scores[score]["season"], season_year=scores[score]["season_year"], episodes=scores[score]["episodes"], link_to_cover=scores[score]["link_to_cover"])
                db.session.add(anime)
                db.session.commit()
        user = UserScores.query.filter_by(username=username, service=service.upper()).first()
        if user is None:
            user = UserScores(username=username, service=service.upper(), scores=json.dumps(scores))
            db.session.add(user)
        else:
            user.scores = json.dumps(scores)
        db.session.commit()
        
        return render_template('add_user.html', success="User added/updated successfully")
    else:
        return render_template('add_user.html')

@app.route('/compare', methods=['POST', 'GET'])
def compare():
    users = UserScores.query.all()
    users = [(user.username, user.service) for user in users]
    if request.method == 'POST':
        user1 = UserScores.query.filter_by(username=str(request.form['user1']))
        user2 = UserScores.query.filter_by(username=str(request.form['user2']))
        if user1 is None or user2 is None:
            return render_template('compare.html', error="Invalid username")
        user1 = user1.first()
        user2 = user2.first()
        user1_scores = json.loads(user1.scores)
        user2_scores = json.loads(user2.scores)
        user1_scores = {int(id): user1_scores[id]["score"] for id in user1_scores}
        user2_scores = {int(id): user2_scores[id]["score"] for id in user2_scores}
        
        brackets = {
            'same' : [],
            'user1more1' : [],
            'user1more2' : [],
            'user2more1' : [],
            'user2more2' : []
        }
        scores = []
        for id in user1_scores:
            if id in user2_scores:
                anime = Anime.query.filter_by(idMal=id).first()
                title, season, season_year, episodes, link_to_cover = anime.title, anime.season, anime.season_year, anime.episodes, anime.link_to_cover
                data = {
                    "id": id,
                    "title": title,
                    "season": season,
                    "season_year": season_year,
                    "episodes": episodes,
                    "link_to_cover": link_to_cover,
                    "user1_score": user1_scores[id],
                    "user2_score": user2_scores[id]
                }
                if user1_scores[id] == 0 or user2_scores[id] == 0:
                    continue
                scores.append((user1_scores[id], user2_scores[id]))
                if user1_scores[id] == user2_scores[id]:
                    brackets['same'].append(data)
                if user1_scores[id] == user2_scores[id] + 1:
                    brackets['user1more1'].append(data)
                if user1_scores[id] >= user2_scores[id] + 2:
                    brackets['user1more2'].append(data)
                if user2_scores[id] == user1_scores[id] + 1:
                    brackets['user2more1'].append(data)
                if user2_scores[id] >= user1_scores[id] + 2:
                    brackets['user2more2'].append(data)
        # print(count)
        result, (affinity, length) = get_affinity(scores)
        if result == ERROR:
            return render_template('compare.html', error="Error calculating affinity")

        return render_template('compare.html', users=users, brackets=brackets, sel_user1=user1.username, sel_user2=user2.username, affinity=affinity, length=length)
    else:
        return render_template('compare.html', users=users)



if __name__ == '__main__':
    with app.test_request_context():
        db.create_all()
    
    app.run(debug=True, port=4242)
