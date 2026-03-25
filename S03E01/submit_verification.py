import os
import json
import requests
from dotenv import load_dotenv, find_dotenv

def submit():
    load_dotenv(find_dotenv())
    api_key = os.getenv("HUB_API_KEY")
    hub_url = os.getenv("HUB_URL")
    
    if not api_key or not hub_url:
        print("Error: HUB_API_KEY or HUB_URL not found in .env")
        return

    base_dir = "xxx"
    invalid_files_path = os.path.join(base_dir, "invalid_files.json")

    with open(invalid_files_path, 'r') as f:
        invalid_files = json.load(f)
    
    # Clean filenames: remove .json extension
    recheck_list = [f.replace(".json", "") for f in invalid_files]
    
    payload = {
        "apikey": api_key,
        "task": "evaluation",
        "answer": {
            "recheck": recheck_list
        }
    }
    
    print(f"Submitting {len(recheck_list)} files to {hub_url}/verify...")
    try:
        response = requests.post(f"{hub_url}/verify", json=payload)
        print(f"Status Code: {response.status_code}")
        print("Response Body:")
        print(response.text)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    submit()
