#!/usr/bin/python3
import hashlib
import os
import flask
import werkzeug
import argparse
import sys
import json
import datetime

from pygbx import Gbx, GbxType
import tm2020parser

import sqlalchemy
from sqlalchemy import Column, Integer, String, Boolean, or_, and_, asc, desc
from flask_sqlalchemy import SQLAlchemy

app = flask.Flask("TM Friends Replay Server")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLITE_LOCATION") or "sqlite:///sqlite.db"
db = SQLAlchemy(app)

class Map(db.Model):

    __tablename__ = "maps"

    map_uid = Column(String, primary_key=True)
    mapname = Column(String)
    game    = Column(String)

    def get_best_replay(self):

        q = db.session.query(ParsedReplay).filter(ParsedReplay.map_uid == self.map_uid)
        r = q.order_by(asc(ParsedReplay.race_time)).first()
        return r

    def get_best_replay_for_player(self, player):

        q = db.session.query(ParsedReplay).filter(ParsedReplay.map_uid == self.map_uid)
        q = q.filter(or_(ParsedReplay.uploader == player, ParsedReplay.login == player))
        r = q.order_by(asc(ParsedReplay.race_time)).first()
        return r

    def get_second_best_replay(self):

        q = db.session.query(ParsedReplay).filter(ParsedReplay.map_uid == self.map_uid)
        q = q.filter(ParsedReplay.login != self.get_best_replay().login)
        results = q.order_by(asc(ParsedReplay.race_time)).all()
        if not results or len(results) < 1:
            return None
        return results[0] # because first is already filtered out by login filter

    def get_record_replay_percent_diff(self):

        best = self.get_best_replay()
        second = self.get_second_best_replay()

        if not second:
            return ""
        elif best.race_time == second.race_time:
            return "Tied by {}".format(second.clean_login())
        else:
            dif = second.race_time - best.race_time
            percent = dif/best.race_time*100
            return "+ {:.2f}% by {}".format(percent, second.clean_login())

    def get_best_replay_repr(self):
        r = self.get_best_replay()
        if not r:
            return "-"
        return str(r)

    def get_best_replay_age(self):

        parsed = datetime.datetime.fromisoformat(self.get_best_replay().upload_dt)
        delta = datetime.datetime.now() - parsed
        return delta.days

class UserSettings(db.Model):

    __tablename__ = "user_settings"

    user = Column(String, primary_key=True)

    show_tm_2020         = Column(Boolean)
    show_tmnf            = Column(Boolean)
    show_tm_2020_current = Column(Boolean)

    notifcations_all     = Column(Boolean)
    notifcations_self    = Column(Boolean)

class ParsedReplay(db.Model):

    __tablename__ = "replays"

    filehash    = Column(String, primary_key=True)

    ghost_id    = Column(Integer)
    race_time   = Column(Integer)

    uploader    = Column(String)
    filepath    = Column(String)
    upload_dt   = Column(String)

    map_uid     = Column(String) # ghost_uid
    login       = Column(String)
    cp_times    = Column(String)

    login_uid_tm2020 = Column(String)
    game = Column(String)

    def clean_login(self):
        if "/" in self.login:
            return self.login.split("/")[0]
        else:
            return self.login

    def get_human_readable_time(self, thousands=False):
        t = datetime.timedelta(microseconds=self.race_time*1000)
        t_string = str(t)
        if t.seconds < 60*60:
            t_string =  t_string[2:]
        if t.microseconds != 0:
            return t_string[:-4]
        return t_string + ".00"

    def __repr__(self):
        return "{time} on {map_n} by {login}".format(
                    time=self.get_human_readable_time(),
                    map_n=self.map_uid, login=self.login)

    def to_dict(self):
        d = dict()
        d.update({ "login" : self.login })
        d.update({ "race_time" : self.get_human_readable_time() })
        d.update({ "filepath" : self.filepath })
        d.update({ "upload_dt" : self.upload_dt })
        return d

class DataTable():

    def __init__(self, d, cols):
        self.draw  = int(d["draw"])
        self.start = int(d["start"])
        self.length = int(d["length"])
        self.trueLength = -1
        self.searchValue = d["search[value]"]
        self.searchIsRegex = d["search[regex]"]
        self.cols = cols
        self.orderByCol = int(d["order[0][column]"])
        self.orderDirection = d["order[0][dir]"]

        # order variable for use with pythong sorted etc #
        self.orderAsc = self.orderDirection == "asc"

        # oder variable for use with sqlalchemy
        if self.orderAsc:
            self.orderAscDbClass = sqlalchemy.asc
            self.orderAscDbClassReverse = sqlalchemy.asc
        else:
            self.orderAscDbClass = sqlalchemy.desc
            self.orderAscDbClassReverse = sqlalchemy.desc

    def __build(self, results, total, filtered):

        self.cacheResults = results

        count = 0
        resultDicts = [ r.to_dict() for r in results ]

        # data list must have the correct order (same as table scheme) #
        rows = []
        for r in resultDicts:
            singleRow = []
            for key in self.cols:
                singleRow.append(r[key])
            rows.append(singleRow)


        d = dict()
        d.update({ "draw" : self.draw })
        d.update({ "recordsTotal" : total })
        d.update({ "recordsFiltered" :  filtered })
        d.update({ "data" : rows })

        return d

    def get(self, map_uid=None):

        filtered = 0
        total    = 0

        # base query
        query = db.session.query(ParsedReplay)
        if map_uid:
            print("Filter for map: {}".format(map_uid))
            query = query.filter(ParsedReplay.map_uid == map_uid)
            
        total = query.count()
        if self.searchValue:

            # search string (search for all substrings individually #
            filterQuery = query

            for substr in self.searchValue.split(" "):
                searchSubstr = "%{}%".format(substr.strip())
                filterQuery  = filterQuery.filter(ParsedReplay.tags.like(searchSubstr))

            filtered = filterQuery.count()
            results = filterQuery.offset(self.start).limit(self.length).all()

        else:

            query  = query.order_by(self.orderAscDbClassReverse(ParsedReplay.race_time))
            results  = query.offset(self.start).limit(self.length).all()
            filtered = total

        return self.__build(results, total, filtered)

    def get_all_maps(self):

        filtered = 0
        total    = 0

        # base query
        query = db.session.query(Map)
        total = query.count()
        if self.searchValue:

            # search string (search for all substrings individually #
            filterQuery = query

            for substr in self.searchValue.split(" "):
                searchSubstr = "%{}%".format(substr.strip())
                filterQuery  = filterQuery.filter(Map.mapname.like(searchSubstr))

            filtered = filterQuery.count()
            results = filterQuery.offset(self.start).limit(self.length).all()

        else:

            query  = query.order_by(self.orderAscDbClassReverse(Map.mapname))
            results  = query.offset(self.start).limit(self.length).all()
            filtered = total

        return self.__build(results, total, filtered)

def _extracted_login_from_file(fullpath):
    '''Extract a login from a tmnf 2020 replay manually'''
    
    # TODO fix underscores in filenames #
    if "its_a_sheppy" in fullpath:
        login_from_filename = "its_a_sheppy"
    else:
        login_from_filename = os.path.basename(fullpath).split("_")[0]
    with open(fullpath, "rb") as f:
        content = f.read()
        decoded_string = content.decode("ascii", errors="ignore")
        if login_from_filename not in decoded_string:
            raise ValueError("Login indicated by filename does not match login in file")
    return login_from_filename


def replay_from_path(fullpath, uploader=None):
    '''Load a replay from uploaded path'''

    # use ghost wrapper to parse both tmnf and tm2020 #
    ghost = tm2020parser.GhostWrapper(fullpath, uploader)

    # build a database replay from ghost wrapper #
    replay = ParsedReplay(filehash=ghost.filehash,
                        race_time=ghost.race_time,
                        uploader=ghost.uploader,
                        filepath=ghost.fullpath,
                        map_uid=ghost.map_uid,
                        ghost_id=ghost.ghost_id,
                        login=ghost.login,
                        login_uid_tm2020=ghost.login_uid_tm2020,
                        upload_dt=ghost.upload_dt,
                        cp_times=ghost.cp_times,
                        game=ghost.game)
    
    # build database map object from replay #
    m = Map(map_uid=replay.map_uid, mapname=replay.map_uid, game=replay.game)

    # merge the map & commit and return the replay #
    db.session.merge(m)
    db.session.commit()
    return replay

def get_number_of_rank_x(rank):

    rank = int(rank)
    if rank < 1 or rank > 10:
        raise ValueError("Rank query must be between 1 and 10 (was {}".format(rank))

    rank_query = '''SELECT login,COUNT(login)
                    FROM (SELECT dISTINCT login||map_uid as dis, login, map_uid
                            FROM replays r
                            WHERE r.login IN (
                                SELECT login FROM replays r2
                                WHERE r2.map_uid = r.map_uid
                                ORDER BY r2.race_time ASC
                                LIMIT {limit}
                                OFFSET {offset}
                            )
                    )
                  GROUP BY login;'''.format(limit=rank, offset=rank-1)

    sql_query = sqlalchemy.sql.text(rank_query)
    result = db.session.execute(sql_query).all()
    return dict((login, count) for login, count in sorted(result, key=lambda x: x[1], reverse=True))

@app.route("/ranking-overview")
def ranks():

    rank_dict = {
        1 : get_number_of_rank_x(1),
        2 : get_number_of_rank_x(2),
        3 : get_number_of_rank_x(3),
    }
    return flask.render_template("rank-info.html", rank_dict=rank_dict)


@app.route("/map-info")
def list():
    player = flask.request.headers.get("X-Forwarded-Preferred-Username")
    header_col = ["Player", "Time", "Date", "Replay"]
    map_uid = flask.request.args.get("map_uid")
    return flask.render_template("map-info.html", header_col=header_col, map_uid=map_uid,
                                    player=player)

@app.route("/")
def mapnames():
    '''Index Location'''

    # TODO list by user
    player = flask.request.headers.get("X-Forwarded-Preferred-Username")
    maps_query = db.session.query(Map).order_by(asc(Map.mapname))

    # limit leaderboard to game #
    game = flask.request.args.get("game")
    if game == "tm2020":
        maps_query = maps_query.filter(Map.game=="tm2020")
    elif game=="tmnf":
        maps_query = maps_query.filter(Map.game!="tm2020")
    else:
        pass

    maps = maps_query.all()

    # FIXME better handling for unwanted maps #
    allowed = ("A", "B", "C", "D", "E", "Fall", "Winter", "Spring", "Summer")
    maps_filtered = filter(lambda m: m.mapname.startswith(allowed), maps)

    return flask.render_template("index.html", maps=maps_filtered, player=player)

@app.route("/open-info")
def openinfo():
    maps = db.session.query(Map).order_by(asc(Map.mapname)).all()
    data = dict()

    for m in maps:

        best_replay = m.get_best_replay()
        player = best_replay.clean_login()
        race_time = best_replay.race_time
        data.update( { m.mapname : { "player" : player, "time" : race_time } } )

    return flask.jsonify(data)

@app.route("/data-source/<path:map_uid>", methods=["POST"])
def source(map_uid):

    # path = map_uid
    dt = DataTable(flask.request.form.to_dict(), ["login", "race_time", "upload_dt", "filepath" ])
    jsonDict = dt.get(map_uid=map_uid)
    return flask.Response(json.dumps(jsonDict), 200, mimetype='application/json')

@app.route("/data-source-index", methods=["POST"])
def index_source(map_uid):

    cols = ["mapname", "personal_"]
    dt = DataTable(flask.request.form.to_dict(), )
    jsonDict = dt.get(map_uid=map_uid)
    return flask.Response(json.dumps(jsonDict), 200, mimetype='application/json')

@app.route("/upload", methods = ['GET', 'POST'])
def upload():

    results = []

    uploader = flask.request.headers.get("X-Forwarded-Preferred-Username")
    if flask.request.method == 'POST':
        #f = flask.request.files['file']
        f_list = flask.request.files.getlist("file[]")
        for f_storage in f_list:
            fname = werkzeug.utils.secure_filename(f_storage.filename)
            fullpath = os.path.join("uploads/", fname)
            f_storage.save(fullpath)
            try:
                replay = replay_from_path(fullpath, uploader=uploader)
                db.session.add(replay)
                db.session.commit()
                check_replay_trigger(replay)
            except ValueError as e:
                results += [(fname, str(e))]
                continue
            except sqlalchemy.exc.IntegrityError as e:
                results += [(fname, str(e.args))]
                db.session.rollback()
                continue

            results += [(fname, None)]

        return flask.render_template("upload-post.html", results=results)

    else:
        return flask.render_template("upload.html")

def check_replay_trigger(replay):

    map_obj = db.session.get(Map).filter(Map.map_uid == replay.map_uid).first()
    assert(map_uid)

    best = map_obj.get_best_replay()
    second = map_obj.get_second_best_replay()

    if replay.filehash != best.filehash:
        return

    if second.uploader == replay.uploader:
        return

    settings = db.session.query(UserSettings).filter(UserSettings.user == second.uploader).first()
    if settings and settings.notifcations_self:
        notifications.send_notification(app, settings.user, map_obj.map_uid, second, replay)

def create_app():
    db.create_all()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='TM Replay Server',
                        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # general parameters #
    parser.add_argument("-i", "--interface", default="127.0.0.1", help="Interface to listen on")
    parser.add_argument("-p", "--port",      default="5000",      help="Port to listen on")
    args = parser.parse_args()

    # startup #
    with app.app_context():
        create_app()

    app.run(host=args.interface, port=args.port, debug=True)
