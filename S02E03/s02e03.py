import os
import sys
import urllib.request
import json
import logging
import asyncio
import tiktoken
from dotenv import load_dotenv, find_dotenv

def count_tokens(text: str, model_name: str = "gpt-5-mini") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except BaseException:
        # Fallback jeżeli tiktoken nie rozpoznaje modelu, spróbuj popularny typ gpt-4o:
        try:
            return len(tiktoken.encoding_for_model("gpt-4o").encode(text))
        except BaseException:
            return len(text) // 4
from openai import AsyncOpenAI
from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

load_dotenv(find_dotenv())
    
HUB_URL = os.getenv("HUB_URL")
HUB_API_KEY = os.getenv("HUB_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

LOG_FILE_URL = f"{HUB_URL}/data/{HUB_API_KEY}/failure.log"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_file_if_missing(url):
    if not url:
        print("Brak adresu URL do pobrania.")
        return None

    target_dir = os.path.dirname(os.path.abspath(__file__))
    file_name = url.split("/")[-1]
    if not file_name:
        file_name = "downloaded_log.txt"
        
    target_path = os.path.join(target_dir, file_name)
    
    if os.path.exists(target_path):
        print(f"Plik '{file_name}' już istnieje w {target_dir}. Pomijam pobieranie.")
        return target_path

    print(f"Rozpoczynam pobieranie pliku z: {url}")
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(url, context=ctx) as response, open(target_path, 'wb') as out_file:
            out_file.write(response.read())
            
        print(f"Plik został pomyślnie pobrany i zapisany w: {target_path}")
        return target_path
    except Exception as e:
        print(f"Wystąpił błąd podczas pobierania pliku: {e}")
        return None

async def pre_filter_logs(client: AsyncOpenAI, file_path: str) -> str:
    """Uses LLM to quickly discard unrelated non-[INFO] logs, significantly reducing context for Agent."""
    with open(file_path, "r", encoding="utf-8") as f:
        logs_content = f.read()
        
    logger.info(f"[PRE-FILTER] Wysyłam {len(logs_content.splitlines())} wpisów do wstępnej selekcji przez LLM...")
    
    system_prompt = """Jesteś rygorystycznym filtrem zdarzeń elektrowni.
Na wejściu otrzymujesz zbiór logów fabrycznych. Musisz wyrzucić większość z nich.
Zostaw TYLKO logi, które dotyczą awarii systemów (zasilania, chłodzenia, pomp przepływowych, oprogramowania sterującego).
Całkowicie usuń logi normalnej, standardowej pracy, konserwacji czujników, testów, etc., bez względu na to, jak ważne się wydają, chyba że zgłaszają błąd.
NICZEGO NIE MODYFIKUJ w logach, po prostu ZMIEJSZ ICH ILOŚĆ (zwróć oryginalne linijki błędu uszeregowane chronologicznie).
NIE dodawaj komentarzy ani formatowania markdown (```).
"""
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": logs_content}
            ]
        )
        filtered = resp.choices[0].message.content.strip()
        
        pre_filtered_path = file_path.replace(".log", "_llm_filtered.log")
        with open(pre_filtered_path, "w", encoding="utf-8") as out:
            out.write(filtered)
            
        logger.info(f"[PRE-FILTER] Udało się zredukować plik z logami do {len(filtered.splitlines())} wierszy.")
        return pre_filtered_path
    except Exception as e:
        logger.error(f"Błąd podczas pre-filtrowania: {e}")
        return file_path

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

async def run_agent(filtered_log_path: str, original_log_path: str):
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    server_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared", "mcp_server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=os.environ.copy()
    )

    async with AsyncExitStack() as stack:
        logger.info("Connecting to MCP Tools server...")
        read_stream, write_stream = await stack.enter_async_context(stdio_client(server_params))
        mcp_session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await mcp_session.initialize()
        
        response = await mcp_session.list_tools()
        mcp_tools = response.tools
        openai_tools = convert_mcp_tools_to_openai(mcp_tools)
        
        logger.info(f"Loaded MCP tools")

        system_prompt = f"""Jesteś analitykiem systemów elektrowni. Twoim celem jest skondensowanie logów awarii z zachowaniem restrykcyjnych reguł oraz zdobycie sygnatury weryfikacyjnej (flagi).

ZASADY:
- BEZWZGLĘDNY ZAKAZ: Nie wolno Ci edytować ani zmieniać oryginalnego formatu daty i godziny w logach. Daty muszą zostać nietknięte.
- Utrzymuj każdą log-linijkę osobno, format line-by-line (czas na początku + treść).
- Logi dotyczą awarii w elektrowni (zasilanie, chłodzenie, pompy wodne, oprogramowanie i inne podzespoły). Twoim zadaniem jest SKONDENSOWANIE opisów. 
- Zredaguj każdy wpis tak, aby zawierał JEDYNIE najważniejsze, surowe fakty o działaniu w/w podzespołów. Wyrzuć ozdobniki, używaj ekstremalnie krótkich zdań.

ALGORYTM:
1. Pobierz dane poprzez narzędzie z mcp servera read_local_file (przefiltrowane dane masz pod: {filtered_log_path}). Możesz też zajrzeć do pełnego pliku ({original_log_path}).
2. Zastosuj się do powyższych ZASAD we własnej pamięci (nie edytuj plików) i prześlij skompresowany, gotowy tekst za pomocą narzędzia send_logs_to_api.
3. Analizuj odpowiedź API (powie Ci, czego brakuje lub czy logi są za długie):
   - Brak danych: znajdź właściwe wpisy w pliku pełnym, skondensuj je, dopisz do swojej wersji i użyj narzędzia ponownie.
   - Za długo: skróć treść jeszcze mocniej i wyślij ponownie.
4. Działaj aż do skutku, kiedy w oknie zwrotki od API otrzymasz frazę 'FLG'.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Ruszaj do działania. Zacznij od pobrania wyfiltrowanych danych."}
        ]

        for iteration in range(15):
            logger.info(f"\n--- Iteracja {iteration+1} ---")
            
            try:
                resp = await client.chat.completions.create(
                    model="gpt-5-mini",
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                    tool_choice="auto" if openai_tools else "none"
                )
            except Exception as e:
                logger.error(f"OpenAI API error: {e}")
                break
                
            message = resp.choices[0].message
            logger.info(f"Rozważania Agenta:\n{message.content}")
            
            if message.tool_calls:
                messages.append(message)
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    if func_name == "send_logs_to_api":
                        logs_body = args.get("logs_content", "")
                        tokens_sent_to_api = count_tokens(logs_body)
                        logger.info(f"[STATS] Oczekiwana liczba tokenów dla zawartości wysyłanego za chwilę payloadu do mock-api: {tokens_sent_to_api} tokenów")
                        logger.info(f"-> Agent wysyła {len(logs_body.splitlines())} wpisów/wierszy do weryfikacji w interfejsie API.")
                    else:
                        logger.info(f"-> Agent decyduje się wywołać z MCP Server: {func_name}")
                    
                    try:
                        mcp_res = await mcp_session.call_tool(func_name, arguments=args)
                        content_parts = [c.text for c in mcp_res.content if hasattr(c, 'text')]
                        tool_result = "\n".join(content_parts)
                        
                        logger.info(f"<- ZWROTKA Z NARZĘDZIA ({func_name}):\n{tool_result}\n")
                        
                        if "FLG:" in tool_result or "{{FLG:" in tool_result or "FLG" in tool_result\
                                and "MOCK" not in tool_result:
                            logger.info(f"\n!!! SYSTEM ZAMELDOWAŁ FLAGĘ !!!\n{tool_result}")
                            return
                            
                    except Exception as e:
                        logger.error(f"MCP Tool error ({func_name}): {e}")
                        tool_result = json.dumps({"error": str(e)})
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })
            else:
                messages.append({"role": "assistant", "content": message.content or ""})
                messages.append({"role": "user", "content": "Jeśli zadanie nie jest gotowe (brak 'FLG' z API), powtarzaj korekty wędrując do oryginalnych danych z pliku i operuj za pomocą send_logs_to_api."})
                
        logger.info("Iteracje zostały wyczerpane.")

async def main():
    downloaded_path = download_file_if_missing(LOG_FILE_URL)
    
    if downloaded_path:
        filtered_path = downloaded_path.replace(".log", "_filtered.log")
        if downloaded_path == filtered_path:
            filtered_path = downloaded_path + "_filtered"
            
        print(f"Rozpoczynam filtrowanie pliku (usuwanie linii z [INFO])...")
        with open(downloaded_path, "r", encoding="utf-8") as f_in:
            with open(filtered_path, "w", encoding="utf-8") as f_out:
                for line in f_in:
                    if "[INFO]" not in line:
                        f_out.write(line)
        print(f"Zapisano przefiltrowany plik: {filtered_path}")

        print("\nRozpoczynam wstępne filtrowanie zawartości przez OpenAI (Pre-Filter)...")
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        pre_filtered_path = await pre_filter_logs(client, filtered_path)

        print("Rozpoczynam sesyjną asynchroniczną pętlę Agentic MCP...")
        await run_agent(pre_filtered_path, downloaded_path)

if __name__ == "__main__":
    asyncio.run(main())