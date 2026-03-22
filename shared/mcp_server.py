import os
import httpx
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp.server.fastmcp import FastMCP
import csv
import json
# Setup basic logging to stderr so it doesn't pollute stdout (which MCP uses)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
HUB_API_KEY = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

if not HUB_API_KEY:
    logger.error("Missing HUB_API_KEY")
    exit(1)

# HUB_API_URL = f"{HUB_URL}/api/packages"
HUB_API_URL = f"{HUB_URL}/verify"

# Initialize FastMCP server
mcp = FastMCP("Packages Provider")

async def call_external_api(payload: dict) -> dict:
    async with httpx.AsyncClient() as http_client:
        try:
            logger.info(f"Calling external API with payload: {payload}")
            response = await http_client.post(HUB_API_URL, json=payload, timeout=10.0)
            res_json = response.json()
            return res_json
        except Exception as e:
            logger.error(f"Error calling external API: {e}")
            return {"error": str(e)}

@mcp.tool()
async def check_package(packageid: str) -> str:
    """Checks the status and location of a package."""
    payload = {
        "apikey": HUB_API_KEY,
        "action": "check",
        "packageid": packageid
    }
    res = await call_external_api(payload)
    import json
    return json.dumps(res)

@mcp.tool()
async def redirect_package(packageid: str, destination: str, code: str) -> str:
    """Redirects a package to a new destination."""
    payload = {
        "apikey": HUB_API_KEY,
        "action": "redirect",
        "packageid": packageid,
        "destination": destination,
        "code": code
    }
    res = await call_external_api(payload)
    import json
    return json.dumps(res)

@mcp.tool()
async def read_image(url: str) -> str:
    """Reads an image from the given URL and returns its textual content / description using vision AI."""
    try:
        logger.info(f"Reading image from URL: {url}")
        response = await openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe the content of this image in detail. If there is any text in the image, extract it exactly as written. Return all text and visual content you can identify."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": url}
                        }
                    ]
                }
            ]
        )
        result = response.choices[0].message.content
        logger.info(f"Image read successfully, response length: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Error reading image: {e}")
        return f"Error reading image: {str(e)}"


@mcp.tool()
async def read_file(url: str) -> str:
    """Reads a text file from the given URL and returns its content."""
    async with httpx.AsyncClient() as http_client:
        try:
            logger.info(f"Reading file from URL: {url}")
            response = await http_client.get(url, timeout=15.0)
            response.raise_for_status()
            logger.info(f"File read successfully, length: {len(response.text)}")
            return response.text
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return f"Error reading file: {str(e)}"

@mcp.tool()
async def send_logs_to_api(logs_content: str) -> str:
    """Sends the processed logs to the verification API for task S02E03."""
    logger.info(f"Sending {len(logs_content)} chars to API mock...")
    payload = {
        "apikey": HUB_API_KEY,
        "task": "failure",
        "answer": {
            "logs": logs_content
        }
    }
    res = await call_external_api(payload)
    import json
    return json.dumps(res)

@mcp.tool()
async def read_local_file(file_path: str) -> str:
    """Reads a text file from the local file system and returns its content."""
    try:
        logger.info(f"Reading local file: {file_path}")
        if not os.path.exists(file_path):
            return f"Error: File {file_path} does not exist."
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        logger.info(f"Local file {file_path} read successfully, length: {len(content)}")
        return content
    except Exception as e:
        logger.error(f"Error reading local file: {e}")
        return f"Error reading local file: {str(e)}"

@mcp.tool()
async def evaluate_classifier_prompt(prompt_template: str) -> str:
    """Evaluates the given classifier prompt_template against the central hub using 10 CSV items.
    Replaces {description} in the template with actual item descriptions from the CSV."""
    
    async with httpx.AsyncClient() as http_client:
        try:
            # 1. Wysyłanie POST na /verify celem wbudowanego resetowania
            reset_payload = {"apikey": HUB_API_KEY, "task": "categorize", "answer": {"prompt": "reset"}}
            logger.info("Resetting categorization task in hub...")
            reset_res = await http_client.post(f"{HUB_URL}/verify", json=reset_payload, timeout=10.0)
            logger.info(f"Reset returned: {reset_res.text[:200]}")
            
            # Pobranie aktualnego CSV
            csv_url = f"{HUB_URL}/data/{HUB_API_KEY}/categorize.csv"
            logger.info(f"Downloading CSV from: {csv_url}")
            csv_res = await http_client.get(csv_url, timeout=15.0)
            csv_res.raise_for_status()
            
            # Parsowanie CSV
            decoded_content = csv_res.text.splitlines()
            reader = csv.reader(decoded_content)
            
            items = []
            for row in reader:
                if len(row) >= 2 and row[0].lower() != 'code':
                    items.append({"code": row[0], "description": row[1]})
            
            logger.info(f"Got {len(items)} items from CSV. Going to evaluate the first 10...")
            
            items_to_eval = items[:10]
            
            # W pętli dla maks 10 towarów
            for i, item in enumerate(items_to_eval):
                final_prompt = prompt_template.replace("{description}", item['description']).replace("{id}", item['code'])
                
                payload = {
                    "apikey": HUB_API_KEY,
                    "task": "categorize",
                    "answer": {
                        "prompt": final_prompt
                    }
                }
                
                logger.info(f"Item #{i+1} [{item['code']}] - payload: {payload}")
                
                try:
                    verify_res = await http_client.post(f"{HUB_URL}/verify", json=payload, timeout=20.0)
                    verify_res.raise_for_status()
                    res_json = verify_res.json()
                except httpx.HTTPStatusError as e:
                    try:
                        err_json = e.response.json()
                        return f"Błąd API na przedmiocie {item['code']} ({item['description']}): {json.dumps(err_json)}"
                    except Exception:
                        return f"Błąd HTTP na przedmiocie {item['code']}: {e}"
                except Exception as e:
                    return f"Błąd na przedmiocie {item['code']}: {e}"
                
                logger.info(f"Response for {item['code']}: {res_json}")
                
                if res_json.get("code") != 0 and res_json.get("code") != 1:
                    return f"Błędna walidacja na przedmiocie {item['code']} ({item['description']}). Kod: {res_json.get('code')}, Wiadomość: {res_json.get('message')}"
                
                # Jeśli w odpowiedzi dostaniemy flagę
                if "FLG:" in str(res_json.get("message", "")) or "FLG:" in str(res_json):
                    return f"WYGRANA! Zdobyliśmy flagę: {res_json}"
                    
            return f"Pętla zakończona sukcesem (10/10) dla promptu: {prompt_template}. Sprawdź logi (być może flaga jest w res_json ostatniego elementu)."
            
        except Exception as e:
            logger.error(f"Error evaluating prompt: {e}")
            return json.dumps({"error": str(e)})


@mcp.tool()
async def rotate(row: int, column: int) -> str:
    """Rotates a tile on the electricity grid by 90 degrees clockwise.
    The parameters are row and column (1-indexed based on the visual layout)."""
    async with httpx.AsyncClient() as http_client:
        position = f"{row}x{column}"
        payload = {
            "apikey": HUB_API_KEY,
            "task": "electricity",
            "answer": {
                "rotate": position
            }
        }
        try:
            logger.info(f"Sending rotate command for tile {position} (task: electricity)")
            response = await http_client.post(f"{HUB_URL}/verify", json=payload, timeout=10.0)
            response.raise_for_status()
            res_json = response.json()
            return json.dumps(res_json)
        except httpx.HTTPStatusError as e:
            try:
                err_json = e.response.json()
                return f"API Error on rotation of {position}: {json.dumps(err_json)}"
            except Exception:
                return f"HTTP Error on rotation of {position}: {e}"
        except Exception as e:
            logger.error(f"Error executing rotation: {e}")
            return json.dumps({"error": str(e)})

if __name__ == "__main__":
    # Start the server using stdio
    mcp.run(transport='stdio')
