import os
import requests
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
API_KEY = os.getenv("HUB_API_KEY", os.getenv("API_KEY"))
HUB_URL = os.getenv("HUB_URL")

def send_api_request(answer_payload):
    """
    Sends the action to the Central API for the filesystem task.
    """
    if not API_KEY:
        return {"error": "API key not found in environment."}
    
    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": API_KEY,
        "task": "filesystem",
        "answer": answer_payload
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            return {"error": f"Request failed with status {e.response.status_code}: {e.response.text}"}
        return {"error": f"Request failed: {str(e)}"}

def run_agent():
    client = OpenAI()
    
    # Przekazujemy notatki wprost do promptu by nie komplikowac agenta dodatkowymi toollami do odczytu
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files_content = ""
    for filename in ["README.md", "ogłoszenia.txt", "rozmowy.txt", "transakcje.txt"]:
        path = os.path.join(base_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                files_content += f"\n\n--- Zawartość pliku: {filename} ---\n{content}\n"
        except FileNotFoundError:
            files_content += f"\n\n--- Zawartość pliku: {filename} ---\n(Plik nie istnieje lub nie można go odczytać.)\n"

    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_action",
                "description": "Wysyła pojedynczą instrukcję do serwera (np. reset, help, done, createFile).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": { "type": "string", "description": "Nazwa akcji, np. 'help', 'reset', 'done', 'createFile', 'createDir', 'list', 'move', 'delete'." },
                        "path": { "type": "string", "description": "Ścieżka dla akcji (opcjonalne)." },
                        "content": { "type": "string", "description": "Zawartość dla createFile (opcjonalne)." },
                        "newPath": { "type": "string", "description": "Nowa ścieżka dla move (opcjonalne)." }
                    },
                    "required": ["action"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_batch_actions",
                "description": "Wysyła wiele instrukcji do serwera hurtowo w jednym requeście.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actions": {
                            "type": "array",
                            "description": "Lista obiektów akcji.",
                            "items": {
                                "type": "object",
                                "additionalProperties": True
                            }
                        }
                    },
                    "required": ["actions"]
                }
            }
        }
    ]
    
    system_prompt = f"""Jesteś Agentem AI Dowódcą (Filesystem Agent). Twoim zadaniem jest stworzenie na serwerze wirtualnego systemu plików zgodnie z poleceniem z centrali.
Zarządzasz systemem plików przez API za pomocą dostarczonych narzędzi `send_action` oraz `send_batch_actions`.

Zasady:
1. Rozpocznij od wysłania `send_action(action='help')`, aby poznać komendy API.
2. Następnie wykonaj `send_action(action='reset')`, by oczyścić strukturę filesystemu.
3. Musisz stworzyć katalogi `/miasta`, `/osoby` oraz `/towary` (korzystając z wniosków z notatek poniżej).
4. Do analizy masz poniższe dane zebrane przez Natana. Zastanów się kto zarządza miastami, kto co potrzebuje i czego chce, a co kto oferuje na sprzedaż.

STRUKTURA:
- Katalog /miasta: pliki o nazwie miast w mianowniku (bez polskich znaków, np. Gdansk). Zawartość: JSON z towarami których miasto POTRZEBUJE (klucz=towar, wartość=liczba). Przykład: {{"chleb": 10}}
- Katalog /osoby: pliki z imionami i nazwiskami (np. Jan_Kowalski). Zawartość: link markdownowy do miasta, np. `[Gdansk](/miasta/Gdansk)`.
- Katalog /towary: pliki dla towarów które miasto SPRZEDAJE. Nazwa pliku to towar w mianowniku l.poj (np. `cegla`). Zawartość: link markdownowy do miasta oferującego go: `[Gdansk](/miasta/Gdansk)`.
- ABSOLUTNY ZAKAZ używania polskich znaków w nazwach plików oraz w polach w JSON. Zamień wszystkie znaki na ASCII.

<NOTATKI>
{files_content}
</NOTATKI>

Twoim celem ostatecznym jest wywołanie `send_action(action='done')`. Korzystaj z `send_batch_actions` do dodawania wielu plików na raz."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Zaczynaj. Krok pierwszy: pobierz `help`. Potem `reset`. Potem cała struktura i na koniec `done`."}
    ]
    
    log_filename = os.path.join(base_dir, f"agent_log_filesystem_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(log_filename, "w", encoding="utf-8", buffering=1) as log_file:
        log_file.write(f"--- FILESYSTEM AGENT LOG: {datetime.now()} ---\n\n")
        
        for step in range(50):
            print(f"--- [Step {step+1}] ---")
            log_file.write(f"--- [Step {step+1}] ---\n")
            
            try:
                response = client.chat.completions.create(
                    model="gpt-5-mini",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
            except Exception as e:
                print(f"OpenAI Error: {e}")
                log_file.write(f"OpenAI Error: {e}\n")
                break
                
            msg = response.choices[0].message
            messages.append(msg)
            
            if not msg.tool_calls:
                if msg.content:
                    print(f"Agent: {msg.content}")
                    log_file.write(f"Agent: {msg.content}\n")
                if "FLG" in msg.content:
                    break
                
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    name = tool_call.function.name
                    args_str = tool_call.function.arguments
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}
                    
                    print(f"> Call: {name}({args_str})")
                    log_file.write(f"> Call: {name}({args_str})\n")
                    
                    if name == "send_action":
                        res = send_api_request(args)
                    elif name == "send_batch_actions":
                        actions = args.get("actions", [])
                        res = send_api_request(actions)
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
                    
                    if "FLG{" in res_str:
                        print("SUCCESS! Got the flag from API.")
                        return

if __name__ == "__main__":
    run_agent()
