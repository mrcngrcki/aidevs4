import os
import requests
import json
from dotenv import load_dotenv
from openai import OpenAI
import time

# Wczytanie zmiennych środowiskowych
load_dotenv()
api_key = os.getenv("HUB_API_KEY")

if not api_key:
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)
    api_key = os.getenv("HUB_API_KEY")

if not api_key:
    print("Błąd: Nie znaleziono klucza 'HUB_API_KEY' w pliku .env")
    exit(1)

HUB_URL = os.getenv("HUB_URL")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Wczytanie podejrzanych
suspects_path = os.path.join(os.path.dirname(__file__), '..', 'suspects.json')
with open(suspects_path, 'r', encoding='utf-8') as file:
    suspects = json.load(file)

# Narzędzia / Tools
def get_suspect_locations(name: str, surname: str) -> str:
    print(f"[TOOL] get_suspect_locations(name='{name}', surname='{surname}')")
    response = requests.post(f"{HUB_URL}/api/location", json={
        "apikey": api_key,
        "name": name,
        "surname": surname
    })
    return response.text

def get_person_access_level(name: str, surname: str, birthYear: int) -> str:
    print(f"[TOOL] get_person_access_level(name='{name}', surname='{surname}', birthYear={birthYear})")
    response = requests.post(f"{HUB_URL}/api/accesslevel", json={
        "apikey": api_key,
        "name": name,
        "surname": surname,
        "birthYear": birthYear
    })
    return response.text

def submit_verification(name: str, surname: str, accessLevel: int, powerPlant: str) -> str:
    print(f"[TOOL] submit_verification(name='{name}', surname='{surname}', accessLevel={accessLevel}, powerPlant='{powerPlant}')")
    payload = {
        "apikey": api_key,
        "task": "findhim",
        "answer": {
            "name": name,
            "surname": surname,
            "accessLevel": accessLevel,
            "powerPlant": powerPlant
        }
    }
    response = requests.post(f"{HUB_URL}/verify", json=payload)
    return response.text

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_suspect_locations",
            "description": "Fetch a list of GPS coordinates where the suspect was seen. Call this to check if a suspect was visiting areas near power plants.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                },
                "required": ["name", "surname"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_person_access_level",
            "description": "Fetch the security clearance (access level) for a specific person. Make sure to retrieve this before submitting verification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "birthYear": {
                        "type": "integer",
                        "description": "The person's birth year, e.g. 1987 as an integer."
                    }
                },
                "required": ["name", "surname", "birthYear"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verification",
            "description": "Submit the final answer after successfully identifying the suspect who was near a power plant and fetching their access level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "accessLevel": {"type": "integer"},
                    "powerPlant": {"type": "string", "description": "The code of the power plant, e.g., PWR0000PL"},
                },
                "required": ["name", "surname", "accessLevel", "powerPlant"]
            }
        }
    }
]

# Pobranie lokalizacji elektrowni
resp = requests.get(f"{HUB_URL}/data/{api_key}/findhim_locations.json")
power_plants_data = resp.text

system_prompt = f"""
Twoim celem jest wskazanie, która z podejrzanych osób przebywała blisko jednej z polskich elektrowni na podstawie zebranych koordynatów GPS.

Masz do dyspozycji:
1. Listę podejrzanych (osoba to imię, nazwisko, i 'born' - rok urodzenia, tu nazywany birthYear):
{json.dumps(suspects, ensure_ascii=False, indent=2)}

2. Listę miast z elektrowniami (wraz z ich kodem - code):
{power_plants_data}

Twój algorytm postępowania krok po kroku:
1. Pobieraj listę koordynatów za pomocą 'get_suspect_locations' dla kolejnych podejrzanych.
2. Spróbuj powiązać otrzymane współrzędne z którymś z miast w których są elektrownie (masz ogólną wiedzę o geografii Polski, więc poradzisz sobie ze zrównaniem koordynatów GPS m.in w okolicach Zabrza, Piotrkowa Trybunalskiego, Grudziądza, Tczewa, Radomia, Chełmna, Żarnowca). Uwaga: koordynaty z API location to miasto elektrowni.
3. Gdy zlokalizujesz osobę, która przebywała bardzo blisko elektrowni, to jest Twój podejrzany!
4. Dla tego podejrzanego musisz zawołać 'get_person_access_level' (pamiętaj, aby podać 'birthYear' pobrany ze zmiennej 'born' z jsona dostarczonego w prompcie systemowym - musi być to liczba całkowita!).
5. Następnie zakończ zadanie wywołując 'submit_verification' z pełnymi danymi (imię, nazwisko, accessLevel, oraz wyciągnięty z powyższych danych 'code' power_plantu niedaleko którego przebywała osoba).
6. Jeśli odpowiedź z /verify jest popuprawna (dostaniesz flagę), możesz zakończyć.
"""

messages = [{"role": "system", "content": system_prompt}]

print("Agent uruchamia proces poszukiwań...")
max_iterations = 15
for iteration in range(max_iterations):
    print(f"\n--- Iteracja {iteration + 1} ---")
    response = openai_client.chat.completions.create(
        model="gpt-5-mini",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    response_message = response.choices[0].message
    
    # Dołączamy odpowiedź asystenta do historii z narzędziami, które wywołał:
    # uwaga: `response_message` zawiera pole `tool_calls`
    msg_dict = response_message.model_dump(exclude_unset=True)
    messages.append(msg_dict)
    
    if not response_message.tool_calls:
        print("Model odpowiedział bezpośrednio (bez wywołania funkcji):")
        print(response_message.content)
        break

    for tool_call in response_message.tool_calls:
        func_name = tool_call.function.name
        func_args = json.loads(tool_call.function.arguments)
        
        result_text = ""
        if func_name == "get_suspect_locations":
            result_text = get_suspect_locations(func_args["name"], func_args["surname"])
        elif func_name == "get_person_access_level":
            result_text = get_person_access_level(func_args["name"], func_args["surname"], func_args["birthYear"])
        elif func_name == "submit_verification":
            result_text = submit_verification(func_args["name"], func_args["surname"], func_args["accessLevel"], func_args["powerPlant"])
            
        print(f"Wynik z funkcji {func_name}: {result_text}")
        
        messages.append({
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": func_name,
            "content": result_text,
        })
        
        if func_name == "submit_verification" and "FLG" in result_text:
            print("ZADANIE ZAKOŃCZONE SUKCESEM!")
            exit(0)

print("\nOsiągnięto limit iteracji lub zadanie nie zostało powiedzmy 'submit_verification' z powodem sukcesu.")