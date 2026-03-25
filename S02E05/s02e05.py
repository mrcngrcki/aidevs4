import os
import requests
import json
import re
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def scrape_drone_docs():
    """Pobiera i parsuje instrukcję ze strony z dokumentacją drona."""
    url = f"{HUB_URL}/dane/drone.html"
    print(f"Pobieranie dokumentacji z {url}...")
    resp = requests.get(url)
    resp.raise_for_status()
    
    html_content = resp.text
    # Proste czyszczenie z tagów by wyciągnąć czytelny tekst dla LLM
    text_content = re.sub(r'<style.*?</style>', ' ', html_content, flags=re.DOTALL)
    text_content = re.sub(r'<script.*?</script>', ' ', text_content, flags=re.DOTALL)
    text_content = re.sub(r'<[^>]+>', ' ', text_content)
    text_content = re.sub(r'\s{2,}', ' ', text_content)
    
    return text_content.strip()

def send_drone_instructions(instructions: list):
    """
    Wysyła listę instrukcji do drona poprzez API.
    """
    if not api_key:
        print("Error: HUB_API_KEY not found in .env")
        return None

    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": api_key,
        "task": "drone",
        "answer": {
            "instructions": instructions
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
    
    # 1. Pobieramy dokumentację API
    drone_docs = scrape_drone_docs()
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_drone_instructions",
                "description": "Wysyła instrukcje do drona. Przyjmuje tablicę instrukcji wg dokumentacji API. Np. ['set(4,2)', 'set(destroy)']. Zawsze modyfikuj instrukcje na podstawie błędów zwracanych przez tę funkcję.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instructions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Lista komend dla drona."
                        }
                    },
                    "required": ["instructions"]
                }
            }
        }
    ]

    system_prompt = f"""Jesteś agentem w szkoleniu edukacyjnym typu CTF - Capture The Flag - sterującym dronem DRN-BMB7.
Twoim celem jest zniszczenie pola o koordynatach sektor_x=2, sektor_y=4 (z reguły np. set(2,4) lub podobne, zobacz dokumentację!) i zdobycie flagi.
Na samym początku uzyj narzędzia i zrób hardReset a potem spróbuj zniszczyć cel bezpośrednio, tak jak wymaga tego instrukcja. Prawdopodobnie zgłosi błąd z brakami.
TWOIM ZADANIEM JEST WYKORZYSTANIE NARZĘDZIA DO DOSTARCZENIA POPRAWNEJ SEKWENCJI INSTRUKCJI. Każdą pomyłkę (błąd z API) analizuj i dodawaj brakujące instrukcje. Próbuj do skutku.

OTO POBRANA STRONA Z DOKUMENTACJĄ API DRONA:
{drone_docs}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Rozpocznij misję zniszczenia pola sektor_x=2, sektor_y=4 używając odpowiednich metod z dokumentacji. Najpierw zrób hardReset a potem podejmij pierwszą, bezpośrednią próbę zniszczenia celu. ID lokalizacji naszego celu to PWR6132PL."}
    ]

    for step in range(15):
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
            print("Odpowiedź asystenta:", msg.content)
            if msg.content and "FLG:" in msg.content:
                print("\nAGENT ZDOBYŁ FLAGĘ (z tekstu) - KOŃCZENIE PRACY.")
                return
            
        else:
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                print(f"\n> Agent wywołuje narzędzie: {name} z parametrami: {args}")
                
                if name == "send_drone_instructions":
                    res = send_drone_instructions(**args)
                    tool_result = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
                else:
                    tool_result = "Unknown tool"

                print(f"< Wynik narzędzia z serwera: {tool_result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(tool_result)
                })

                if "flg" in str(tool_result).lower() or "{{flg" in str(tool_result).lower():
                    print("\nAGENT ZDOBYŁ FLAGĘ - KOŃCZENIE PRACY.")
                    return

if __name__ == "__main__":
    run_agent()
