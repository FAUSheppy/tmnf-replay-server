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

    def clean_login(self):
        if "/" in self.login:
            return self.login.split("/")[0]
        else:
            return self.login

    def guess_map(self):
        base = os.path.basename(self.filepath)
        return base.split("_")[1].split(".Replay")[0]

    def get_human_readable_time(self):
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
                    map_n=self.guess_map(), login=self.login)

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

def replay_from_path(fullpath, uploader=None):

    if not fullpath.endswith(".gbx"):
        raise ValueError("Path must be a .gbx file")


    g = Gbx(fullpath)
    ghost = g.get_class_by_id(GbxType.CTN_GHOST)
    if not ghost:
        raise ValueError("No ghost found in GBX file")

    f_hash = None
    mapname_from_filename = os.path.basename(fullpath).split("_")[1].split(".Replay")[0]
    with open(fullpath, "rb") as f:
        content = f.read()
        decoded_string = content.decode("ascii", errors="ignore")
        if mapname_from_filename not in decoded_string:
            raise ValueError("Mapname indicated by filename does not match map in file")
        f_hash = hashlib.sha512(content).hexdigest()

    replay = ParsedReplay(filehash=f_hash,
                            race_time=ghost.race_time,
                            uploader=uploader,
                            filepath=fullpath,
                            map_uid=mapname_from_filename,
                            ghost_id=ghost.id,
                            login=ghost.login,
                            upload_dt=datetime.datetime.now().isoformat(),
                            cp_times=",".join(map(str, ghost.cp_times)))

    m = Map(map_uid=replay.map_uid, mapname=replay.guess_map())
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
    # TODO list by user
    player = flask.request.headers.get("X-Forwarded-Preferred-Username")
    maps = db.session.query(Map).order_by(asc(Map.mapname)).all()
    return flask.render_template("index.html", maps=maps, player=player)

@app.route("/data-source/<path:map_uid>", methods=["POST"])
def source(map_uid):

    # path = map_uid
    dt = DataTable(flask.request.form.to_dict(), ["login", "race_time", "upload_dt", "filepath" ])
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

    app.run(host=args.interface, port=args.port)
