import os
import requests
import time
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
api_key = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv(f"{HUB_URL}/verify")

if not api_key:
    print("Brak klucza HUB_API_KEY w zmiennych środowiskowych.")
    exit(1)

openai_client = OpenAI()

def send_api_request(action_data: dict):
    payload = {
        "apikey": api_key,
        "task": "railway",
        "answer": action_data
    }
    
    while True:
        try:
            resp = requests.post(HUB_URL, json=payload)
            print(f"[{resp.status_code}] Action sent: {action_data}")
            
            if resp.status_code == 200:
                print("Response:", resp.text)
                return resp.json()
            elif resp.status_code == 429:
                retry = int(resp.headers.get('Retry-After', 5))
                print(f"Błąd 429 (Rate limited). Czekam {retry} sekund przed ponowieniem...")
                time.sleep(retry + 1)
            elif resp.status_code == 503:
                print("Błąd 503 (Temporary outage). Czekam 2 sekundy przed ponowieniem...")
                time.sleep(2)
            else:
                print(f"Nieoczekiwany błąd {resp.status_code}: {resp.text}")
                try:
                    return resp.json()
                except:
                    return {"error": resp.text}
        except Exception as e:
            print(f"Błąd zapytania: {e}. Ponawiam za 2 sekundy...")
            time.sleep(2)

def main():
    print("--- Pobieranie dokumentacji API (action: help) ---")
    help_action = {"action": "help"}
    help_resp = send_api_request(help_action)
    if not help_resp:
        print("Nie udało się pobrać dokumentacji help.")
        return
        
    messages = [
        {
            "role": "system", 
            "content": (
                "Jesteś agentem, który ma za zadanie aktywować trasę kolejową 'X-01'. "
                "Otrzymasz dokumentację API dostarczoną z akcji 'help', oraz odpowiedzi z poprzednich akcji. "
                "Twoim celem jest wygenerowanie kolejnego obiektu JSON, który zostanie wstawiony w pole 'answer' żądania HTTP. "
                "Output MUSI być tylko SUROWYM obiektem JSON, be znaczników markdown. "
                "Pamiętaj, aby respektować kolejność akcji wskazaną w dokumentacji lub na podstawie logiki. "
                "Zazwyczaj trzeba 'reconfigure', potem 'setstatus', a na koniec 'save', ale w razie błędu API dostosuj swoje działanie. "
                "Dokumentacja API poniżej:\n\n" + json.dumps(help_resp, indent=2)
            )
        }
    ]
    
    max_steps = 15
    for i in range(max_steps):
        print(f"\n--- Krok {i+1} ---")
        
        # Pytamy LLM o kolejną akcję
        completion = openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        next_action_str = completion.choices[0].message.content
        print(f"LLM wygenerował akcję: {next_action_str}")
        
        try:
            next_action = json.loads(next_action_str)
        except json.JSONDecodeError:
            print("LLM nie zwrócił poprawnego JSON. Przerywam.")
            break
            
        messages.append({"role": "assistant", "content": next_action_str})
        
        # Wykonujemy wymyśloną akcję
        api_resp = send_api_request(next_action)
        
        if not api_resp:
            print("Pusta odpowiedź z API. Agent spróbuje ponownie.")
            messages.append({"role": "user", "content": "Błąd sieci lub pusta odpowiedź API. Spróbuj ponownie lub dostosuj akcję."})
            continue
            
        # Przekazujemy odpowiedź z powrotem do LLM
        resp_str = json.dumps(api_resp, indent=2)
        messages.append({"role": "user", "content": resp_str})
        
        # Szukamy flagi w dowolnym polu odpowiedzi API
        if "FLG:" in resp_str or "{{FLG:" in resp_str:
            print("\n!!! ZADANIE ZAKOŃCZONE SUKCESEM. ZNALEZIONO FLAGĘ !!!")
            print(resp_str)
            break

if __name__ == "__main__":
    main()
