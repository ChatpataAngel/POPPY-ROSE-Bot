from flask import Flask, jsonify
from threading import Thread
import os
from waitress import serve

from src.api import register_routes

app = Flask(__name__)
STATE = {"bot_ready": False, "bot_username": ""}

@app.get("/")
def home():
    return jsonify({"service": "POPPY ROSE", "status": "online", "bot_ready": STATE["bot_ready"]})

@app.get("/health")
def health():
    return jsonify({"status": "ok" if STATE["bot_ready"] else "starting", "bot_ready": STATE["bot_ready"]}), 200 if STATE["bot_ready"] else 503

# Dashboard REST API (/api/...) — registered after the core routes.
register_routes(app, STATE)

def run():
    port=int(os.getenv("PORT","10000"))
    serve(app, host="0.0.0.0", port=port, threads=4)

def keep_alive():
    Thread(target=run, name="render-health-server", daemon=True).start()
