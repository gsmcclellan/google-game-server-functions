import os
import time
from typing import Optional
from flask import Request, jsonify, make_response
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import functions_framework

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
INSTANCE = os.getenv("INSTANCE_NAME")
ZONE     = os.getenv("ZONE")
TOKEN    = os.getenv("TRIGGER_TOKEN")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")

def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return resp

def _external_ip(instance: dict) -> Optional[str]:
    for ni in instance.get("networkInterfaces", []):
        for ac in ni.get("accessConfigs", []):
            ip = ac.get("natIP")
            if ip:
                return ip
    return None

@functions_framework.http
def start_valheim(request: Request):
    """HTTP Cloud Function.
        Args:
            request (flask.Request): The request object.
            <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
        Returns:
            The response text, or any set of values that can be turned into a
            Response object using `make_response`
            <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
        Note:
            For more information on how Flask integrates with Cloud
            Functions, see the `Writing HTTP functions` page.
            <https://cloud.google.com/functions/docs/writing/http#http_frameworks>
    """

    # Print config
    print(f"PROJECT={PROJECT} INSTANCE={INSTANCE} ZONE={ZONE} TOKEN={TOKEN} ALLOWED_ORIGIN={ALLOWED_ORIGIN}")

    # CORS preflight
    if request.method == "OPTIONS":
        return _cors(make_response("", 204))

    # Optional shared-secret check (skip if TOKEN not set)
    if TOKEN and request.args.get("token") != TOKEN:
        return _cors(make_response(("unauthorized", 401)))

    wait = request.args.get("wait", "false").lower() == "true"

    compute = build("compute", "v1", cache_discovery=False)

    try:
        inst = compute.instances().get(project=PROJECT, zone=ZONE, instance=INSTANCE).execute()
        status = inst.get("status", "UNKNOWN")

        if status in ("PROVISIONING", "STAGING", "RUNNING"):
            resp = jsonify({"started": True, "status": status, "ip": _external_ip(inst)})
            return _cors(make_response(resp, 200))

        # Start the instance
        op = compute.instances().start(project=PROJECT, zone=ZONE, instance=INSTANCE).execute()
        op_name = op["name"]

        if not wait:
            resp = jsonify({"started": True, "status": "STARTING"})
            return _cors(make_response(resp, 202))

        # Poll the zonal operation until DONE
        while True:
            o = compute.zoneOperations().get(project=PROJECT, zone=ZONE, operation=op_name).execute()
            if o.get("status") == "DONE":
                break
            time.sleep(3)

        # Fetch final state and IP
        inst = compute.instances().get(project=PROJECT, zone=ZONE, instance=INSTANCE).execute()
        resp = jsonify({"started": True, "status": inst.get("status"), "ip": _external_ip(inst)})
        return _cors(make_response(resp, 200))

    except HttpError as e:
        code = getattr(e, "status_code", None) or getattr(e.resp, "status", 500)
        msg = getattr(e, "reason", str(e))
        return _cors(make_response((f"compute api error: {msg}", int(code))))
