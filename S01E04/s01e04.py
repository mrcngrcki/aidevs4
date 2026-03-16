import asyncio
import logging
import os
import re
import sys
from contextlib import AsyncExitStack
import requests

from dotenv import load_dotenv
from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HUB_URL = os.getenv("HUB_URL")
BASE_URL = f"{HUB_URL}/dane/doc/"
INDEX_URL = f"{BASE_URL}index.md"
API_KEY = os.getenv("HUB_API_KEY")

# Regex to match [include file="filename.ext"]
INCLUDE_PATTERN = re.compile(r'\[include file="([^"]+)"\]')


async def call_mcp_tool(mcp_session, tool_name: str, args: dict) -> str:
    """Call an MCP tool and return the text result."""
    try:
        mcp_res = await mcp_session.call_tool(tool_name, arguments=args)
        content_parts = [c.text for c in mcp_res.content if hasattr(c, 'text')]
        return "\n".join(content_parts)
    except Exception as e:
        logger.error(f"MCP tool {tool_name} error: {e}")
        return f"[ERROR: {e}]"


async def main():
    output_path = os.path.join(os.path.dirname(__file__), "instrukcje.md")

    if os.path.exists(output_path):
        logger.info(f"File {output_path} already exists, loading from file.")
        with open(output_path, "r", encoding="utf-8") as f:
            final_document = f.read()
    else:
        # Connect to MCP server
        server_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared", "mcp_server.py")
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
            env=os.environ.copy()
        )

        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(stdio_client(server_params))
            mcp_session = await stack.enter_async_context(ClientSession(read, write))
            await mcp_session.initialize()

            # Load tools
            response = await mcp_session.list_tools()
            tool_names = [t.name for t in response.tools]
            logger.info(f"Loaded MCP tools: {tool_names}")

            # Step 1: Fetch index.md
            logger.info(f"Fetching index.md from {INDEX_URL}")
            document = await call_mcp_tool(mcp_session, "read_file", {"url": INDEX_URL})
            logger.info(f"index.md fetched, length: {len(document)} chars")

            # Step 2: Find all [include file="..."] directives
            includes = INCLUDE_PATTERN.findall(document)
            logger.info(f"Found {len(includes)} include directives: {includes}")

            # Step 3: Fetch all included files in parallel
            async def fetch_include(filename: str) -> tuple[str, str]:
                url = f"{BASE_URL}{filename}"
                if filename.endswith(".png"):
                    logger.info(f"Reading image: {url}")
                    content = await call_mcp_tool(mcp_session, "read_image", {"url": url})
                else:
                    logger.info(f"Reading file: {url}")
                    content = await call_mcp_tool(mcp_session, "read_file", {"url": url})
                logger.info(f"Fetched {filename}: {len(content)} chars")
                return filename, content

            # Fetch all includes (MCP calls are sequential per session, but we queue them all)
            results = {}
            for filename in includes:
                fname, content = await fetch_include(filename)
                results[fname] = content

            # Step 4: Replace all [include file="..."] with fetched content
            def replace_include(match):
                filename = match.group(1)
                if filename in results:
                    return results[filename]
                return match.group(0)  # leave as-is if not found

            final_document = INCLUDE_PATTERN.sub(replace_include, document)
            logger.info(f"Final document length: {len(final_document)} chars")

            # Step 5: Save output
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(final_document)
            logger.info(f"Output saved to {output_path}")

    template = """SYSTEM PRZESYŁEK KONDUKTORSKICH - DEKLARACJA ZAWARTOŚCI
======================================================
DATA: 2026-03-17
PUNKT NADAWCZY: Gdańsk
------------------------------------------------------
NADAWCA: 450202122
PUNKT DOCELOWY: Żarnowiec
TRASA: [kod trasy]
------------------------------------------------------
KATEGORIA PRZESYŁKI: A/B/C/D/E
------------------------------------------------------
OPIS ZAWARTOŚCI (max 200 znaków): kasety z paliwem do reaktora
------------------------------------------------------
DEKLAROWANA MASA (kg): 2800
------------------------------------------------------
WDP: [liczba]
------------------------------------------------------
UWAGI SPECJALNE: 
------------------------------------------------------
KWOTA DO ZAPŁATY: 0
------------------------------------------------------
OŚWIADCZAM, ŻE PODANE INFORMACJE SĄ PRAWDZIWE.
BIORĘ NA SIEBIE KONSEKWENCJĘ ZA FAŁSZYWE OŚWIADCZENIE.
======================================================"""

    logger.info("Przygotowanie zapytania do OpenAI...")
    openai_client = AsyncOpenAI()

    prompt = f"""Na podstawie poniższej dokumentacji uzupełnij brakujące pola w zmiennej template. 
Zadanie: Przesyłka ma zostać wysłana na trasie Gdańsk-Żarnowiec (strefa wyłączona), a jej całkowity koszt ma wynosić dokładnie 0 PP (Punktów Pracy). 
Masa przesyłki: 2800 kg. Oznacza to, że potrzebne są dodatkowe wagony (WDP). WDP to liczba wagonów (każdy o pojemności 500kg). Ponieważ udźwig składu bazowego to 1000kg to konieczne jest opłacone wagony za pozostałe 1800kg czyli co najmniej 4 wagony. Sprawdź, jak WDP i opłaty za masę i dodatkowe wagony wpływają na koszt przesyłki zależnie od kategorii! Czasami te opłaty pokrywa system. Musisz wybrać kategorię dla której końcowy koszt to 0 PP.
Wymagane pola do uzupełnienia to: [kod trasy], kategoria przesyłki na miejscu A/B/C/D/E, i [liczba] przy WDP w poniższym szablonie.

Oto dokumentacja:
{final_document}

Zwróć TYLKO uzupełniony tekst szablonu. Nie dodawaj znaczników markdown ani niczego innego, sam uzupełniony tekst.

Szablon:
{template}
"""
    
    response = await openai_client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": "Jesteś asystentem uzupełniającym szablon i zwracającym wyłącznie uzupełniony tekst (bez żadnego formatowania, bez znaczników markdown)."},
            {"role": "user", "content": prompt}
        ]
    )

    filled_template = response.choices[0].message.content.strip()
    logger.info(f"Uzupełniony template z OpenAI:\\n{filled_template}")
    
    # Można tutaj zapisać filled_template do pliku jeśli takie jest zadanie
    with open("template_filled.txt", "w", encoding="utf-8") as f:
        f.write(filled_template)

    output_data = {
        "apikey": API_KEY,
        "task": "sendit",
        "answer": {
            "declaration": filled_template
        }
    }

    print(f"Wysyłanie danych do {HUB_URL}/verify...")
    verify_response = requests.post(
        f"{HUB_URL}/verify",
        json=output_data
    )
    
    print(f"Status: {verify_response.status_code}")
    print("Odpowiedź API:")
    print(verify_response.text)

if __name__ == "__main__":
    asyncio.run(main())
