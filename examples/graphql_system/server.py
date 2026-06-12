"""
Mock GraphQL flag server — mirrors a real AWS SSM + GraphQL backend.

Simulates the exact query your app fires:
    query GetFeatureFlags {
      featureFlags {
        name
        activeVersion
      }
    }

Flags are stored in-memory here; in production they come from
AWS SSM Parameter Store via your backend resolver.

Run:
    pip install flask
    python server.py
    # → listening on http://localhost:4000/graphql
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Auth token (in production: verify a JWT signed by your IdP)
# Set via: export FLAGSERVER_TOKEN=my-secret-token
# ---------------------------------------------------------------------------
_TOKEN = os.environ.get("FLAGSERVER_TOKEN", "dev-token-change-in-prod")

# ---------------------------------------------------------------------------
# Flag store — simulates SSM Parameter Store contents
#
# Each flag has:
#   activeVersion : the currently live version string
#   complianceStatus : approved | pending | deprecated  (not queried by client
#                      today, but exists on the backend schema — add to your
#                      GraphQL query to unlock FlagBench P3 testing)
#   rolloutPct    : 0.0–1.0 (same — add to unlock P4 testing)
# ---------------------------------------------------------------------------
FLAG_STORE: dict[str, dict] = {
    "creEnabled": {
        "activeVersion":     "enabled",
        "complianceStatus":  "approved",
        "rolloutPct":        1.0,
    },
    "helocEnabled": {
        "activeVersion":     "disabled",
        "complianceStatus":  "approved",
        "rolloutPct":        0.0,
    },
    "loanWriteMode": {
        "activeVersion":     "hybrid",
        "complianceStatus":  "pending",
        "rolloutPct":        0.5,
    },
    "asyncPoolCreation": {
        "activeVersion":     "enabled",
        "complianceStatus":  "approved",
        "rolloutPct":        1.0,
    },
    "remittanceEnabled": {
        "activeVersion":     "enabled",
        "complianceStatus":  "approved",
        "rolloutPct":        1.0,
    },
    "bidsTableVersion": {
        "activeVersion":     "v2",
        "complianceStatus":  "approved",
        "rolloutPct":        1.0,
    },
    "poolFiltersVersion": {
        "activeVersion":     "v1",
        "complianceStatus":  "approved",
        "rolloutPct":        1.0,
    },
}


def _verify_token(auth_header: str | None) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return False
    token = auth_header[len("Bearer "):]
    return hmac.compare_digest(token, _TOKEN)


def _handle_get_feature_flags() -> dict:
    """Returns only name + activeVersion — matches your current client query."""
    return {
        "data": {
            "featureFlags": [
                {"name": name, "activeVersion": meta["activeVersion"]}
                for name, meta in FLAG_STORE.items()
            ]
        }
    }


def _handle_get_feature_flags_full() -> dict:
    """Extended response including compliance and rollout — for FlagBench P3/P4."""
    return {
        "data": {
            "featureFlags": [
                {
                    "name":             name,
                    "activeVersion":    meta["activeVersion"],
                    "complianceStatus": meta["complianceStatus"],
                    "rolloutPct":       meta["rolloutPct"],
                }
                for name, meta in FLAG_STORE.items()
            ]
        }
    }


@app.route("/graphql", methods=["POST"])
def graphql():
    # --- Auth ---
    if not _verify_token(request.headers.get("Authorization")):
        log.warning("Unauthorized request from %s", request.remote_addr)
        return jsonify({"errors": [{"message": "Unauthorized"}]}), 401

    body = request.get_json(silent=True)
    if not body or "query" not in body:
        return jsonify({"errors": [{"message": "Invalid request body"}]}), 400

    query: str = body["query"]
    log.info("GraphQL query received (len=%d)", len(query))

    # Route to handler based on query content
    if "featureFlags" not in query:
        return jsonify({"errors": [{"message": "Unknown query"}]}), 400

    # Return extended response if client requests compliance/rollout fields
    if "complianceStatus" in query or "rolloutPct" in query:
        return jsonify(_handle_get_feature_flags_full())

    return jsonify(_handle_get_feature_flags())


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "flags": len(FLAG_STORE), "ts": time.time()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    log.info("Flag server starting on port %d (debug=%s)", port, debug)
    log.info("Set FLAGSERVER_TOKEN env var before deploying to any non-local environment")
    app.run(host="0.0.0.0", port=port, debug=debug)
