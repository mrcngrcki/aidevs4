import json
import logging
import os
import csv
from typing import List, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from openai import AsyncOpenAI
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    logger.error("Missing required API keys in .env")
    exit(1)

# Initialize OpenAI Client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
MODEL = "gpt-4o-mini"

app = FastAPI()

# Data storage
cities: Dict[str, str] = {}  # code -> name
items: List[Dict[str, str]] = []  # list of {name, code}
connections: Dict[str, List[str]] = {}  # itemCode -> list of cityCodes

def load_data():
    base_path = os.path.dirname(__file__)
    
    # Load cities
    with open(os.path.join(base_path, "cities.csv"), mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cities[row['code']] = row['name']
            
    # Load items
    with open(os.path.join(base_path, "items.csv"), mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append({"name": row['name'], "code": row['code']})
            
    # Load connections
    with open(os.path.join(base_path, "connections.csv"), mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_code = row['itemCode']
            city_code = row['cityCode']
            if item_code not in connections:
                connections[item_code] = []
            connections[item_code].append(city_code)
    
    logger.info(f"Loaded {len(cities)} cities, {len(items)} items, and {len(connections)} connections.")

load_data()

class ToolRequest(BaseModel):
    params: str

class ToolResponse(BaseModel):
    output: str

async def find_best_item_code(description: str) -> str:
    # 1. Simple keyword filtering to reduce candidates for LLM
    query_words = description.lower().split()
    # Filter out common Polish words
    stop_words = {"potrzebuję", "potrzebuje", "chcę", "chce", "szukam", "mi", "dla", "do", "z", "w", "na"}
    keywords = [w for w in query_words if w not in stop_words and len(w) > 2]
    
    if not keywords:
        keywords = query_words

    candidates = []
    for item in items:
        match_count = sum(1 for kw in keywords if kw in item['name'].lower())
        if match_count > 0:
            candidates.append((match_count, item))
    
    # Sort by match count and take top 50
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_candidates = [c[1] for c in candidates[:50]]
    
    if not top_candidates:
        # If no keywords match, try a broader search or just send a subset to LLM
        top_candidates = items[:50] # Fail-safe

    # 2. Use LLM to pick the best match from top candidates
    candidate_str = "\n".join([f"{c['code']}: {c['name']}" for c in top_candidates])
    
    system_prompt = """You are a helpful assistant that matches a user's natural language request for an item to the most relevant item from a list.
Return ONLY the item code of the best match. If no match is even remotely relevant, return 'NONE'."""
    
    user_prompt = f"User request: '{description}'\n\nCandidates:\n{candidate_str}\n\nBest item code:"
    
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=10,
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return "NONE"

@app.post("/api/get_cities_by_item", response_model=ToolResponse)
async def get_cities_endpoint(request: ToolRequest):
    logger.info(f"Received request: {request.params}")
    
    # Check if it's already a code
    item_code = request.params.strip().upper()
    found_item = any(item['code'] == item_code for item in items)
    
    if not found_item:
        # Search using LLM
        item_code = await find_best_item_code(request.params)
        logger.info(f"LLM found item code: {item_code}")

    if item_code == "NONE" or item_code not in connections:
        return ToolResponse(output="Nie znaleziono miast oferujacych ten przedmiot.")
    
    city_codes = connections[item_code]
    city_names = [cities[code] for code in city_codes if code in cities]
    
    # Return comma-separated list
    output = ", ".join(sorted(city_names))
    
    # Ensure output is within limits (4-500 bytes)
    if len(output) > 500:
        output = output[:497] + "..."
    if len(output) < 4:
        output = "BRAK"
        
    logger.info(f"Returning output: {output}")
    return ToolResponse(output=output)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)

