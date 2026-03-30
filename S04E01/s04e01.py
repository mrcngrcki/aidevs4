import os
import requests
import json
from datetime import datetime
from openai import OpenAI
from bs4 import BeautifulSoup
from dotenv import load_dotenv, find_dotenv
import re

load_dotenv(find_dotenv())
API_KEY = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def call_verify_api(answer_payload=None):
    """
    Sends a payload as the 'answer' field to the /verify endpoint for the task 'okoeditor'.
    
    :param answer_payload: A dictionary representing the answer object.
    :return: JSON response from the verify API.
    """
    if answer_payload is None:
        answer_payload = {}
    if not API_KEY:
        return {"error": "HUB_API_KEY not found in environment."}
    
    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": API_KEY,
        "task": "okoeditor",
        "answer": answer_payload
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            try:
                return e.response.json()
            except:
                return {"error": f"Request failed with status {e.response.status_code}: {e.response.text}"}
        return {"error": f"Request failed: {str(e)}"}

def fetch_oko_panel(page):
    """
    Fetches text and IDs from the OKO web panel pages.
    """
    session = requests.Session()
    # Simple login
    session.post("https://oko.ag3nts.org/", data={
        "login": "Zofia", 
        "password": "Zofia2026!",
        "access_key": API_KEY,
        "action": "login"
    })
    res = session.get(f"https://oko.ag3nts.org/{page}")
    if res.status_code != 200:
        return {"error": f"Failed to fetch {page}, status code {res.status_code}"}
    
    soup = BeautifulSoup(res.text, "html.parser")
    # If the user asks for a specific subpage, just return all the text
    if "/" in page:
        return {"data": soup.get_text(separator=" ", strip=True)}
        
    results = []
    # Identify items with IDs correctly
    # Return all items with their IDs so the agent can choose what to edit or overwrite
    for a in soup.find_all('a', href=True):
        match = re.search(r'[a-f0-9]{32}', a['href'])
        if match:
            text = a.get_text(separator=" ", strip=True)
            results.append(f"Content: {text[:2000]} | ID: {match.group(0)}")
    
    if not results:
        return {"data": "No relevant entries found for Skolwin or Komarowo on this page."}
    
    return {"data": results}

def run_agent():
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "call_verify_api",
                "description": "Call the central /verify API for the okoeditor task. Pass a JSON object `answer_payload` that will be sent as the `answer` field.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "answer_payload": {
                            "type": "object",
                            "description": "The payload dictionary to send inside the 'answer' field. Start with {'action': 'help'} and use other actions as discovered."
                        }
                    },
                    "required": ["answer_payload"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_oko_panel",
                "description": "Fetch data and record IDs from the OKO web panel. Use 'incydenty', 'notatki', or 'zadania' to list records and their IDs. To view the full text of a specific record (e.g. to read a full note), pass 'notatki/ID', 'incydenty/ID', or 'zadania/ID'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page": {
                            "type": "string",
                            "description": "The page to scrape, e.g. 'incydenty', 'notatki', 'zadania', or specific record like 'notatki/380792b2c86d9c5be670b3bde48e187b'"
                        }
                    },
                    "required": ["page"]
                }
            }
        }
    ]
    
    system_prompt = """You are an AI agent designed to edit the OKO Central system through a backdoor API.
Your task is: okoeditor

OBJECTIVES TO COMPLETE:
1. Zmień klasyfikację raportu o mieście Skolwin tak, aby nie był to raport o widzianych pojazdach i ludziach, a o zwierzętach.
2. Na liście zadań znajdź zadanie związane z miastem Skolwin i oznacz je jako wykonane. W jego treści wpisz, że widziano tam jakieś zwierzęta np. bobry.
3. Musimy przekierować uwagę operatorów na inne, niezamieszkałe miasto, aby ocalić Skolwin. Spraw więc, aby na liście incydentów pojawił się raport o wykryciu ruchu ludzi w okolicach miasta Komarowo.
4. Gdy to wszystko wykonasz, wywołaj akcję 'done' (np. {'action': 'done'}).

INSTRUCTIONS:
- You must interact with the API using the `call_verify_api` tool.
- START by calling `call_verify_api(answer_payload={"action": "help"})` to discover the schema and commands you can use.
- Use `fetch_oko_panel` tool to read the pages ('incydenty', 'notatki', 'zadania') and find the 32-character hex IDs.
- To understand the correct ticket codes (e.g. RECO vs MOVE), you MUST read the full text of the 'Metody kodowania incydentów' note by fetching its specific URL page using `fetch_oko_panel` (e.g. 'notatki/ID').
- If you need to add a report for Komarowo but there is no such incident, you MUST overwrite one of the existing incidents (choose one that is NOT about Skolwin).
- After discovering the schema and getting the IDs, fulfill the objectives one by one using the appropriate actions.
- IMPORTANT: You cannot edit the system manually. ONLY use `call_verify_api`.
- Respond ONLY with tool calls. Do not output text until the final objective is complete and you receive the flag.
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Fetch the initial help instructions and proceed to complete the objectives."}
    ]
    
    log_filename = f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_filename, "w", encoding="utf-8") as log_file:
        log_file.write(f"--- OKOEDITOR AGENT LOG: {datetime.now()} ---\n\n")
        
        for step in range(30):
            print(f"--- [Step {step+1}] ---")
            log_file.write(f"--- [Step {step+1}] ---\n")
            
            try:
                response = client.chat.completions.create(
                    model="gpt-5.4",
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
                if "FLG" in (msg.content or ""):
                    print("SUCCESS!")
                    return
                # If there are no tool calls, it might have finished or waiting. Let's break or ask to continue.
                messages.append({"role": "user", "content": "Please continue with tool calls if you haven't received the flag yet."})
                continue
                
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                # Parse arguments
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    print("Error parsing tool arguments.")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"error": "Invalid JSON in arguments passed to tool."})
                    })
                    continue

                print(f"> Call: {name}({args})")
                log_file.write(f"> Call: {name}({args})\n")
                
                if name == "call_verify_api":
                    if "answer_payload" in args:
                        res = call_verify_api(args["answer_payload"])
                    else:
                        res = call_verify_api(args)
                elif name == "fetch_oko_panel":
                    res = fetch_oko_panel(**args)
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
                
                if "FLG" in res_str or "flag" in res_str.lower() or "flg" in res_str.lower():
                    print("MIGHT BE SUCCESS!")

if __name__ == "__main__":
    run_agent()
