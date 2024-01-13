import sys
import requests

def send_notification(app, target_user, mapname, old_replay, new_replay):
    '''Build notification and handoff to dispatcher'''

    url =  app.config["DISPATCH_SERVER"]

    # send to event dispatcher #
    message = "Trackmania: Record broken on {}".format(mapname)
    message += "Old time: {}".format(old_replay.get_human_readable_time())
    message += "New time: {}".format(new_replay.get_human_readable_time())
    message += "by {}".format(new_replay.clean_login())

    payload = { "users": [user], "msg" : message }

    r = requests.post(app.config["DISPATCH_SERVER"] + "/smart-send",
                    json=payload, auth=app.config["DISPATCH_AUTH"])

    if not r.ok:
        print("Error handing off notification to dispatch ({})".format(r.status_code), file=sys.stderr)
