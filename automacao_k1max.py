import asyncio
import websockets
import requests
import json
import os
import time
import logging
import sys # Importado para lidar com argumentos de linha de comando

# --- Configuraçao Basica ---
# Configure o logging para ter mensagens claras no console e em um arquivo
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler(), # Mostra logs no console
                        logging.FileHandler("k1max_automation.log") # Salva logs em um arquivo
                    ])

# --- Constantes (AJUSTADAS PARA O SIMULADOR DOCKER) ---
K1_MAX_IP = "127.0.0.1"  # IP do seu simulador Docker (localhost)
MOONRAKER_PORT = 7125  # Porta padrao da API Moonraker (valida para o simulador)
HTTP_URL_BASE = f"http://{K1_MAX_IP}:{MOONRAKER_PORT}"
WS_URL_BASE = f"ws://{K1_MAX_IP}:{MOONRAKER_PORT}/websocket"

# --- ATENÇAO: Constantes para Mocking (APENAS PARA TESTES SEM CONEXAO REAL) ---
# Defina isso como True para ativar o modo de mocking.
# Quando for para a impressora real, defina como False ou remova.
ENABLE_MOCK_API_RESPONSES = True 

# --- Funçoes de Interaçao com a Impressora (Melhoradas com Robustez) ---

async def robust_http_request(method: str, url: str, json_data: dict = None, files_data: dict = None,
                              headers: dict = None,
                              retries: int = 5, delay: int = 2) -> dict | None:
    """
    Executa uma requisiçao HTTP de forma robusta com retentativas e atraso exponencial.
    Retorna o JSON da resposta em caso de sucesso, ou None se todas as retentativas falharem.
    """
    if ENABLE_MOCK_API_RESPONSES and "127.0.0.1" in url: # Ativa mocking se for para localhost E a flag estiver ligada
        logging.info(f"MODO MOCKING ATIVO: Simulaçao de resposta para {method} {url}")
        if "server/info" in url:
            return {"result": {"api_version": "2.0.0-mock", "status": "ok"}}
        elif "printer/objects/query" in url:
            # Simula a impressora como 'printing' para testar o fluxo de monitoramento
            # A chave 'printer' deve estar dentro de 'status'
            mock_state = "printing" if "Peca T2_PLA_2h29m.gcode" in url else "ready"
            return {"result": {"status": {"printer": {"state": mock_state}}, "print_stats": {"state": mock_state, "progress": 0.0}}}
        elif "server/files/upload" in url:
            return {"success": True, "file_id": "mock_file_id_Peca_T2_PLA_2h29m.gcode"}
        elif "printer/print/start" in url:
            return {"success": True, "job_id": "mock_job_id"}
        # Adicione mais mocks conforme o script precisar de outras respostas
        return {"status": True, "message": "Mocked success for unknown endpoint"}
    
    # --- CÓDIGO REAL DE REQUISIÇAO HTTP (ABAIXO SÓ EXECUTA SE MOCKING ESTIVER DESATIVADO OU NAO FOR LOCALHOST) ---
    for i in range(retries):
        try:
            logging.info(f"Tentativa {i+1}/{retries} de {method} para {url} (Real)...")
            if files_data:
                response = requests.request(method, url, files=files_data, headers=headers, timeout=30)
            else:
                response = requests.request(method, url, json=json_data, headers=headers, timeout=15)
            
            response.raise_for_status()
            logging.info(f"Requisiçao {method} para {url} bem-sucedida (Real).")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.warning(f"Erro na requisiçao para {url} (tentativa {i+1}): {e} (Real)")
            if i < retries - 1:
                logging.info(f"Aguardando {delay} segundos antes de tentar novamente (Real)...")
                await asyncio.sleep(delay)
                delay *= 2
            else:
                logging.critical(f"Todas as {retries} tentativas de {method} para {url} falharam (Real). Abortando.")
                return None
    return None

async def check_moonraker_connection(ip_address: str) -> bool:
    """Verifica se a API Moonraker do simulador esta acessivel via HTTP."""
    url = f"http://{ip_address}:{MOONRAKER_PORT}/server/info"
    # Usamos robust_http_request para a verificaçao inicial
    response_data = await robust_http_request("GET", url, retries=3, delay=1) # Menos retentativas para ping inicial
    if response_data:
        logging.info(f"Conexao com Moonraker do simulador bem-sucedida. Versao: {response_data.get('result', {}).get('api_version')}")
        return True
    return False

async def is_printer_ready(ip_address: str) -> bool:
    """
    Verifica se o Klipper da impressora simulada esta no estado 'ready' ou 'idle'.
    """
    url = f"http://{ip_address}:{MOONRAKER_PORT}/printer/objects/query?full=true&websockets=false"
    response_data = await robust_http_request("GET", url, retries=1, delay=0) # Sem retentativas, apenas consulta rapida
    
    if response_data:
        printer_state = response_data.get("result", {}).get("status", {}).get("printer", {}).get("state")
        if printer_state in ["ready", "idle"]:
            logging.info(f"Impressora esta no estado '{printer_state}'. Pronta para operaçao.")
            return True
        else:
            logging.warning(f"Impressora nao esta pronta. Estado atual: '{printer_state}'.")
            return False
    else:
        logging.error("Nao foi possivel obter o estado da impressora.")
        return False

async def upload_gcode(file_path: str, ip_address: str) -> str | None:
    """
    Faz o upload de um arquivo G-code para o simulador da impressora usando robust_http_request.
    Retorna o nome do arquivo no servidor do simulador (sem caminho) em caso de sucesso.
    """
    url = f"{HTTP_URL_BASE}/server/files/upload"
    filename_on_printer = os.path.basename(file_path)

    try:
        with open(file_path, 'rb') as f:
            files = {'file': (filename_on_printer, f, 'application/octet-stream')}
            response_data = await robust_http_request("POST", url, files_data=files, retries=3, delay=5) # Retentativas para upload
            if response_data:
                logging.info(f"Upload de '{filename_on_printer}' para o simulador concluido com sucesso.")
                return filename_on_printer
            return None
    except FileNotFoundError:
        logging.error(f"Erro: Arquivo local '{file_path}' nao encontrado no seu computador.")
        return None
    except Exception as e:
        logging.error(f"Erro inesperado durante o upload do G-code: {e}", exc_info=True)
        return None

async def start_print(gcode_filename_on_printer: str, ip_address: str) -> bool:
    """
    Inicia a impressao de um arquivo G-code ja enviado para o simulador da impressora usando robust_http_request.
    """
    url = f"{HTTP_URL_BASE}/printer/print/start"
    payload = {"filename": gcode_filename_on_printer}
    response_data = await robust_http_request("POST", url, json_data=payload, retries=3, delay=5) # Retentativas para iniciar
    
    if response_data:
        logging.info(f"Comando para iniciar impressao de '{gcode_filename_on_printer}' enviado ao simulador.")
        return True
    return False

async def monitor_print_status(websocket: websockets.WebSocketClientProtocol, filename_expected: str) -> bool:
    """
    Monitora o status da impressao via WebSocket no simulador ate a finalizaçao ou erro.
    Retorna True se a impressao for concluida com sucesso, False caso contrario.
    """
    logging.info("Iniciando monitoramento da impressao no simulador via WebSocket...")

    subscribe_message = {
        "jsonrpc": "2.0",
        "method": "printer.objects.subscribe",
        "params": {
            "objects": {
                "print_stats": {"state": None, "filename": None, "total_duration": None, "print_duration": None, "progress": None},
                "toolhead": {"position": None},
                "extruder": {"temperature": None, "target": None},
                "heater_bed": {"temperature": None, "target": None}
            }
        }
    }
    await websocket.send(json.dumps(subscribe_message))
    logging.info("Inscrito para receber notificaçoes de status do simulador.")

    print_completed_successfully = False
    max_idle_time = 120

    try:
        while True:
            try:
                response_str = await asyncio.wait_for(websocket.recv(), timeout=max_idle_time)
                response_data = json.loads(response_str)

                if "method" in response_data and response_data["method"] == "notify_status_update":
                    data = response_data["params"][0]
                    print_stats = data.get("print_stats", {})
                    
                    if "state" in print_stats:
                        current_state = print_stats["state"]
                        progress = print_stats.get("progress", 0) * 100
                        print_duration = print_stats.get("print_duration", 0)
                        
                        logging.info(f"Status do Simulador: {current_state} | Progresso: {progress:.2f}% | Duraçao: {print_duration:.0f}s")

                        if print_stats.get("filename") == filename_expected:
                            if current_state == "complete":
                                logging.info("Impressao simulada concluida com sucesso!")
                                print_completed_successfully = True
                                break
                            elif current_state in ["error", "cancelled", "shutdown"]:
                                logging.warning(f"Impressao simulada finalizada com status: {current_state} (Nao concluida com sucesso).")
                                break
                            elif current_state == "paused":
                                logging.info("Impressao simulada pausada.")
                        else:
                             logging.debug(f"Impressao simulada diferente detectada ou estado inicial: {print_stats.get('filename')} | {current_state}")

            except asyncio.TimeoutError:
                logging.warning(f"Nenhuma atualizaçao de status do simulador recebida em {max_idle_time} segundos. Tentando re-subscrever.")
                await websocket.send(json.dumps(subscribe_message))
            except websockets.exceptions.ConnectionClosedOK:
                logging.info("Conexao WebSocket com simulador fechada normalmente.")
                break
            except websockets.exceptions.WebSocketException as e:
                logging.error(f"Erro de WebSocket durante o monitoramento do simulador: {e}")
                break
            except json.JSONDecodeError as e:
                logging.error(f"Erro ao decodificar JSON da mensagem WebSocket do simulador: {e}. Mensagem: {response_str[:200]}...")
            except Exception as e:
                logging.error(f"Erro inesperado durante o monitoramento do simulador: {e}", exc_info=True)
                break
    finally:
        if not websocket.closed:
            await websocket.close()
        logging.info("Monitoramento de impressao do simulador encerrado.")
    return print_completed_successfully

# --- Funçao Principal de Automaçao ---

async def automate_k1max_printing_workflow(local_gcode_path: str):
    """
    Funçao principal que orquestra todo o processo de automaçao no simulador.
    """
    logging.info(f"--- Iniciando fluxo de automaçao para G-code: {local_gcode_path} no simulador Docker ---")

    # 1. Verificar Conectividade Moonraker (Inicial)
    if not await check_moonraker_connection(K1_MAX_IP):
        logging.critical("Nao foi possivel conectar a Moonraker do simulador. Verifique se o Docker esta rodando e o simulador esta acessivel.")
        return False

    # 2. Verificar se a impressora esta pronta antes de prosseguir
    #    Tenta 5 vezes com atraso crescente para dar tempo ao Klipper de iniciar (se estivesse offline)
    for i in range(5):
        if await is_printer_ready(K1_MAX_IP):
            break
        logging.warning(f"Impressora nao esta pronta (tentativa {i+1}/5). Estado Klipper Halted? Aguardando 10 segundos...")
        await asyncio.sleep(10)
    else:
        logging.critical("Impressora nao ficou pronta apos varias tentativas. Abortando automaçao.")
        return False
    
    # 3. Upload do G-code
    gcode_filename_on_printer = await upload_gcode(local_gcode_path, K1_MAX_IP)
    if not gcode_filename_on_printer:
        logging.critical("Falha no upload do G-code para o simulador. Abortando automaçao.")
        return False

    # 4. Conectar via WebSocket e Iniciar Impressao
    try:
        # Abertura da conexao WebSocket aqui para que ela esteja ativa antes do comando de inicio e monitoramento
        async with websockets.connect(WS_URL_BASE) as websocket: 
            logging.info("Conectado via WebSocket ao simulador para automaçao.")
            
            # Comando para iniciar a impressao
            if not await start_print(gcode_filename_on_printer, K1_MAX_IP):
                logging.critical("Falha ao iniciar a impressao no simulador. Abortando automaçao.")
                return False

            # 5. Monitorar Status da Impressao
            success = await monitor_print_status(websocket, gcode_filename_on_printer)
            if success:
                logging.info(f"Automaçao de '{gcode_filename_on_printer}' no simulador concluida com sucesso!")
                return True
            else:
                logging.warning(f"Automaçao de '{gcode_filename_on_printer}' no simulador falhou ou foi interrompida.")
                return False

    except websockets.exceptions.WebSocketException as e:
        logging.critical(f"Erro fatal na conexao WebSocket com o simulador: {e}. Certifique-se de que o simulador Docker esta online e acessivel.")
        return False
    except Exception as e:
        logging.critical(f"Erro inesperado no fluxo de automaçao do simulador: {e}", exc_info=True)
        return False

# --- Execuçao Principal do Script ---
if __name__ == "__main__":
    # O caminho do G-code sera passado como argumento de linha de comando.
    # Exemplo de uso no terminal: python automacao_k1max.py "C:/Caminho/Para/Seu/Arquivo.gcode"
    
    # sys.argv[0] é o nome do script (automacao_k1max.py)
    # sys.argv[1] sera o primeiro argumento (o caminho do arquivo G-code)
    if len(sys.argv) < 2:
        logging.critical("Erro: O caminho do arquivo G-code nao foi fornecido como argumento de linha de comando.")
        logging.critical("Uso correto: python automacao_k1max.py \"C:\\Users\\leite\\OneDrive\\Area de Trabalho\\Klipper\\Peca T2_PLA_2h29m.gcode\"")
        sys.exit(1) # Sai do script com codigo de erro

    # Atribui o argumento da linha de comando a variavel GCODE_LOCAL_PATH
    # CAMINHO EXATO DO SEU ARQUIVO G-CODE:
    GCODE_LOCAL_PATH = sys.argv[1] 
    
    if not os.path.exists(GCODE_LOCAL_PATH):
        logging.error(f"Erro: O arquivo G-code '{GCODE_LOCAL_PATH}' nao foi encontrado no seu computador.")
        logging.error("Por favor, verifique o caminho e nome do arquivo.")
        sys.exit(1) # Sai do script com codigo de erro
    else:
        # Roda a funçao assincrona principal
        asyncio.run(automate_k1max_printing_workflow(GCODE_LOCAL_PATH))