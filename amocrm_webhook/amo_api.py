import json
from datetime import datetime

import requests

from config import AMO_DOMAIN, API_TOKEN_AMO


def get_lead_info_rest(lead_id: int):
    headers = {
        "Authorization": f"Bearer {API_TOKEN_AMO}",
        "Content-Type": "application/json",
    }

    base_url = f"https://{AMO_DOMAIN}.amocrm.ru/api/v4"
    lead_url = f"{base_url}/leads/{lead_id}?with=contacts"
    lead_resp = requests.get(lead_url, headers=headers)

    if lead_resp.status_code != 200:
        print(f"❌ Ошибка при получении сделки: {lead_resp.status_code}")
        print(lead_resp.text)
        return

    lead = lead_resp.json()

    print("\n=== 💼 Информация о сделке ===")
    print(f"ID: {lead.get('id')}")
    print(f"Название: {lead.get('name')}")
    print(f"Бюджет: {lead.get('price')}")
    print(f"Дата создания: {datetime.fromtimestamp(lead.get('created_at'))}")
    print(f"Дата обновления: {datetime.fromtimestamp(lead.get('updated_at'))}")
    print(f"Статус ID: {lead.get('status_id')}")
    print(f"Воронка ID: {lead.get('pipeline_id')}")
    print(f"Ответственный ID: {lead.get('responsible_user_id')}")


def post_note_lead_rest(lead_id: int, note_text: str):
    url = f"https://{AMO_DOMAIN}.amocrm.ru/api/v4/leads/{lead_id}/notes"

    headers = {
        "Authorization": f"Bearer {API_TOKEN_AMO}",
        "Content-Type": "application/json",
    }

    payload = [
        {
            "note_type": "common",
            "params": {
                "text": note_text
            }
        }
    ]

    response = requests.post(url, headers=headers, data=json.dumps(payload))

    if response.status_code in (200, 201):
        print("Примечание успешно добавлено в сделку.")
    else:
        print("Ошибка добавления примечания:", response.status_code, response.text)

    return response


def is_lead_add(form):
    return any(key.startswith("leads[add]") for key in form.keys())


def is_lead_note(form):
    return any(key.startswith("leads[note]") for key in form.keys())
