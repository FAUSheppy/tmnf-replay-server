import sys
import requests

def send_notification(app, target_user, mapname, old_replay, new_replay):
    '''Build notification and handoff to dispatcher'''

    url =  app.config["DISPATCH_SERVER"]

    if not url:
        return

    # send to event dispatcher #
    message = "TM: Record broken on {}\n\n".format(mapname)
    message += "Old time:   {}\n".format(old_replay.get_human_readable_time())
    message += "New time: {}\n".format(new_replay.get_human_readable_time())
    message += "\nby {}".format(new_replay.clean_login())

    payload = { "users": [target_user], "msg" : message }

    url_and_token = "/smart-send?dispatch-access-token={}".format(app.config["DISPATCH_TOKEN"])
    r = requests.post(app.config["DISPATCH_SERVER"] + url_and_token, json=payload)

    if not r.ok:
        msg = "Error handing off notification to dispatch ({} {})".format(r.status_code, r.content)
        print(msg, file=sys.stderr)
