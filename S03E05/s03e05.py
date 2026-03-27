import os
import requests
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
API_KEY = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def call_api(url, query):
    """
    Sends a query to a specific API endpoint.
    All tools use the same JSON format: {"apikey": "...", "query": "..."}
    
    :param url: The API endpoint URL (absolute or relative to HUB_URL).
    :param query: The natural language query or keywords (keep it short!).
    :return: JSON response from the API.
    """
    if not API_KEY:
        return {"error": "HUB_API_KEY not found in environment."}
    
    # Handle relative URLs
    if url.startswith("/"):
        url = f"{HUB_URL}{url}"
    elif not url.startswith("http"):
        url = f"{HUB_URL}/api/{url}"
    
    payload = {
        "apikey": API_KEY,
        "query": query
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            return {"error": f"Request failed with status {e.response.status_code}: {e.response.text}"}
        return {"error": f"Request failed: {str(e)}"}

def submit_answer(path_data):
    """
    Submits the final answer to the /verify endpoint.
    
    :param path_data: List of steps, e.g. ["vehicle_name", "right", "up", ...]
    :return: JSON response from the verification API.
    """
    if not API_KEY:
        return {"error": "HUB_API_KEY not found in environment."}
    
    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": API_KEY,
        "task": "savethem",
        "answer": path_data
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            return {"error": f"Verification failed: {e.response.text}"}
        return {"error": f"Verification failed: {str(e)}"}

def run_agent():
    client = OpenAI()
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "call_api",
                "description": "Calls an API tool (maps, wehicles, toolsearch). Keep 'query' SHORTER than 50 chars.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full or relative URL."
                        },
                        "query": {
                            "type": "string",
                            "description": "Keywords like 'Skolwin', 'rocket', 'horse', 'walk', 'car', 'rules'."
                        }
                    },
                    "required": ["url", "query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "submit_answer",
                "description": "Submits the final optimal path. Format: [vehicle, move, ..., 'dismount', move, ...]",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path_data": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "Sequence starting with vehicle, then moves (up, down, left, right), then optional 'dismount' to switch to walk."
                        }
                    },
                    "required": ["path_data"]
                }
            }
        }
    ]
    
    system_prompt = """You are an AI agent tasked with finding the optimal path to Skolwin.
URL for tool discovery: {HUB_URL}/api/toolsearch

MISSION RULES:
1. Discover tools for 'maps' and 'wehicles'.
2. GATHER: 10x10 map, vehicle stats (rocket, horse, walk, car), and traverse rules.
3. CONSTRAINTS: 10 fuel, 10 food. 10x10 grid.
4. MOVEMENT: Standard cardinal directions (up, down, left, right).
5. SWITCHING: You MUST start with a vehicle from the base. You can switch to walking EXCLUSIVELY by inserting 'dismount' into your path list. Once you dismount, you are walking for the rest of the journey.
6. RESOURCE TRADEOFF: Slower modes (walk) use more food (2.5/move). Faster modes (rocket) use more fuel (1.0/move). Car is a compromise (0.7 fuel, 1.0 food).
7. MAP LEGEND: S=Start, G=Goal, W=Water, T=Trees, R=Rocks.
   - TEST terrain crossing by querying vehicle notes or by trial and error in reasoning.
   - If a wall of water blocks you, remember you can 'dismount' to walk over specific tiles if allowed.

MISSION STRATEGY:
1. GATHER DATA:
   - To get the map, you MUST call: call_api(url="/api/maps", query="Skolwin")
   - To get vehicle stats, call: call_api(url="/api/wehicles", query="rocket"), then "horse", "car", "walk".
2. ANALYZE:
   - S = (7,0), G = (4,8). Map is 10x10.
   - Rocket (1.0 fuel, 0.1 food) can go 10 moves. It can cross 'T' but not 'R' or 'W'.
   - Walk (0 fuel, 2.5 food) can cross 'W'.
   - Switch to walk by inserting 'dismount' in your path.
3. EXECUTE:
   - Once you have the map and stats, calculate the 11-move path: (7,0) -> 3 up -> 5 right -> dismount -> 3 right.
   - Submit immediately using `submit_answer`.

IMPORTANT RULES:
- Respond ONLY with tool calls. DO NOT write any text before you have the flag.
- If you fail, adjust your path based on the error message and try again immediately.
- Never give up until you have the flag.
"""





    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I can't find a path on the map. Research specifically if 'T' (Trees) or 'W' (Water) can be crossed by any vehicle. Query /api/maps for 'terrain' and 'symbols'. Also query /api/wehicles about 'terrain' and 'movement'."}
    ]
    
    log_filename = f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_filename, "w", encoding="utf-8") as log_file:
        log_file.write(f"--- SAVETHEM AGENT LOG: {datetime.now()} ---\n\n")
        
        for step in range(30):
            print(f"--- [Step {step+1}] ---")
            log_file.write(f"--- [Step {step+1}] ---\n")
            
            try:
                response = client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
            except Exception as e:
                print(f"OpenAI Error: {e}")
                break
                
            msg = response.choices[0].message
            messages.append(msg)
            
            if not msg.tool_calls:
                if msg.content:
                    print(f"Agent: {msg.content}")
                    log_file.write(f"Agent: {msg.content}\n")
                break
                
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                print(f"> Call: {name}({args})")
                log_file.write(f"> Call: {name}({args})\n")
                
                if name == "call_api":
                    res = call_api(**args)
                elif name == "submit_answer":
                    res = submit_answer(**args)
                else:
                    res = {"error": "Unknown tool."}
                
                res_str = json.dumps(res, ensure_ascii=False)
                print(f"< Result: {res_str}")
                log_file.write(f"< Result: {res_str}\n")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": res_str
                })
                
                if "FLG" in res_str:
                    print("SUCCESS!")
                    return

if __name__ == "__main__":
    run_agent()
