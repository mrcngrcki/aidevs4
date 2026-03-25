import os
import requests
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def send_reactor_command(command: str):
    """
    Sends a command to the reactor control API.
    
    :param command: One of: 'start', 'reset', 'left', 'wait', 'right'.
    :return: Current status of the reactor and the robot.
    """
    if not api_key:
        return "Error: HUB_API_KEY not found in environment."

    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": api_key,
        "task": "reactor",
        "answer": {
            "command": command
        }
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            return f"Request failed with status {e.response.status_code}: {e.response.text}"
        return f"Request failed: {str(e)}"

def run_agent():
    client = OpenAI()
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_reactor_command",
                "description": "Wysyła polecenie do sterownika robota w reaktorze.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["start", "reset", "left", "wait", "right"],
                            "description": "Polecenie dla robota: start (na początek), reset (powrót do startu), left (ruch w lewo), wait (czekaj), right (ruch w prawo)."
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    ]

    system_prompt = """Twoim zadaniem jest doprowadzenie robota do punktu docelowego wewnątrz reaktora.
Robot porusza się po najniższym (5.) wierszu mapy o wymiarach 7 (kolumny) na 5 (wiersze).

MAPA:
- P: Pozycja startowa (Kolumna 1, Wiersz 5)
- G: Punkt docelowy (Kolumna 7, Wiersz 5)
- B: Bloki reaktora (zajmują 2 pola pionowo, poruszają się góra/dół)
- .: Puste pole (bezpieczne)

MECHANIKA:
1. Robot znajduje się zawsze w wierszu 5.
2. Bloki poruszają się tylko wtedy, gdy wydajesz polecenie. 'wait' też przesuwa bloki.
3. Każdy blok zajmuje 2 pola. Jeśli blok zajmuje pole w wierszu 5 w danej kolumnie, nie możesz tam wejść.
4. Twoim celem jest dotarcie do kolumny 7.

STRATEGIA:
- Rozglądaj się po każdym kroku (API zwraca stan mapy).
- Jeśli kolumna po prawej jest bezpieczna (nie ma tam bloku w wierszu 5 i nie zbliża się on), idź w prawo ('right').
- Jeśli ruch w prawo jest niebezpieczny, czekaj ('wait').
- Jeśli czekanie w obecnej kolumnie staje się niebezpieczne (blok zbliża się do wierszu 5), wycofaj się w lewo ('left').

POLECENIA:
- Na początek wyślij 'start'.
- Następnie analizuj mapę i podejmuj decyzje.

W odpowiedzi od narzędzia otrzymasz JSON z opisem sytuacji. Skup się na pozycji robota i położeniu bloków w wierszu 5.
Twoim celem jest dotarcie do (7, 5)."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Zacznij zadanie wysyłając polecenie 'start'."}
    ]

    log_filename = f"reactor_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_filename, "w", encoding="utf-8") as log_file:
        log_file.write(f"--- REACTOR AGENT LOG: {datetime.now()} ---\n")

        print("--- ROZPOCZĘCIE PRACY AGENTA REAKTORA ---")

        for step in range(50):
            step_info = f"\n--- [Krok {step+1}] ---"
            print(step_info)
            log_file.write(step_info + "\n")
            try:
                response = client.chat.completions.create(
                    model="gpt-5-mini", 
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
            except Exception as e:
                err_msg = f"Błąd OpenAI: {e}"
                print(err_msg)
                log_file.write(err_msg + "\n")
                break

            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                if msg.content:
                    agent_text = f"Agent: {msg.content}"
                    print(agent_text)
                    log_file.write(agent_text + "\n")
                else:
                    break
                
                # Jeśli agent sam uzna, że skończył
                if "sukces" in msg.content.lower() or "dotarłem" in msg.content.lower() or "FLG" in msg.content:
                    break
                continue
                
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                call_info = f"> Polecenie: {args.get('command')}"
                print(call_info)
                log_file.write(call_info + "\n")
                
                res = send_reactor_command(**args)
                tool_result = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
                res_info = f"< Status: {tool_result}"
                print(res_info)
                log_file.write(res_info + "\n")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })

                if "G" in tool_result and '"robot_pos": [7, 5]' in tool_result:
                    print("\nCEL OSIĄGNIĘTY!")
                    log_file.write("\nCEL OSIĄGNIĘTY!\n")
                    # Możemy jeszcze raz sprawdzić czy dostaliśmy flagę
                    if "FLG" in tool_result:
                        return

if __name__ == "__main__":
    run_agent()
