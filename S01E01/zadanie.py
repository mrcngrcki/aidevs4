import os
import requests
import csv
import io
import json
from dotenv import load_dotenv
from openai import OpenAI

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
url = f"https://hub.ag3nts.org/data/{api_key}/people.csv"

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

    def get_job_tags(job_description):
        prompt = f"""Przeanalizuj poniższy opis stanowiska i przypisz go do jednej lub wielu z podanych kategorii:
- IT (szeroko pojęta informatyka)
- transport
- edukacja
- medycyna
- praca z ludźmi
- praca z pojazdami
- praca fizyczna

Zwróć wynik JAKO LISTĘ W FORMACIE JSON (tylko poprawne ciągi znaków z nazwami kategorii). Zwróć same kategorie z podanej listy (dokładnie z taką składnią, jaka jest zdefiniowana w punktach). Nie dodawaj żadnego dodatkowego tekstu ani formatowania Markdown.

Opis: {job_description}"""
        
        response = openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "user", "content": prompt}
            ]
            #temperature=0.1
        )
        content = response.choices[0].message.content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # W przypadku błędu formatowania, próbuj jakoś odzyskać listę
            return [cat for cat in [
                "IT (szeroko pojęta informatyka)", "transport", "edukacja", 
                "medycyna", "praca z ludźmi", "praca z pojazdami", "praca fizyczna"
            ] if cat.lower() in content.lower()]

    answer_list = []
    print(f"Znaleziono {len(filtered_people)} kandydatów. Rozpoczynam kategoryzację przez OpenAI...")
    
    for i, person in enumerate(filtered_people):
        print(f"[{i+1}/{len(filtered_people)}] Kategoryzacja dla: {person['name']} {person['surname']} (zawód: {person['job'][:30]}...)")
        try:
            born_year = int(person['birthDate'].split('-')[0])
        except (ValueError, KeyError):
            born_year = None
            
        tags = get_job_tags(person['job'])
        
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
    
    print("Wysyłanie danych do https://hub.ag3nts.org/verify...")
    verify_response = requests.post(
        "https://hub.ag3nts.org/verify",
        json=output_data
    )
    
    print(f"Status: {verify_response.status_code}")
    print("Odpowiedź API:")
    print(verify_response.text)
except requests.exceptions.RequestException as e:
    print(f"Wystąpił błąd podczas pobierania danych: {e}")
except Exception as e:
    print(f"Błąd przetwarzania: {e}")
    
