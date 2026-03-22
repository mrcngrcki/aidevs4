import os
import requests
import json
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def send_zmail_action(action: str = "help", **kwargs):
    """
    Służy do interakcji z serwisem pocztowym.
    
    :param action: Akcja, którą chcemy wykonać w serwisie (domyślnie 'help').
    :return: Słownik z odpowiedzią JSON lub tekst w przypadku błędu parsowania JSON.
    """
    if not api_key:
        print("Error: HUB_API_KEY not found in .env")
        return None

    url = f"{HUB_URL}/api/zmail"
    payload = {
        "apikey": api_key,
        "action": action,
    }
    payload.update(kwargs)

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            return response.text
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        if e.response is not None:
            print(f"Response Code: {e.response.status_code}")
            return e.response.text
        return str(e)

def verify_answers(password: str, date: str, confirmation_code: str):
    """
    Wysyła odpowiedź do weryfikacji zadania.
    """
    if not api_key:
        print("Error: HUB_API_KEY not found in .env")
        return None

    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": api_key,
        "task": "mailbox",
        "answer": {
            "password": password,
            "date": date,
            "confirmation_code": confirmation_code
        }
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            return response.text
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        if e.response is not None:
            print(f"Response Code: {e.response.status_code}")
            return e.response.text
        return str(e)


def run_agent():
    client = OpenAI()
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_zmail_action",
                "description": "Narzędzie do analizy skrzynki mailowej. Obsługuje akcje w systemie pocztowym zmail. Zacznij zadanie od użycia akcji 'help', aby poznać możliwe akcje i parametry.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Akcja do wykonania, np. 'help', 'search', 'read'."
                        },
                        "query": {
                            "type": "string",
                            "description": "Zasady wyszukiwania do filtrowania maili, np. z użyciem operatorów from:, to:, subject:, OR, AND."
                        },
                        "id": {
                            "type": "string",
                            "description": "Identyfikator wiadomości do przeczytania, np. w przypadku akcji 'read'."
                        }
                    },
                    "required": ["action"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "verify_answers",
                "description": "Testuje odpowiedź. Kończy poszukiwania jeśli uzyskamy poprawne potwierdzenie.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "password": {
                            "type": "string",
                            "description": "hasło do systemu pracowniczego, które prawdopodobnie nadal znajduje się na tej skrzynce"
                        },
                        "date": {
                            "type": "string",
                            "description": "kiedy (format YYYY-MM-DD) dział bezpieczeństwa planuje atak na naszą elektrownię"
                        },
                        "confirmation_code": {
                            "type": "string",
                            "description": "kod potwierdzenia z ticketa wysłanego przez dział bezpieczeństwa (format: SEC- + 32 znaki = 36 znaków łącznie)"
                        }
                    },
                    "required": ["password", "date", "confirmation_code"]
                }
            }
        }
    ]

    system_prompt = """Jesteś agentem AI analizującym skrzynkę pocztową.
Masz na celu znalezienie i wyodrębnienie trzech konkretnych informacji:
1) date - kiedy (format YYYY-MM-DD) dział bezpieczeństwa planuje atak na naszą elektrownię
2) password - hasło do systemu pracowniczego, które prawdopodobnie nadal znajduje się na tej skrzynce
3) confirmation_code - kod potwierdzenia z ticketa wysłanego przez dział bezpieczeństwa (format: SEC- + 32 znaki = 36 znaków łącznie)

Skrzynka jest cały czas w użyciu - w trakcie Twojej pracy mogą na nią wpływać nowe wiadomości. Musisz to uwzględnić (np. odpytywać ponownie).
Aby przeszukiwać skrzynkę, używaj narzędzia `send_zmail_action`.
Zacznij na początku od wywołania akcji 'help', żeby dostać dalsze instrukcje o tym, jakich komend używać do wyszukiwania (tzw. query) oraz czytania wiadomości.

Wskazówki dodatkowe na start:
- Wiktor wysłał maila z domeny proton.me - nie wymyślaj całego adresu, sprawdź samą domenę
- API pocztowe działa jak wyszukiwarka Gmail - obsługuje operatory from:, to:, subject:, OR, AND w wyszukiwaniu.

Kiedy zgromadzisz wszystkie trzy informacje, wywołaj `verify_answers` i przekaż je w parametrach aby zatwierdzić zadanie. Przeanalizuj odpowiedź, by sprawdzić po prostu, czy się udało - w razie ew. błędu ponów proces z modyfikacjami."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Zacznij zadanie od wysłania akcji 'help'."}
    ]

    for step in range(30):
        print(f"\n--- [Krok {step+1}] Uruchamianie agenta AI ---")
        try:
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
        except Exception as e:
            print(f"Błąd OpenAI: {e}")
            break

        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            print("Odpowiedź asystenta bez wykonania kolejnego narzędzia:", msg.content)
            break
            
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"\n> Agent wywołuje narzędzie: {name} z parametrami: {args}")
            
            if name == "send_zmail_action":
                res = send_zmail_action(**args)
                tool_result = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
            elif name == "verify_answers":
                res = verify_answers(**args)
                tool_result = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
            else:
                tool_result = "Unknown tool"

            print(f"< Wynik narzędzia z serwera: {tool_result}")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(tool_result)
            })

            # Sprawdzenie czy zdobyliśmy flagę :)
            if name == "verify_answers":
                res_str = str(tool_result).lower()
                print(res_str)
                if "flg" in res_str or "poprawna" in res_str or "ok" in res_str or "true" in res_str:
                    print("\nAGENT OTRZYMAŁ POWODZENIE WERYFIKACJI - KOŃCZENIE PRACY.")
                    return

if __name__ == "__main__":
    run_agent()
