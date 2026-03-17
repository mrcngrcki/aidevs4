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

# Import nowej funkcjonalności z extract_map
from extract_map import analyze_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    load_dotenv(find_dotenv())
    
    HUB_URL = os.getenv("HUB_URL")
    HUB_API_KEY = os.getenv("HUB_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    current_image_url = f"{HUB_URL}/data/{HUB_API_KEY}/electricity.png"
    
    logger.info(f"Pobieram mapę z obrazka: {current_image_url}")
    board_state = analyze_image(current_image_url)
    board_json_str = board_state.model_dump_json(indent=2)
    logger.info("Otrzymany wektor JSON (stan początkowy planszy):\n" + board_json_str)

    # ----------- Uruchamiamy Agenta --------------
    logger.info("--- URUCHAMIAM AGENTA ROZWIĄZUJĄCEGO ŁAMIGŁÓWKĘ ---")
    
    SYSTEM_PROMPT = """
# Rola
Jesteś zaawansowanym agentem AI rozwiązującym logiczne łamigłówki przestrzenne. Masz do dyspozycji interaktywne narzędzia (Tools), za pomocą których bezpośrednio modyfikujesz stan planszy.

# Kontekst
Otrzymujesz stan początkowy planszy w formacie JSON. Plansza to siatka kafelków z fragmentami przewodów. 
**UWAGA NA UKŁAD:** Po PRAWEJ stronie znajdują się 3 punkty wejściowe (`inputs`), a po LEWEJ stronie na samym dole znajduje się 1 docelowy punkt wyjściowy (`outputs`).

# Zadanie
Twoim zadaniem jest znalezienie i wykonanie takiej sekwencji obrotów kafelków, aby połączyć wszystkie 3 punkty wejściowe z prawej strony z 1 punktem wyjściowym po lewej stronie za pomocą nieprzerwanej linii przewodu.

# Zasady Mechaniki
1. **Zasady łączenia**: Kafelki łączą się ze sobą tylko wtedy, gdy mają naprzeciwległe porty na styku.
   *(Przykład: aby kafelek po prawej połączył się z kafelkiem po lewej, prawy musi mieć aktywny port `W`, a lewy aktywny port `E`).*
2. **Efekt obrotu**: Jeden obrót (90 stopni zgodnie z ruchem wskazówek zegara) zmienia porty w następujący sposób: `N -> E`, `E -> S`, `S -> W`, `W -> N`.
   *(Przykład: kafelek `["N", "E"]` po jednym obrocie staje się `["E", "S"]`).*

# Dostępne Narzędzia
Masz podpięte narzędzie `rotate(row, column)`:
- Narzędzie to obraca wskazany kafelek o **90 stopni w prawo** (jeden obrót).
- Jeśli z Twoich obliczeń wynika, że kafelek wymaga obrotu o 180 stopni, musisz użyć narzędzia `rotate` **dwa razy** (2 wywołania / 2 obroty) dla tych samych współrzędnych.
- Jeśli wymaga obrotu o 270 stopni, użyj narzędzia **trzy razy**.

UWAGA! Należy użyć Function Calling do wywołania narzędzi (Tools)!

# Instrukcje wykonania
1. **Analiza (Chain of Thought)**: Zanim użyjesz jakiegokolwiek narzędzia, przeanalizuj dostarczony JSON. Krok po kroku zaplanuj w tekście ścieżki łączące 3 wejścia po prawej stronie z 1 wyjściem po lewej. Oblicz w pamięci, ile obrotów potrzebuje każdy kafelek na trasie, aby jego porty idealnie pasowały do sąsiadów.
2. **Wywołanie narzędzi (Execution)**: Po ułożeniu pełnego planu, wywołaj narzędzie `rotate(row, column)` za pomocą Function Call! (możesz wywołać wielokrotnie naraz). Wywołaj je dokładnie tyle razy i dla takich współrzędnych, jak wynika z Twojego planu, aby rozwiązać łamigłówkę. Używaj call tools żeby tego dokonać!
"""

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    server_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared", "mcp_server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=os.environ.copy()
    )

    async with AsyncExitStack() as stack:
        logger.info("Connecting to MCP Tools server...")
        read, write = await stack.enter_async_context(stdio_client(server_params))
        mcp_session = await stack.enter_async_context(ClientSession(read, write))
        await mcp_session.initialize()
        
        response = await mcp_session.list_tools()
        mcp_tools = response.tools
        openai_tools = convert_mcp_tools_to_openai(mcp_tools)
        logger.info(f"Loaded MCP tools: {[t.name for t in mcp_tools]}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Oto aktualny stan planszy, przeanalizuj problem i wykonaj wymagane naprawy i rotacje używając Tool Calls!:\n\n{board_json_str}"}
        ]

        max_steps = 30
        for i in range(max_steps):
            logger.info(f"\n--- Krok {i+1} ---")
            
            try:
                response = await client.chat.completions.create(
                    model="gpt-5-mini", # model uzyty przez Ciebie
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                    tool_choice="auto" if openai_tools else "none"
                )
            except Exception as e:
                logger.error(f"OpenAI error: {e}")
                break

            message = response.choices[0].message
            logger.info(f"Baza myślowa agenta: {message.content}")

            if message.tool_calls:
                messages.append(message)
                
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    logger.info(f"Executing MCP tool {func_name} with args {args}")
                    
                    try:
                        mcp_res = await mcp_session.call_tool(func_name, arguments=args)
                        content_parts = [c.text for c in mcp_res.content if hasattr(c, 'text')]
                        tool_result = "\n".join(content_parts)
                        logger.info(f"MCP tool {func_name} returned: {tool_result}")
                        
                        if "FLG:" in tool_result or "{{FLG:" in tool_result:
                            logger.info(f"\n!!! ZADANIE ZAKOŃCZONE SUKCESEM. ZNALEZIONO FLAGĘ !!!\n{tool_result}")
                            return

                    except Exception as e:
                        logger.error(f"MCP Tool execution error: {e}")
                        tool_result = json.dumps({"error": str(e)})

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })
            else:
                agent_reply = message.content or ""
                messages.append({"role": "assistant", "content": agent_reply})
                
                if "gotowe" in agent_reply.lower() or "zrobione" in agent_reply.lower() or "sukces" in agent_reply.lower():
                    logger.info("Agent zgłasza zakończenie zadania, ale flaga nie została wychwycona z tooli. Sprawdź logi.")
                    break
                else:
                    messages.append({
                        "role": "user",
                        "content": "Flaga nie została jeszcze zdobyta. Kontynuuj rotacje lub przeanalizuj swój postęp."
                    })
                
        logger.info("Agent execution completed.")

if __name__ == "__main__":
    asyncio.run(main())
