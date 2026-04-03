import os
import requests
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
API_KEY = os.getenv("HUB_API_KEY", os.getenv("API_KEY"))
HUB_URL = os.getenv("HUB_URL")
TASK_NAME = "foodwarehouse"
FOOD4CITIES_URL = f"{HUB_URL}/dane/food4cities.json"


def send_api_request(answer_payload: dict) -> dict:
    """
    Wysyła żądanie do API Centrali dla zadania foodwarehouse.
    answer_payload to zawartość pola "answer" w JSON.
    """
    if not API_KEY:
        return {"error": "API key not found in environment."}

    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": API_KEY,
        "task": TASK_NAME,
        "answer": answer_payload
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except requests.exceptions.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            return {"error": f"Request failed with status {e.response.status_code}: {e.response.text}"}
        return {"error": f"Request failed: {str(e)}"}


def fetch_food4cities() -> dict:
    """
    Pobiera plik z zapotrzebowaniem miast.
    """
    try:
        response = requests.get(FOOD4CITIES_URL, timeout=30)
        return response.json()
    except Exception as e:
        return {"error": f"Failed to fetch food4cities.json: {str(e)}"}


def run_agent():
    client = OpenAI()
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Pobierz plik z zapotrzebowaniem miast z góry i przekaż do promptu
    print("Pobieranie pliku food4cities.json...")
    food4cities_data = fetch_food4cities()
    food4cities_str = json.dumps(food4cities_data, ensure_ascii=False, indent=2)
    print(f"Dane z food4cities.json:\n{food4cities_str}\n")

    # Narzędzia z płaską strukturą parametrów – model nie gubi pola "answer"
    tools = [
        {
            "type": "function",
            "function": {
                "name": "warehouse_api",
                "description": (
                    "Wywołuje API magazynu żywności. "
                    "Parametr 'tool' określa operację: help, reset, orders, database, signatureGenerator, done. "
                    "Pozostałe parametry zależą od wybranego narzędzia i są opcjonalne."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "enum": ["help", "reset", "orders", "database", "signatureGenerator", "done"],
                            "description": "Nazwa narzędzia API do wywołania."
                        },
                        "action": {
                            "type": "string",
                            "enum": ["get", "create", "append", "delete"],
                            "description": "Akcja dla narzędzia 'orders': get, create, append lub delete."
                        },
                        "title": {
                            "type": "string",
                            "description": "Tytuł zamówienia (dla orders.create)."
                        },
                        "creatorID": {
                            "type": "integer",
                            "description": "ID twórcy zamówienia (dla orders.create). Pobierz z bazy danych."
                        },
                        "destination": {
                            "type": "string",
                            "description": "Kod docelowy zamówienia (dla orders.create). Pobierz z bazy danych."
                        },
                        "signature": {
                            "type": "string",
                            "description": "Podpis SHA1 zamówienia (dla orders.create). Wygeneruj przez signatureGenerator."
                        },
                        "id": {
                            "type": "string",
                            "description": "ID zamówienia (dla orders.append / orders.delete)."
                        },
                        "name": {
                            "type": "string",
                            "description": "Nazwa pojedynczego towaru (alternatywa dla 'items' w orders.append)."
                        },
                        "items": {
                            "oneOf": [
                                {
                                    "type": "integer",
                                    "description": "Ilość towaru, gdy podajesz 'name' (pojedynczy towar)."
                                },
                                {
                                    "type": "object",
                                    "description": "Słownik {nazwa_towaru: ilość} dla batch append wielu towarów naraz.",
                                    "additionalProperties": {"type": "integer"}
                                }
                            ],
                            "description": "Towary do dopisania do zamówienia (dla orders.append)."
                        },
                        "query": {
                            "type": "string",
                            "description": "Zapytanie SQL lub 'show tables' (dla tool='database')."
                        }
                    },
                    "required": ["tool"],
                    "additionalProperties": True
                }
            }
        }
    ]

    system_prompt = f"""Jesteś Agentem AI Magazyniera (Foodwarehouse Agent). Twoim zadaniem jest przygotowanie zamówień żywności i narzędzi dla wskazanych miast.

Masz dostęp do narzędzia `warehouse_api`, które obsługuje wszystkie operacje API.

=== DANE WEJŚCIOWE (food4cities.json) ===
{food4cities_str}

=== PLAN DZIAŁANIA (wykonuj krok po kroku) ===

KROK 1: Pobierz dokumentację API
  warehouse_api(tool="help")
  → Zapamiętaj dokładne pole(a) wymagane przez signatureGenerator

KROK 2: Zresetuj stan zadania
  warehouse_api(tool="reset")

KROK 3: Poznaj strukturę bazy danych
  warehouse_api(tool="database", query="show tables")
  → Dla każdej tabeli wykonaj: warehouse_api(tool="database", query="select * from <tabela>")
  → Zidentyfikuj:
    a) creatorID – ID użytkownika do tworzenia zamówień
    b) destination – kody docelowe dla każdego z 8 miast
    c) dane potrzebne do signatureGenerator (zgodnie z dokumentacją z help)

KROK 4: Dla każdego z 8 miast z food4cities.json utwórz zamówienie:
  a) Wygeneruj podpis:
     warehouse_api(tool="signatureGenerator", <pola z bazy danych wg dokumentacji help>)
  b) Utwórz zamówienie:
     warehouse_api(tool="orders", action="create", title="Dostawa dla <miasto>",
                   creatorID=<ID>, destination="<kod>", signature="<sha1>")
  c) Dopisz towary (BATCH – wszystkie naraz):
     warehouse_api(tool="orders", action="append", id="<id_zamowienia>",
                   items={{"<towar>": <ilość>, ...}})

KROK 5: Zakończ i odbierz flagę
  warehouse_api(tool="done")

=== ZASADY ===
- Musisz utworzyć DOKŁADNIE 8 zamówień (po jednym dla każdego miasta z JSON)
- Ilości towarów muszą być DOKŁADNE jak w food4cities.json – bez braków i nadmiarów
- Użyj batch mode (items jako obiekt) przy append, żeby ograniczyć liczbę requestów
- Każde zamówienie musi mieć poprawny creatorID, destination i signature
- Jeśli zepsujesz stan, wywołaj warehouse_api(tool="reset") i zacznij od nowa
- NIE twórz zamówień dopóki nie masz wszystkich danych z bazy i dokumentacji help
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Zaczynaj! Wykonaj plan krokowo:\n"
                "1. help → 2. reset → 3. eksploruj bazę danych → "
                "4. utwórz 8 zamówień z poprawnymi podpisami i towarami → 5. done"
            )
        }
    ]

    log_filename = os.path.join(base_dir, f"agent_log_foodwarehouse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(log_filename, "w", encoding="utf-8", buffering=1) as log_file:
        log_file.write(f"--- FOODWAREHOUSE AGENT LOG: {datetime.now()} ---\n\n")
        log_file.write(f"food4cities.json:\n{food4cities_str}\n\n")

        for step in range(100):
            print(f"\n--- [Step {step + 1}] ---")
            log_file.write(f"\n--- [Step {step + 1}] ---\n")

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
                if msg.content and "FLG" in msg.content:
                    print("\n=== SUKCES! Flaga znaleziona! ===")
                    break
                # Brak tool calls i brak flagi – agent zakończył
                print("Agent zakończył pracę (brak tool calls).")
                break

            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args_str = tool_call.function.arguments
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}

                print(f"> Call: {name}({args_str})")
                log_file.write(f"> Call: {name}({args_str})\n")

                if name == "warehouse_api":
                    # Przekazujemy cały args jako answer – wszystkie pola płasko
                    res = send_api_request(args)
                else:
                    res = {"error": f"Unknown tool: {name}"}

                res_str = json.dumps(res, ensure_ascii=False)
                print(f"< Result: {res_str}")
                log_file.write(f"< Result: {res_str}\n")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": res_str
                })

                if "FLG{" in res_str:
                    print("\n=== SUKCES! Flaga znaleziona w odpowiedzi API! ===")
                    print(f"Flaga: {res_str}")
                    log_file.write(f"\n=== SUKCES! Flaga: {res_str} ===\n")
                    return

    print(f"\nLog zapisany do: {log_filename}")


if __name__ == "__main__":
    run_agent()
