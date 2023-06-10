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

    def guess_map(self):
        base = os.path.basename(self.filepath)
        return base.split("_")[1].split(".Replay")[0]

    def get_human_readable_time(self):
        t = datetime.timedelta(microseconds=self.race_time*1000)
        t_string = str(t)
        if t.seconds < 60*60:
            t_string =  t_string[2:]
        return t_string[:-4]

    def __repr__(self):
        return "{time} on {map_n} by {login}/{uploader}".format(
                    time=self.get_human_readable_time(),
                    map_n=self.guess_map(), login=self.login, uploader=self.uploader)

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
            self.orderAscDbClassReverse = sqlalchemy.desc
        else:
            self.orderAscDbClass = sqlalchemy.desc
            self.orderAscDbClassReverse = sqlalchemy.asc

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
    with open(fullpath, "rb") as f:
        content = f.read()
        f_hash = hashlib.sha512(content).hexdigest()

    if not f_hash:
        raise RuntimeError("Missing file hash for some reason")

    replay = ParsedReplay(filehash=f_hash,
                            race_time=ghost.race_time,
                            uploader=uploader,
                            filepath=fullpath,
                            map_uid=ghost.uid,
                            ghost_id=ghost.id,
                            login=ghost.login,
                            upload_dt=datetime.datetime.now().isoformat(),
                            cp_times=",".join(map(str, ghost.cp_times)))

    if uploader in app.config["TRUSTED_UPLOADERS"]:
        m = Map(map_uid=replay.map_uid, mapname=replay.guess_map())
        db.session.merge(m)
        db.session.commit()

    return replay

@app.route("/map")
def list():
    # TODO list maps by mapnames
    # TODO list replays by mapnames
    # TODO list by user
    # TODO show all/show only best
    header_col = ["Player", "Time", "Date", "Replay"]
    map_uid = flask.request.args.get("map_uid")
    return flask.render_template("index.html", header_col=header_col, map_uid=map_uid)

@app.route("/")
def mapnames():

@app.route("/data-source<path:path>", methods=["POST"])
def source():

    # path = map_uid
    dt = DataTable(flask.request.form.to_dict(), ["login", "race_time", "upload_dt", "filepath" ])
    jsonDict = dt.get(path)
    return flask.Response(json.dumps(jsonDict), 200, mimetype='application/json')

@app.route("/upload", methods = ['GET', 'POST'])
def upload():
    if flask.request.method == 'POST':
        #f = flask.request.files['file']
        f_list = flask.request.files.getlist("file[]")
        for f_storage in f_list:
            fname = werkzeug.utils.secure_filename(f_storage.filename)
            fullpath = os.path.join("uploads/", fname)
            f_storage.save(fullpath)
            replay = replay_from_path(fullpath, uploader="sheppy")
            print(replay)
            db.session.add(replay)
            db.session.commit()
        return ("", 204)
    else:
        return flask.render_template("upload.html")

def create_app():
    app.config["TRUSTED_UPLOADERS"] = ["sheppy"]
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
