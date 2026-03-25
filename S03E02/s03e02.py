import os
import requests
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")

def run_shell_command(cmd: str):
    """
    Wykonuje komendę w powłoce wirtualnej maszyny.
    
    :param cmd: Komenda do wykonania, np. 'ls -la', 'cat settings.ini'.
    :return: Wynik komendy lub informacja o błędzie.
    """
    if not api_key:
        return "Error: HUB_API_KEY not found in environment."

    url = f"{HUB_URL}/api/shell"
    payload = {
        "apikey": api_key,
        "cmd": cmd,
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            return f"Request failed with status {e.response.status_code}: {e.response.text}"
        return f"Request failed: {str(e)}"

def verify_firmware(confirmation: str):
    """
    Przesyła uzyskany kod (ECCS-...) do weryfikacji zadania.
    
    :param confirmation: Uzyskany kod z aplikacji cooler.bin.
    :return: Wynik weryfikacji.
    """
    if not api_key:
        return "Error: HUB_API_KEY not found in environment."

    url = f"{HUB_URL}/verify"
    payload = {
        "apikey": api_key,
        "task": "firmware",
        "answer": {
            "confirmation": confirmation
        }
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            return f"Verification failed: {e.response.text}"
        return f"Verification failed: {str(e)}"


def run_agent():
    client = OpenAI()
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "run_shell_command",
                "description": "Wykonuje komendę w powłoce systemu Linux na wirtualnej maszynie.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {
                            "type": "string",
                            "description": "Komenda do wykonania, np. 'ls -R /opt/firmware', 'cat /opt/firmware/cooler/settings.ini'."
                        }
                    },
                    "required": ["cmd"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "verify_firmware",
                "description": "Wysyła uzyskany kod potwierdzenia do Centrali w celu zaliczenia zadania.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmation": {
                            "type": "string",
                            "description": "Kod w formacie ECCS-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                        }
                    },
                    "required": ["confirmation"]
                }
            }
        }
    ]

    system_prompt = """Jesteś agentem AI, Twoim zadaniem jest uruchomienie oprogramowania sterownika na wirtualnej maszynie Linux i zdobycie kodu potwierdzającego. Musisz za kazdym razem uzyc dostepnych narzedzi, dopoki w odpowiedzi nie bedzie kodu ECCS-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.

CEL:
Uruchom plik binarny (nie odczytuj go!): /opt/firmware/cooler/cooler.bin
Gdy poprawnie go uruchomisz, na ekranie pojawi się kod ECCS-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx, który musisz odesłać za pomocą narzędzia `verify_firmware`.

ZADANIA DO WYKONANIA:
1. Ten 'terminal' ma nietypowy zestaw komend, to nie jest zwykły linux. Zacznij od komendy 'help' i sprawdź jakich komend mozesz uzyc.
2. Znajdź plik .gitignore i sprawdź co jest w nim zabronione. POD ZADNYM POZOREM nie wchodź w foldery wymienione w .gitignore ani nie uruchamiaj plików z nich pochodzących.
3. Spróbuj uruchomić /opt/firmware/cooler/cooler.bin i sprawdź co wypisuje.
4. Zdobądź hasło dostępowe do aplikacji (zapisane jest w kilku miejscach w systemie). Przeszukaj pliki w dostępnych katalogach (ls -R / jest dobrym startem, ale pamiętaj o ograniczeniach).
5. Przeczytaj i zmodyfikuj plik konfiguracyjny (prawdopodobnie settings.ini w /opt/firmware/cooler/), aby oprogramowanie działało poprawnie. Możesz używać komendy 'echo "nowa zawartość" > plik' do nadpisywania plików w /opt/firmware/.
6. Jeśli oprogramowanie poprosi o hasło lub inne parametry, uwzględnij to w uruchomieniu lub konfiguracji.
7. Jeśli zbyt mocno namieszasz, możesz użyć komendy 'reboot'.

ZASADY BEZPIECZEŃSTWA (BARDZO WAŻNE):
- Szanuj pliki .gitignore. Nie dotykaj plików/katalogów tam wymienionych (np. .env).
- Nie odczytuj zawartości pliku cooler.bin, co najwyżej uruchamiaj go.
- Pracujesz na koncie zwykłego użytkownika.
- NIE WOLNO Ci zaglądać do katalogów /etc, /root i /proc/.
- Złamanie zasad skutkuje blokadą dostępu!

Dostępne narzędzie `run_shell_command` pozwala na interakcję z systemem.
Kiedy uzyskasz kod ECCS-..., użyj narzędzia `verify_firmware`."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Zacznij od zbadania zawartości katalogu /opt/firmware/cooler/ i spróbuj uruchomić plik binarny."}
    ]

    log_filename = f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_filename, "w", encoding="utf-8") as log_file:
        log_file.write(f"--- AGENT LOG: {datetime.now()} ---\n")
        log_file.write(f"MODEL: gpt-5.4-mini\n\n")

        print("--- ROZPOCZĘCIE PRACY AGENTA ---")

        for step in range(30):
            step_info = f"\n--- [Krok {step+1}] ---"
            print(step_info)
            log_file.write(step_info + "\n")
            try:
                response = client.chat.completions.create(
                    model="gpt-5.4", 
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
            except Exception as e:
                err_msg = f"Błąd OpenAI: {e}"
                print(err_msg)
                log_file.write(err_msg + "\n")
                break

            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                if msg.content:
                    agent_text = f"Agent mówi: {msg.content}"
                    print(agent_text)
                    log_file.write(agent_text + "\n")
                else:
                    empty_msg = "Brak odpowiedzi od agenta i brak wywołań narzędzi."
                    print(empty_msg)
                    log_file.write(empty_msg + "\n")
                break
                
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args_str = tool_call.function.arguments
                args = json.loads(args_str)
                call_info = f"> Wywołanie: {name}({args})"
                print(call_info)
                log_file.write(call_info + "\n")
                
                if name == "run_shell_command":
                    res = run_shell_command(**args)
                elif name == "verify_firmware":
                    res = verify_firmware(**args)
                else:
                    res = "Nieznane narzędzie."

                tool_result = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
                res_info = f"< Wynik: {tool_result}"
                print(res_info)
                log_file.write(res_info + "\n")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })

                # Jeśli verif_firmware zwróciło sukces, kończymy
                if name == "verify_firmware":
                    try:
                        res_json = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                        if res_json.get("code") == 0 or "OK" in str(res_json).upper() or "FLG" in str(res_json).upper():
                            success_info = "\nZADANIE ZAKOŃCZONE SUKCESEM!"
                            print(success_info)
                            log_file.write(success_info + "\n")
                            return
                    except:
                        pass

if __name__ == "__main__":
    run_agent()
