import os
from flask import Flask, request
from threading import Thread

from connect import call_exists
from amocrm_webhook.processor import process_webhook_async

app = Flask(__name__)


@app.route("/")
def index():
    return "Бот живой!", 200


@app.route("/amo-webhook", methods=["POST"])
def amo_webhook():
    try:
        form = request.form.to_dict()
        note_id = None
        lead_id = None

        if "leads[note][0][note][id]" in form:
            note_id = int(form.get("leads[note][0][note][id]"))
            lead_id = int(form.get("leads[note][0][note][element_id]"))

        if note_id and lead_id:
            if call_exists(note_id, lead_id):
                print("⚠️ Duplicate webhook ignored")
                return "duplicate", 200

        Thread(
            target=process_webhook_async,
            args=(form, note_id, lead_id)
        ).start()

        return "ok", 200

    except Exception as e:
        print("Webhook error:", e)
        return "error", 500


if __name__ == "__main__":
    app.run(port=5000)
