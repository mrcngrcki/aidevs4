import os
import requests
import csv
import io
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from typing import List

# Wczytanie zmiennych środowiskowych z pliku .env
load_dotenv()

# Pobranie klucza API
api_key = os.getenv("HUB_API_KEY")

if not api_key:
    # Spróbujmy wymusić ścieżkę, jeśli domyślne load_dotenv() nie zadziałało
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)
    api_key = os.getenv("HUB_API_KEY")

if not api_key:
    print("Błąd: Nie znaleziono klucza 'HUB_API_KEY' w pliku .env")
    exit(1)

# Budowanie URL
HUB_URL = os.getenv("HUB_URL")
url = f"{HUB_URL}/data/{api_key}/people.csv"

# Wysłanie requestu GET
try:
    response = requests.get(url)
    response.raise_for_status() # Sprawdzenie czy request się powiódł
    
    csv_data = response.text
    reader = csv.DictReader(io.StringIO(csv_data))
    
    filtered_people = []
    
    
    for row in reader:
        # Płeć: Mężczyzna
        if row['gender'] not in ['M', 'Mężczyzna']:
            continue
            
        # Wiek w 2026: 20 do 40 lat (czyli rok urodzenia 1986 - 2006)
        try:
            birth_year = int(row['birthDate'].split('-')[0])
            if not (1986 <= birth_year <= 2006):
                continue
        except (ValueError, KeyError):
            continue
            
        # Miejsce urodzenia: Grudziądz
        if row['birthPlace'] != 'Grudziądz':
            continue
            
        filtered_people.append(row)
        
    # Inicjalizacja klienta OpenAI
    # Wymaga zmiennej OPENAI_API_KEY w podłączonym środowisku lub .env
    openai_client = OpenAI()

    class JobTags(BaseModel):
        person_id: int
        tags: List[str]

    class BatchJobTagsResponse(BaseModel):
        results: List[JobTags]

    print(f"Znaleziono {len(filtered_people)} kandydatów. Rozpoczynam kategoryzację (Batch Tagging) przez OpenAI...")
    
    # Przygotowanie danych do batcha
    jobs_text = "\n".join([f"ID: {i} | Opis: {p['job']}" for i, p in enumerate(filtered_people)])
    
    prompt = f"""Przeanalizuj poniższe opisy stanowisk (oznaczone ID) i przypisz każdy do jednej lub wielu z podanych kategorii:
- IT (szeroko pojęta informatyka)
- transport
- edukacja
- medycyna
- praca z ludźmi
- praca z pojazdami
- praca fizyczna

Zwróć wynik jako ustrukturyzowany JSON. Każdemu 'person_id' przypisz listę 'tags' zawierającą poprawne kategorie z powyższej listy.

Lista stanowisk:
{jobs_text}"""

    response = openai_client.beta.chat.completions.parse(
        model="gpt-5-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        response_format=BatchJobTagsResponse
    )
    
    batch_results = response.choices[0].message.parsed
    tags_map = {res.person_id: res.tags for res in batch_results.results}

    answer_list = []
    
    for i, person in enumerate(filtered_people):
        try:
            born_year = int(person['birthDate'].split('-')[0])
        except (ValueError, KeyError):
            born_year = None
            
        tags = tags_map.get(i, [])
        
        if "transport" not in tags:
            continue
            
        answer_list.append({
            "name": person['name'],
            "surname": person['surname'],
            "gender": person['gender'],
            "born": born_year,
            "city": person['birthPlace'],
            "tags": tags
        })
        
    output_data = {
        "apikey": api_key,
        "task": "people",
        "answer": answer_list
    }
    
    print(f"Wysyłanie danych do {HUB_URL}/verify...")
    verify_response = requests.post(
        f"{HUB_URL}/verify",
        json=output_data
    )
    
    print(f"Status: {verify_response.status_code}")
    print("Odpowiedź API:")
    print(verify_response.text)
except requests.exceptions.RequestException as e:
    print(f"Wystąpił błąd podczas pobierania danych: {e}")
except Exception as e:
    print(f"Błąd przetwarzania: {e}")

