from flask import Flask
import os
from threading import Thread

app = Flask(__name__)

@app.get("/")
def index():
    return "Bot is running!"

def run_web():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        use_reloader=False,
    )

def start_web():
    Thread(target=run_web, daemon=True).start()
