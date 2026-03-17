import os
from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Literal

# Typ wyliczeniowy dla kierunków, żeby model nie mógł wymyślić innych liter
Direction = Literal["N", "E", "S", "W"]

class GridSize(BaseModel):
    rows: int = Field(
        description="Całkowita liczba wierszy planszy (zawsze 3)"
    )
    cols: int = Field(
        description="Całkowita liczba kolumn planszy (zawsze 3)"
    )

class InputPoint(BaseModel):
    id: str = Field(
        description="Nazwa, symbol lub opis obrazka znajdującego się po PRAWEJ stronie planszy (np. napis z nazwą lub kodem)."
    )
    row: int = Field(
        description="Numer wiersza (indeksowany od 1), w którym znajduje się to wejście."
    )
    entry_port: Direction = Field(
        default="E",
        description="Kierunek, z którego przewód wchodzi na planszę. Zazwyczaj 'E' (Wschód/Prawo)."
    )

class OutputPoint(BaseModel):
    id: str = Field(
        description="Nazwa, symbol lub opis obrazka znajdującego się po LEWEJ stronie planszy (np. ikona fabryki lub elektrowni)."
    )
    row: int = Field(
        description="Numer wiersza (indeksowany od 1), z którym łączy się to wyjście. Zawsze 3."
    )
    exit_port: Direction = Field(
        default="W",
        description="Kierunek, w którym przewód wychodzi z planszy. Zazwyczaj 'W' (Zachód/Lewo)."
    )

class Tile(BaseModel):
    row: int = Field(
        description="Współrzędna wiersza kafelka (od 1)."
    )
    col: int = Field(
        description="Współrzędna kolumny kafelka (od 1)."
    )
    connections: List[Direction] = Field(
        description="Lista kierunków (N, E, S, W), w których końcówki przewodu stykają się z krawędziami tego kafelka."
    )

class BoardState(BaseModel):
    """Główna klasa reprezentująca cały stan planszy łamigłówki."""
    thinking: str = Field(
        description="Twój tok rozumowania. Zwykłym tekstem opisz co widzisz na obrazku, "
                    "jaki to rodzaj łamigłówki, ile widzisz wierszy i kolumn, "
                    "oraz jakie elementy znajdują się po lewej i prawej stronie."
    )
    grid_size: GridSize
    inputs: List[InputPoint]
    output: OutputPoint
    tiles: List[Tile]

# Wczytuje zmienne środowiskowe, m.in. OPENAI_API_KEY
load_dotenv()
HUB_URL = os.getenv("HUB_URL")
HUB_API_KEY = os.getenv("HUB_API_KEY")

client = OpenAI()

SYSTEM_PROMPT = """
# Rola
Jesteś ekspertem ds. analizy obrazu i systemów logicznych. 

# Zadanie
Twoim zadaniem jest przeanalizowanie planszy z łamigłówką typu "połącz rury/przewody" i zapisanie jej stanu początkowego zgodnie z wymaganym schematem JSON (Structured Output).

# Kroki analizy:
1. **Analiza opisowa (pole `thinking`)**: Rozpocznij od opisania własnymi słowami, co widzisz na obrazku. Zwróć szczególną uwagę na to, że **3 punkty wejściowe (inputs) znajdują się po PRAWEJ stronie, a 1 punkt wyjściowy (output) znajduje się po LEWEJ stronie na samym dole**. Policz na głos wiersze i kolumny.
2. **Siatka**: Zidentyfikuj wymiary siatki (liczba wierszy i kolumn, indeksowane od 1).
3. **Połączenia**: Każdy kafelek na planszy zawiera fragment przewodu. Określ, w jakich kierunkach przewód "wychodzi" z kafelka, używając skrótów kierunków świata:
   - **N** (Północ / góra)
   - **E** (Wschód / prawo)
   - **S** (Południe / dół)
   - **W** (Zachód / lewo)
4. **Punkty startowe i końcowe**: Zidentyfikuj pozycje 3 elementów wejściowych po prawej stronie (po prostu zwróć wiersze 1, 2 i 3) i 1 elementu wyjściowego po lewej stronie na dole (po prostu zwróć wiersz 3).

# Instrukcje końcowe
Spójrz na dostarczony obrazek i wygeneruj poprawny obiekt JSON, zaczynając od dokładnego opisu w polu `thinking`, a następnie mapując całą planszę kafel po kafelku zgodnie z dostarczonym schematem.
"""


def analyze_image(image_url: str = None) -> BoardState:
    model = "gpt-5.4"
    if not image_url:
        image_url = f"{HUB_URL}/data/{HUB_API_KEY}/electricity.png"

    print(f"Wysyłam zapytanie do modelu {model}...")
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": "Przeanalizuj ten obrazek i wyciągnij z niego dane w odpowiednim formacie."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url,
                        },
                    },
                ],
            }
        ],
        response_format=BoardState,
    )

    result = response.choices[0].message.parsed
    return result

if __name__ == "__main__":
    board_state = analyze_image()
    print("\nOdczytane dane:")
    print(board_state.model_dump_json(indent=2))
