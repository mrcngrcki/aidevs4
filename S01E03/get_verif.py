import os
import requests
from dotenv import load_dotenv

load_dotenv()

HUB_API_KEY = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def check_task():
    try:
        payload = {
            "apikey": HUB_API_KEY,
            "task": "proxy"
        }
        res = requests.post(f"{HUB_URL}/verify", json=payload)
        print(f"Response: {res.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response: {e.response.text}")

if __name__ == "__main__":
    check_task()
