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


    r = requests.post(app.config["DISPATCH_SERVER"] + "/smart-send",
                    json=payload, auth=app.config["DISPATCH_AUTH"])

    if not r.ok:
        print("Error handing off notification to dispatch ({})".format(r.status_code), file=sys.stderr)
