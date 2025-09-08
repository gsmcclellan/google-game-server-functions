import os
import time
import json
from typing import Optional
import logging

from flask import Request, jsonify, make_response

import functions_framework
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.cloud.logging_v2 import Client as LoggingClient



PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
ZONE     = os.getenv("ZONE")
TOKEN    = os.getenv("TRIGGER_TOKEN")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")

# Structured logs to stdout in serverless (Cloud Run/Functions)
_logging_client = LoggingClient()
_logging_client.setup_logging()        # installs StructuredLogHandler on root
logger = logging.getLogger(__name__)

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

def log(event: str, severity: str = "INFO", **fields):
    """Emit one-line JSON for Cloud Logging. No functional changes."""
    fields.update({
        "event": event,
        "severity": severity,
        "project": PROJECT,
        "zone": ZONE,
        "ts_ms": int(time.time() * 1000),
    })
    print(json.dumps(fields), flush=True)

@functions_framework.http
def start_vm(request: Request):
    wait = request.args.get("wait", "false").lower() == "true"
    vm_instance = request.args.get("instance")
    log("request.received", method=request.method, wait=wait, origin=request.headers.get("Origin"), instance=vm_instance)

    # CORS preflight
    if request.method == "OPTIONS":
        return _cors(make_response("", 204))

    # Optional shared-secret check (skip if TOKEN not set)
    if TOKEN and request.args.get("token") != TOKEN:
        log("request.rejected",
            reason=f"missing/incorrect token expected={TOKEN} received={request.args.get('token')}",
            method=request.method,
            wait=wait,
            origin=request.headers.get("Origin")
        )
        return _cors(make_response(("unauthorized", 401)))



    compute = build("compute", "v1", cache_discovery=False)

    try:
        inst = compute.instances().get(project=PROJECT, zone=ZONE, instance=vm_instance).execute()
        ip = _external_ip(inst)
        status = inst.get("status", "UNKNOWN")

        if status in ("PROVISIONING", "STAGING", "RUNNING"):
            log("instance.already_running", status=status, ip=ip, instance_id=inst.get("id"))
            resp = jsonify({"started": True, "status": status, "ip": ip})
            return _cors(make_response(resp, 200))

        # Start the instance
        op = compute.instances().start(project=PROJECT, zone=ZONE, instance=vm_instance).execute()
        op_name = op["name"]
        log("compute.start.called", op=op_name)

        if not wait:
            log("compute.start.accepted", op=op_name)
            resp = jsonify({"started": True, "status": "STARTING"})
            return _cors(make_response(resp, 202))

        t0 = time.time()
        # Poll the zonal operation until DONE
        while True:
            o = compute.zoneOperations().get(project=PROJECT, zone=ZONE, operation=op_name).execute()
            if o.get("status") == "DONE":
                break
            time.sleep(3)

        log("compute.start.done",
            status = inst.get("status"),
            ip = ip,
            instance_id = inst.get("id"),
            elapsed_ms = int((time.time() - t0) * 1000)
        )

        resp = jsonify({"started": True, "status": inst.get("status"), "ip": ip})
        return _cors(make_response(resp, 200))

    except HttpError as e:
        log("compute.error", severity="ERROR", http_code=int(code), message=str(msg))
        code = getattr(e, "status_code", None) or getattr(e.resp, "status", 500)
        msg = getattr(e, "reason", str(e))
        return _cors(make_response((f"compute api error: {msg}", int(code))))
