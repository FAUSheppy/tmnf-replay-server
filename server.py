#!/usr/bin/python3
import os
import flask
import argparse
import sys
import json

from sqlalchemy import Column, Integer, String, Boolean, or_, and_, asc, desc
from flask_sqlalchemy import

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLITE_LOCATION") or "sqlite:///sqlite.db"

app = flask.Flask("TM Friends Replay Server")
db = SQLAlchemy(app)

class ParsedReplay(db.Model):

    __tablename__ = "replays"


    replay_id   = Column(Integer, primary_key=True)
    race_time   = Column(Integer)

    uploader    = Column(String)
    filepath    = Column(String)
    upload_dt   = Column(String)

    map_uid     = Column(String) # ghost_uid
    ghost_login = Column(String)

    ghost_cp_times = Column(String)

    def get_human_readable_time(self):
        t = datetime.timedelta(seconds=racetime)
        t_string = str(t)
        if t.hours == 0:
            return t_string[2:]
        return t_string

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
                            map_uid=ghost.uid
                            ghost_login=ghost.login,
                            upload_dt=datetime.datetime.now().isoformat(),
                            ghost.cp_times=",".join(ghost.cp_times))

    return replay

@app.route("/")
def list():
    return flask.render_template("index.html")

@app.route("/upload", methods = ['GET', 'POST'])
def upload():
    if flask.request.method == 'POST':
        #f = flask.request.files['file']
        f_list = flask.request.files.getlist("file[]")
        print(f_list)
        return ""
        fname = werkzeug.utils.secure_filename(f.filename)
        fullpath = os.path.join("uploads/", fname)
        f.save(fullpath)
        replay = replay_from_path(fullpath)
        db.add(replay)
        db.commit()
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

    # startup #
    args = parser.parse_args()
    create_app()
    app.run(host=args.interface, port=args.port)
