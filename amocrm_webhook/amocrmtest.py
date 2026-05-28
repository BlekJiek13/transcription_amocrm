import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from amocrm_webhook.app import app

#   lt --port 5000 --subdomain myamobot/myamobot-python-job13 

if __name__ == "__main__":
    app.run(port=5000)
