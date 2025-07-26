import asyncio
import websockets
import requests
import json
import os
import time
import logging
import sys

# --- Configuração Básica ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler("k1max_automation.log")
                    ])

# --- Constantes (AJUSTADAS PARA O SIMULADOR/REAL) ---
# Estas deveriam ser lidas de um config.yml em um ambiente de produção/integração
K1_MAX_IP = "127.0.0.1"  # Para testes com Docker/Mock. Mudar para o IP real da K1 Max.
MOONRAKER_PORT = 7125   # Porta padrão da API Moonraker
ENABLE_MOCK_API_RESPONSES = True # Defina como False para usar a impressora real

# --- Cliente HTTP Genérico e Robusto ---
async def robust_http_request(method: str, url: str, json_data: dict = None, files_data: dict = None,
                              headers: dict = None, retries: int = 5, delay: int = 2) -> dict | None:
    """
    Executa uma requisição HTTP de forma robusta com retentativas e atraso exponencial.
    Retorna o JSON da resposta em caso de sucesso, ou None se todas as retentativas falharem.
    """
    for i in range(retries):
        try:
            logging.info(f"Tentativa {i+1}/{retries} de {method} para {url}...")
            if files_data:
                response = requests.request(method, url, files=files_data, headers=headers, timeout=30)
            else:
                response = requests.request(method, url, json=json_data, headers=headers, timeout=15)
            
            response.raise_for_status()
            logging.info(f"Requisição {method} para {url} bem-sucedida.")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.warning(f"Erro na requisição para {url} (tentativa {i+1}): {e}")
            if i < retries - 1:
                logging.info(f"Aguardando {delay} segundos antes de tentar novamente...")
                await asyncio.sleep(delay)
                delay *= 2
            else:
                logging.critical(f"Todas as {retries} tentativas de {method} para {url} falharam. Abortando.")
                return None
    return None

# --- Nova Classe: MoonrakerMockClient para Modularização do Mocking ---
class MoonrakerMockClient:
    """
    Simula as respostas da API Moonraker para testes sem uma impressora real.
    Permite controlar o estado simulado da impressora.
    """
    def __init__(self):
        self._printer_state = "ready" # Estado inicial padrão
        self._print_filename = None
        self._print_progress = 0.0
        logging.info("MoonrakerMockClient inicializado.")

    def set_printer_state(self, state: str):
        """Define o estado simulado da impressora (ex: 'ready', 'printing', 'error', 'complete')."""
        self._printer_state = state
        logging.info(f"Estado simulado da impressora definido para: {self._printer_state}")

    def set_print_details(self, filename: str, progress: float):
        """Define detalhes da impressão simulada."""
        self._print_filename = filename
        self._print_progress = progress
        logging.info(f"Detalhes da impressão simulada: Arquivo='{self._print_filename}', Progresso={self._print_progress:.2f}%")

    async def mock_http_request(self, method: str, url: str, json_data: dict = None, files_data: dict = None) -> dict | None:
        """Simula respostas HTTP da API Moonraker."""
        logging.info(f"MODO MOCKING ATIVO: Simulação de resposta para {method} {url}")
        
        if "server/info" in url:
            return {"result": {"api_version": "2.0.0-mock", "status": "ok"}}
        elif "printer/objects/query" in url:
            # Resposta mais dinâmica baseada no estado interno do mock
            return {
                "result": {
                    "status": {"printer": {"state": self._printer_state}},
                    "print_stats": {
                        "state": self._printer_state,
                        "filename": self._print_filename,
                        "progress": self._print_progress
                    }
                }
            }
        elif "server/files/upload" in url:
            filename = files_data['file'][0] if files_data and 'file' in files_data else "mock_file.gcode"
            self._print_filename = filename # Define o arquivo que "foi" carregado
            return {"success": True, "file_id": f"mock_file_id_{filename}"}
        elif "printer/print/start" in url:
            self.set_printer_state("printing") # Ao iniciar, muda o estado do mock para 'printing'
            return {"success": True, "job_id": "mock_job_id"}
        elif "printer/print/cancel" in url:
            self.set_printer_state("ready") # Ao cancelar, muda o estado do mock para 'ready'
            return {"success": True}
        # Adicione mais mocks conforme o script precisar de outras respostas
        return {"status": True, "message": "Mocked success for unknown endpoint"}

    async def mock_websocket_recv(self) -> str:
        """Simula o recebimento de mensagens WebSocket."""
        # Simula o progresso da impressão
        if self._printer_state == "printing" and self._print_progress < 1.0:
            self._print_progress += 0.1 # Incrementa o progresso
            if self._print_progress >= 1.0:
                self._print_progress = 1.0
                self.set_printer_state("complete") # Marca como completa ao atingir 100%

        mock_response = {
            "jsonrpc": "2.0",
            "method": "notify_status_update",
            "params": [{
                "print_stats": {
                    "state": self._printer_state,
                    "filename": self._print_filename,
                    "total_duration": 3600, # Mock de duração
                    "print_duration": self._print_progress * 3600,
                    "progress": self._print_progress
                },
                "toolhead": {"position": [10, 10, 10]},
                "extruder": {"temperature": 200, "target": 200},
                "heater_bed": {"temperature": 60, "target": 60}
            }]
        }
        await asyncio.sleep(1) # Simula um atraso de rede
        return json.dumps(mock_response)

    # Métodos mock para websocket.send e websocket.close
    async def mock_websocket_send(self, message: str):
        logging.debug(f"Mock WebSocket Send: {message[:100]}...")

    async def mock_websocket_close(self):
        logging.debug("Mock WebSocket Closed.")

# --- Nova Classe: K1MaxBridge para Desacoplamento do Fluxo Principal ---
class K1MaxBridge:
    """
    Ponte de comunicação com a impressora K1 Max via Moonraker API.
    Pode operar em modo real ou mock.
    """
    def __init__(self, ip_address: str, port: int, enable_mock: bool = False):
        self.ip_address = ip_address
        self.port = port
        self.http_url_base = f"http://{ip_address}:{port}"
        self.ws_url_base = f"ws://{ip_address}:{port}/websocket"
        self.enable_mock = enable_mock
        self.mock_client = MoonrakerMockClient() if enable_mock else None
        logging.info(f"K1MaxBridge inicializado. Modo Mock: {self.enable_mock}")

    async def _make_request(self, method: str, endpoint: str, json_data: dict = None, files_data: dict = None, headers: dict = None) -> dict | None:
        """Método interno para rotear requisições para o cliente real ou mock."""
        url = f"{self.http_url_base}/{endpoint}"
        if self.enable_mock:
            return await self.mock_client.mock_http_request(method, url, json_data, files_data)
        else:
            return await robust_http_request(method, url, json_data, files_data, headers)

    async def check_connection(self) -> bool:
        """Verifica se a API Moonraker está acessível."""
        logging.info(f"Verificando conexão com Moonraker em {self.ip_address}:{self.port}...")
        response_data = await self._make_request("GET", "server/info")
        if response_data:
            logging.info(f"Conexão com Moonraker bem-sucedida. Versão: {response_data.get('result', {}).get('api_version')}")
            return True
        logging.critical("Não foi possível conectar a Moonraker.")
        return False

    async def get_printer_state(self) -> str | None:
        """Retorna o estado atual da impressora (e.g., 'ready', 'printing', 'error')."""
        response_data = await self._make_request("GET", "printer/objects/query?full=true&websockets=false")
        if response_data:
            printer_state = response_data.get("result", {}).get("status", {}).get("printer", {}).get("state")
            logging.info(f"Estado da impressora: '{printer_state}'.")
            return printer_state
        logging.error("Não foi possível obter o estado da impressora.")
        return None

    async def is_printer_ready(self) -> bool:
        """Verifica se a impressora está no estado 'ready' ou 'idle'."""
        state = await self.get_printer_state()
        return state in ["ready", "idle"]

    async def upload_gcode(self, file_path: str) -> str | None:
        """Faz o upload de um arquivo G-code para a impressora."""
        endpoint = "server/files/upload"
        filename_on_printer = os.path.basename(file_path)

        try:
            if self.enable_mock:
                # No mock, não precisamos abrir o arquivo real
                files = {'file': (filename_on_printer, b'mock_gcode_content', 'application/octet-stream')}
            else:
                with open(file_path, 'rb') as f:
                    files = {'file': (filename_on_printer, f, 'application/octet-stream')}
            
            response_data = await self._make_request("POST", endpoint, files_data=files)
            if response_data:
                logging.info(f"Upload de '{filename_on_printer}' concluído com sucesso.")
                return filename_on_printer
            return None
        except FileNotFoundError:
            logging.error(f"Erro: Arquivo local '{file_path}' não encontrado no seu computador.")
            return None
        except Exception as e:
            logging.error(f"Erro inesperado durante o upload do G-code: {e}", exc_info=True)
            return None

    async def start_print(self, gcode_filename_on_printer: str) -> bool:
        """Inicia a impressão de um arquivo G-code já enviado."""
        endpoint = "printer/print/start"
        payload = {"filename": gcode_filename_on_printer}
        response_data = await self._make_request("POST", endpoint, json_data=payload)
        if response_data:
            logging.info(f"Comando para iniciar impressão de '{gcode_filename_on_printer}' enviado.")
            return True
        return False

    async def monitor_print_status(self, filename_expected: str) -> bool:
        """
        Monitora o status da impressão via WebSocket até a finalização ou erro.
        Retorna True se a impressão for concluída com sucesso, False caso contrário.
        """
        logging.info("Iniciando monitoramento da impressão via WebSocket...")

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
        
        print_completed_successfully = False
        max_idle_time = 120

        try:
            if self.enable_mock:
                # Usa os métodos mock de WebSocket
                websocket_send = self.mock_client.mock_websocket_send
                websocket_recv = self.mock_client.mock_websocket_recv
                websocket_close = self.mock_client.mock_websocket_close
            else:
                # Conecta ao WebSocket real
                websocket = await websockets.connect(self.ws_url_base)
                websocket_send = websocket.send
                websocket_recv = websocket.recv
                websocket_close = websocket.close

            await websocket_send(json.dumps(subscribe_message))
            logging.info("Inscrito para receber notificações de status.")

            while True:
                try:
                    response_str = await asyncio.wait_for(websocket_recv(), timeout=max_idle_time)
                    response_data = json.loads(response_str)

                    if "method" in response_data and response_data["method"] == "notify_status_update":
                        data = response_data["params"][0]
                        print_stats = data.get("print_stats", {})
                        
                        if "state" in print_stats:
                            current_state = print_stats["state"]
                            progress = print_stats.get("progress", 0) * 100
                            print_duration = print_stats.get("print_duration", 0)
                            
                            logging.info(f"Status da Impressora: {current_state} | Progresso: {progress:.2f}% | Duração: {print_duration:.0f}s")

                            if print_stats.get("filename") == filename_expected:
                                if current_state == "complete":
                                    logging.info("Impressão concluída com sucesso!")
                                    print_completed_successfully = True
                                    break
                                elif current_state in ["error", "cancelled", "shutdown"]:
                                    logging.warning(f"Impressão finalizada com status: {current_state} (Não concluída com sucesso).")
                                    break
                                elif current_state == "paused":
                                    logging.info("Impressão pausada.")
                            else:
                                logging.debug(f"Impressão diferente detectada ou estado inicial: {print_stats.get('filename')} | {current_state}")

                except asyncio.TimeoutError:
                    logging.warning(f"Nenhuma atualização de status recebida em {max_idle_time} segundos. Tentando re-subscrever.")
                    await websocket_send(json.dumps(subscribe_message))
                except websockets.exceptions.ConnectionClosedOK:
                    logging.info("Conexão WebSocket fechada normalmente.")
                    break
                except websockets.exceptions.WebSocketException as e:
                    logging.error(f"Erro de WebSocket durante o monitoramento: {e}")
                    break
                except json.JSONDecodeError as e:
                    logging.error(f"Erro ao decodificar JSON da mensagem WebSocket: {e}. Mensagem: {response_str[:200]}...")
                    break
                except Exception as e:
                    logging.error(f"Erro inesperado durante o monitoramento: {e}", exc_info=True)
                    break
        finally:
            if not self.enable_mock and not websocket.closed: # Fecha apenas se for conexão real e não estiver fechada
                await websocket_close()
            logging.info("Monitoramento de impressão encerrado.")
        return print_completed_successfully

# --- Função Principal de Automação (Exemplo de Uso da K1MaxBridge) ---
async def automate_k1max_printing_workflow(local_gcode_path: str, ip: str, port: int, use_mock: bool):
    """
    Função principal que orquestra todo o processo de automação.
    Agora usa a classe K1MaxBridge.
    """
    logging.info(f"--- Iniciando fluxo de automação para G-code: {local_gcode_path} (IP: {ip}, Porta: {port}, Mock: {use_mock}) ---")

    # Instancia a ponte com a impressora
    bridge = K1MaxBridge(ip_address=ip, port=port, enable_mock=use_mock)

    # Se estiver em modo mock, podemos pré-configurar o estado inicial do mock
    if use_mock:
        bridge.mock_client.set_printer_state("ready")
        bridge.mock_client.set_print_details(filename=os.path.basename(local_gcode_path), progress=0.0)

    # 1. Verificar Conectividade Moonraker
    if not await bridge.check_connection():
        logging.critical("Não foi possível conectar a Moonraker. Abortando automação.")
        return False

    # 2. Verificar se a impressora está pronta antes de prosseguir
    for i in range(5):
        if await bridge.is_printer_ready():
            break
        logging.warning(f"Impressora não está pronta (tentativa {i+1}/5). Aguardando 10 segundos...")
        await asyncio.sleep(10)
    else:
        logging.critical("Impressora não ficou pronta após várias tentativas. Abortando automação.")
        return False
    
    # 3. Upload do G-code
    gcode_filename_on_printer = await bridge.upload_gcode(local_gcode_path)
    if not gcode_filename_on_printer:
        logging.critical("Falha no upload do G-code. Abortando automação.")
        return False

    # 4. Iniciar Impressão e Monitorar Status
    if not await bridge.start_print(gcode_filename_on_printer):
        logging.critical("Falha ao iniciar a impressão. Abortando automação.")
        return False

    success = await bridge.monitor_print_status(gcode_filename_on_printer)
    if success:
        logging.info(f"Automação de '{gcode_filename_on_printer}' concluída com sucesso!")
        return True
    else:
        logging.warning(f"Automação de '{gcode_filename_on_printer}' falhou ou foi interrompida.")
        return False

# --- Execução Principal do Script ---
if __name__ == "__main__":
    # O caminho do G-code será passado como argumento de linha de comando.
    # Exemplo de uso no terminal:
    # python automacao_k1max.py "C:/Caminho/Para/Seu/Arquivo.gcode" --real (para impressora real)
    # python automacao_k1max.py "C:/Caminho/Para/Seu/Arquivo.gcode" --mock (para simulação com mock)
    
    if len(sys.argv) < 2:
        logging.critical("Erro: O caminho do arquivo G-code não foi fornecido como argumento de linha de comando.")
        logging.critical("Uso correto: python automacao_k1max.py \"C:\\Users\\leite\\OneDrive\\Area de Trabalho\\Klipper\\Peca T2_PLA_2h29m.gcode\" [--real | --mock]")
        sys.exit(1)

    GCODE_LOCAL_PATH = sys.argv[1]
    
    # Determina se deve usar o modo mock com base nos argumentos
    use_mock_mode = ENABLE_MOCK_API_RESPONSES # Valor padrão da constante
    if "--real" in sys.argv:
        use_mock_mode = False
        logging.info("Modo de execução: IMPRESSORA REAL")
    elif "--mock" in sys.argv:
        use_mock_mode = True
        logging.info("Modo de execução: MOCKING")
    
    # Ajusta o IP para o mock se o modo mock estiver ativo e o IP não for localhost
    # Isso garante que se você esquecer de mudar o IP para 127.0.0.1 em modo mock, ele ainda funcione
    if use_mock_mode and K1_MAX_IP != "127.0.0.1":
        logging.warning(f"IP da impressora ({K1_MAX_IP}) não é localhost, mas o modo mock está ativado. Forçando IP para 127.0.0.1 para simulação.")
        K1_MAX_IP = "127.0.0.1"

    if not os.path.exists(GCODE_LOCAL_PATH) and not use_mock_mode: # Arquivo não precisa existir no modo mock
        logging.error(f"Erro: O arquivo G-code '{GCODE_LOCAL_PATH}' não foi encontrado no seu computador.")
        logging.error("Por favor, verifique o caminho e nome do arquivo.")
        sys.exit(1)
    elif not os.path.exists(GCODE_LOCAL_PATH) and use_mock_mode:
        logging.warning(f"Aviso: O arquivo G-code '{GCODE_LOCAL_PATH}' não foi encontrado, mas o modo mock está ativo. A simulação continuará.")

    # Roda a função assíncrona principal
    asyncio.run(automate_k1max_printing_workflow(GCODE_LOCAL_PATH, K1_MAX_IP, MOONRAKER_PORT, use_mock_mode))