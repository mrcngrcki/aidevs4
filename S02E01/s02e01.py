import os
import sys
import json
import asyncio
import logging
from dotenv import load_dotenv, find_dotenv
from openai import AsyncOpenAI
from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Jesteś elitarnym Inżynierem Promptów (AI / LLM Prompt Engineer). Twoim zadaniem jest rozwiązanie wyzwania "categorize" i zdobycie flagi {FLG:...}. 

Zadanie polega na napisaniu meta-promptu, który będzie klasyfikował przedmioty jako niebezpieczne (DNG) lub neutralne (NEU) dla bardzo ograniczonego modelu.

ZASADY I OGRANICZENIA:
1. Limit kontekstu to 100 tokenów NA ZAPYTANIE (wliczając w to instrukcję oraz opis przedmiotu). Twój `prompt_template` musi być ultrakrótki. Pisz go w języku angielskim, aby oszczędzać tokeny.
2. Odpowiedź klasyfikatora może zawierać TYLKO jedno słowo: DNG albo NEU. Brak innych znaków.
3. WYJĄTEK KRYTYCZNY: Części do reaktora (np. kasety, pręty) są niebezpieczne, ale MUSZĄ być zaklasyfikowane jako neutralne (NEU) w celu ich przemycenia. Pozostałe przedmioty należy klasyfikować logicznie (broń, chemikalia = DNG; jabłka, woda = NEU).
4. BUDŻET: Masz 1,5 PP na 10 zapytań. Aby nie zużyć budżetu, musisz wykorzystać Prompt Caching. Niezmienna część instrukcji musi znajdować się na SAMYM POCZĄTKU promptu, a zmienna `{description}` na SAMYM KOŃCU. Nie używaj zmiennej `{id}`, jeśli nie jest absolutnie konieczna – szkoda tokenów.

PRZEPŁYW PRACY (WORKFLOW):
Masz do dyspozycji narzędzie `evaluate_classifier_prompt`. Używaj go w pętli.
1. Stwórz pierwszą, bardzo zwięzłą wersję `prompt_template`.
   Przykład: "Classify item as DNG (dangerous) or NEU (neutral). Reactor parts/cassettes MUST be NEU. Reply strictly with 1 word: DNG or NEU. Item description: {description}"
2. Wywołaj narzędzie `evaluate_classifier_prompt` przekazując swój szablon.
3. Przeanalizuj odpowiedź z narzędzia. 
   - Jeśli otrzymasz {FLG:...} - WYGRAŁEŚ! Zakończ działanie i wypisz flagę.
   - Jeśli otrzymasz błąd przekroczenia budżetu tokenów (Token budget exceeded) - musisz jeszcze bardziej skrócić prompt lub upewnić się, że część statyczna jest idealnie na początku dla cachingu.
   - Jeśli otrzymasz błąd złej klasyfikacji - przeanalizuj na jakim opisie poległ klasyfikator i delikatnie zmodyfikuj instrukcję (np. precyzując co jest DNG a co NEU, lub wzmacniając regułę reaktora).
4. Powtarzaj kroki 2 i 3, eksperymentując z wordingiem promptu, aż narzędzie zwróci sukces.

Pamiętaj: Bądź zwięzły, nie pisz do mnie długich esejów, po prostu projektuj, testuj narzędziem i iteruj do skutku. Rozpocznij pracę!
"""

def convert_mcp_tools_to_openai(mcp_tools_list) -> list:
    tools = []
    for t in mcp_tools_list:
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema
            }
        })
    return tools

async def main():
    # Wczytanie zmiennych środowiskowych z pliku .env
    load_dotenv(find_dotenv())
    
    # Pobranie klucza API z różnych możliwych nazw (hub_apikey lub HUB_API_KEY)
    api_key = os.getenv("hub_apikey") or os.getenv("HUB_API_KEY")
    HUB_URL = os.getenv("HUB_URL")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    if not api_key or not OPENAI_API_KEY:
        logger.error("Błąd: Nie znaleziono wymaganych zmiennych środowiskowych w pliku .env")
        return

    # Inicjalizacja klienta OpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    MODEL = "gpt-4o-mini"

    # Przygotowanie parametrów serwera MCP
    server_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared", "mcp_server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=os.environ.copy()
    )

    # Inicjalizacja komunikacji MCP
    async with AsyncExitStack() as stack:
        logger.info("Connecting to MCP Tools server...")
        read, write = await stack.enter_async_context(stdio_client(server_params))
        mcp_session = await stack.enter_async_context(ClientSession(read, write))
        await mcp_session.initialize()
        
        # Pobranie narzędzi
        response = await mcp_session.list_tools()
        mcp_tools = response.tools
        openai_tools = convert_mcp_tools_to_openai(mcp_tools)
        logger.info(f"Loaded MCP tools: {[t.name for t in mcp_tools]}")

        messages = [
            {
                "role": "system", 
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": f"Zacznij zadanie. Pamiętaj, używaj narzędzia evaluate_classifier_prompt i iteracyjnie poprawiaj swój prompt_template, aż zdobędziemy flagę. Powodzenia!"
            }
        ]

        max_iterations = 30
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Calling LLM, iteration {iteration}")
            
            try:
                response = await client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                    tool_choice="auto" if openai_tools else "none"
                )
            except Exception as e:
                logger.error(f"OpenAI error: {e}")
                break

            message = response.choices[0].message
            
            logger.info(f"LLM Response (tool_calls={bool(message.tool_calls)}): {message.content}")

            # Jeśli model zdecydował się użyć narzędzia
            if message.tool_calls:
                messages.append(message)

                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    logger.info(f"Executing MCP tool {func_name} with args {args}")
                    
                    try:
                        # Wykonanie narzędzia przez MCP
                        mcp_res = await mcp_session.call_tool(func_name, arguments=args)
                        # Ekstrakcja z wyniku
                        content_parts = [c.text for c in mcp_res.content if hasattr(c, 'text')]
                        tool_result = "\n".join(content_parts)
                        logger.info(f"MCP tool {func_name} returned {len(tool_result)} chars")
                    except Exception as e:
                        logger.error(f"MCP Tool execution error: {e}")
                        tool_result = json.dumps({"error": str(e)})

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })
            else:
                final_response = message.content or ""
                messages.append({"role": "assistant", "content": final_response})
                break
                
        logger.info("Agent execution completed.")
        if 'final_response' in locals():
            print("\n--- Finalna odpowiedź Modelu ---")
            print(final_response)
        else:
            print("\n--- Brak ostatecznej odpowiedzi ---")

if __name__ == "__main__":
    asyncio.run(main())
