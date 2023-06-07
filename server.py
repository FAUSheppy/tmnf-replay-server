#!/usr/bin/python3
import os
import flask
import werkzeug
import argparse
import sys
import json
import datetime

from pygbx import Gbx, GbxType

from sqlalchemy import Column, Integer, String, Boolean, or_, and_, asc, desc
from flask_sqlalchemy import SQLAlchemy

app = flask.Flask("TM Friends Replay Server")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLITE_LOCATION") or "sqlite:///sqlite.db"
db = SQLAlchemy(app)

class ParsedReplay(db.Model):

    __tablename__ = "replays"


    replay_id   = Column(Integer, primary_key=True)
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
        return "{time} on {map_n} by {login}/{uploader}".format(time=self.get_human_readable_time(),
                    map_n=self.guess_map(), login=self.login, uploader=self.uploader)

def replay_from_path(fullpath, uploader=None):

    if not fullpath.endswith(".gbx"):
        raise ValueError("Path must be a .gbx file")

    g = Gbx(fullpath)
    ghost = g.get_class_by_id(GbxType.CTN_GHOST)
    if not ghost:
        raise ValueError("No ghost found in GBX file")

    replay = ParsedReplay(replay_id=ghost.id,
                            race_time=ghost.race_time,
                            uploader=uploader,
                            filepath=fullpath,
                            map_uid=ghost.uid,
                            login=ghost.login,
                            upload_dt=datetime.datetime.now().isoformat(),
                            cp_times=",".join(map(str, ghost.cp_times)))

    return replay

@app.route("/")
def list():
    return flask.render_template("index.html")

@app.route("/upload", methods = ['GET', 'POST'])
def upload():
    if flask.request.method == 'POST':
        #f = flask.request.files['file']
        f_list = flask.request.files.getlist("file[]")
        for f_storage in f_list:
            fname = werkzeug.utils.secure_filename(f_storage.filename)
            fullpath = os.path.join("uploads/", fname)
            f_storage.save(fullpath)
            replay = replay_from_path(fullpath)
            print(replay)
            db.session.add(replay)
            db.session.commit()
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
