import requests, os
from dotenv import load_dotenv

load_dotenv("../.env")
import csv
import io

load_dotenv("../.env")
url = f"https://hub.ag3nts.org/data/{os.getenv('HUB_API_KEY')}/people.csv"
response = requests.get(url)
response.raise_for_status()

csv_data = response.text
reader = csv.DictReader(io.StringIO(csv_data))

candidates = []
for row in reader:
    # men: gender == 'M'
    if row['gender'] != 'M':
        continue
    # age 20-40 in 2026 => born 1986 - 2006
    birth_year = int(row['birthDate'].split('-')[0])
    if not (1986 <= birth_year <= 2006):
        continue
    # born in Grudziądz
    if row['birthPlace'] != 'Grudziądz':
        continue
    candidates.append(row)

for c in candidates:
    print(c['name'], c['surname'], c['job'])

