import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

HUB_API_KEY = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def submit_task():
    # Fetch ngrok public URL from local API
    try:
        res = requests.get("http://127.0.0.1:4040/api/tunnels")
        res.raise_for_status()
        tunnels = res.json().get("tunnels", [])
        if not tunnels:
            print("Ngrok not running or no tunnels found.")
            return
        public_url = tunnels[0]["public_url"]
        print(f"Ngrok public URL: {public_url}")
    except Exception as e:
        print(f"Failed to get ngrok URL: {e}")
        return
        
    payload = {
        "apikey": HUB_API_KEY,
        "task": "negotiations",
        "answer": {
            "tools": [
                {
                    "URL": f"{public_url}/api/get_cities_by_item",
                    "description": "Returns a comma-separated list of cities that have the item described in 'params'. You can provide either the natural language item description (e.g. 'potrzebuję kabla 10m') or the item's code. This is the only tool you need to find cities for items."
                }
            ]
        }
    }
    
    print(f"Submitting payload to hub: {payload}")
    
    try:
        res = requests.post(f"{HUB_URL}/verify", json=payload)
        res.raise_for_status()
        print(f"Success! Response: {res.json()}")
        
        # Asynchronous verification
        print("Waiting 60 seconds for the agent to finish negotiations...")
        time.sleep(60)
        
        check_payload = {
            "apikey": HUB_API_KEY,
            "task": "negotiations",
            "answer": {
                "action": "check"
            }
        }
        
        print("Checking result...")
        res = requests.post(f"{HUB_URL}/verify", json=check_payload)
        res.raise_for_status()
        print(f"Final Response: {res.json()}")
        
    except requests.exceptions.RequestException as e:
        print(f"Task failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response: {e.response.text}")

if __name__ == "__main__":
    submit_task()

