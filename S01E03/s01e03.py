import os
import requests
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
        
    session_id = "proxy-test-session-12345"
    
    payload = {
        "apikey": HUB_API_KEY,
        "task": "proxy",
        "answer": {
            "url": f"{public_url}/api/chat",
            "sessionID": session_id
        }
    }
    
    print(f"Submitting payload to hub: {payload}")
    
    try:
        res = requests.post(f"{HUB_URL}/verify", json=payload)
        res.raise_for_status()
        print(f"Success! Response: {res.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Submission failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response: {e.response.text}")

if __name__ == "__main__":
    submit_task()
