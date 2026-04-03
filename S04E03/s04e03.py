import os
import requests
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
API_KEY = os.getenv("HUB_API_KEY", os.getenv("API_KEY"))
HUB_URL = os.getenv("HUB_URL")

def send_action(answer_payload):
    """
    Sends the action to the Central API for the domatowo task.
    """
    if not API_KEY:
        return {"error": "API key not found in environment."}
    
    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": API_KEY,
        "task": "domatowo",
        "answer": answer_payload
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        # response.raise_for_status() # Not raising here as errors give useful agent feedback
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            return {"error": f"Request failed with status {e.response.status_code}: {e.response.text}"}
        return {"error": f"Request failed: {str(e)}"}

def run_agent():
    client = OpenAI()
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_action",
                "description": "Wysyła akcję do serwera. Argument 'answer' to obiekt JSON, np. {\"action\": \"help\"}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "answer": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "Obiekt reprezentujący 'answer' (np. {\"action\": \"getMap\"}). Możesz dodawać dodatkowe klucze wymagane do akcji."
                        }
                    },
                    "required": ["answer"]
                }
            }
        }
    ]
    
    system_prompt = """Jesteś Agentem AI Dowódcą (Rescue Agent). Twoim zadaniem jest odnalezienie partyzanta ukrywającego się w ruinach Domatowa i ewakuacja go helikopterem.
Komunikujesz się z API centrali WYŁĄCZNIE za pomocą narzędzia `send_action`.

Kontekst:
"Przeżyłem. Bomby zniszczyły miasto. Żołnierze tu byli, szukali surowców, zabrali ropę. Teraz est pusto. Mam broń, jestem ranny. Ukryłem się w jednym z najwyższych bloków. Nie mam jedzenia. Pomocy."

Zasady misji:
1. Rozpocznij od wysłania `{ "action": "help" }` by poznać wszystkie możliwe parametry i komendy.
2. Zdobądź mapę za pomocą `{ "action": "getMap" }`. Rozwiązuj zadanie analizując tę mapę.
3. Limit punktów akcji: 300.
   - utworzenie zwiadowcy (scout): 5 AP
   - utworzenie transportera: 5 AP (baza) + 5 AP za każdego zwiadowcę
   - ruch zwiadowcy (foot): 7 AP / pole
   - ruch transportera (tylko po ulicach): 1 AP / pole
   - inspekcja pola: 1 AP
   - wysadzenie zwiadowców z transportera: 0 AP
4. Transportery tworzy się np.: `{ "action": "create", "type": "transporter", "passengers": 2 }`
5. Zwiadowcę tworzy się np.: `{ "action": "create", "type": "scout" }`
6. Helikopter wezwać można tylko po znalezieniu partyzanta, np.: `{ "action": "callHelicopter", "destination": "F6" }`
7. Przeszukuj mapę rozważnie, żeby nie "przepalić" punktów. Dowiedz się najpierw z `getMap` i `help`, a potem zaplanuj zwiadowców. Transporterem dojeżdżasz szybciej.
8. Używaj komend inspekcji terenowych (inspect) oraz analizuj np. getLogs.

Kroki postępowania:
- Za każdym razem dostaniesz odpowiedź API w formacie JSON (albo błąd).
- Czytaj błędy (np. zły format), bardzo szybko naprawiaj i próbuj jeszcze raz. Błędy często dają wskazówki jak ułożyć JSON komendy!
- Zmiana strategii jest zalecana jeśli jakaś akcja się nie powodzi.
- Działaj szybko. Odpowiadaj bezpośrednio Tool Callami. Masz do rozwiązania to samodzielnie poprzez to narzędzie.
- Po znalezieniu i wezwaniu helikoptera serwer zwróci FLAGĘ. Kiedy zobaczysz "FLG:", misja kończy się sukcesem.
- Oczekujemy odpowiedzi na zadanie "domatowo". `send_action` układa automatycznie body, Ty musisz tylko podać sam "answer".
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Rozpocznij misję. Wywołaj najpierw `help` i `getMap`, a potem krok po kroku uratuj partyzanta!"}
    ]
    
    log_filename = f"agent_log_domatowo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_filename, "w", encoding="utf-8") as log_file:
        log_file.write(f"--- DOMATOWO AGENT LOG: {datetime.now()} ---\n\n")
        
        for step in range(100): # max 100 limit step
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
                break
                
            msg = response.choices[0].message
            messages.append(msg)
            
            if not msg.tool_calls:
                if msg.content:
                    print(f"Agent: {msg.content}")
                    log_file.write(f"Agent: {msg.content}\n")
                if "FLG" in msg.content or "FLAG" in msg.content or "flg" in msg.content.lower():
                    print("Mission complete!")
                    break
                print("No tool calls, waiting for agent to resume.")
                
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
                        answer_dict = args.get("answer", {})
                        if isinstance(answer_dict, str):
                            try:
                                answer_dict = json.loads(answer_dict)
                            except:
                                pass
                        res = send_action(answer_dict)
                    else:
                        res = {"error": "Unknown tool."}
                    
                    try:
                        res_str = json.dumps(res, ensure_ascii=False)
                    except:
                        res_str = str(res)
                        
                    print(f"< Result: {res_str}")
                    log_file.write(f"< Result: {res_str}\n")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": res_str
                    })
                    
                    if "FLG{" in res_str or "{{FLG" in res_str or "flag" in res_str.lower():
                        print("SUCCESS! Got the flag from API.")
                        return

if __name__ == "__main__":
    run_agent()
