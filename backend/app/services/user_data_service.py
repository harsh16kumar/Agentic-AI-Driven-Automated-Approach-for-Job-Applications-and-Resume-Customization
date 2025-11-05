# backend/app/services/user_data_service.py

import os, json

DATA_DIR = "data"
USER_DATA_PATH = os.path.join(DATA_DIR, "user_data.json")
os.makedirs(DATA_DIR, exist_ok=True)

def load_user_data():
    if os.path.exists(USER_DATA_PATH):
        with open(USER_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_user_data(data):
    with open(USER_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
