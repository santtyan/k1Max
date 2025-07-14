import cv2
import numpy as np
import logging
import asyncio # Necessário para asyncio.sleep, se usado
import os # Para verificar a existência da imagem de referência

# --- Configuração de Logging para este módulo ---
# Ele usará a configuração principal do script quando importado,
# mas é bom tê-lo aqui para testar o módulo individualmente se necessário.
# Se já estiver configurado no script principal, estas linhas podem ser redundantes,
# mas não causam problema.
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler()
                    ])

# --- Constantes para a Câmera (AJUSTE PARA SUA K1 MAX REAL) ---
# Você precisará descobrir a URL real do stream da sua K1 Max.
# Geralmente acessível via interface web (Mainsail/Fluidd) na seção da câmera.
# Exemplo comum: http://<IP_DA_K1MAX>:8080/webcam/?action=stream
# Ou se a K1 Max usa algo como Crowsnest/Ustreamer interno.
WEBCAM_STREAM_URL = "http://SEU_IP_DA_K1MAX:8080/webcam/?action=stream" # <--- AJUSTE AQUI!

# Caminho para a imagem de referência da mesa vazia.
# Esta imagem deve ser capturada da sua impressora com a mesa vazia e bem iluminada.
REFERENCE_IMAGE_PATH = "C:\\Users\\leite\\OneDrive\\Área de Trabalho\\Klipper\\mesa_vazia_referencia.jpg" # <--- AJUSTE AQUI!
# Exemplo Linux: "/home/seu_usuario/impressao3d/mesa_vazia_referencia.jpg"

MIN_OBJECT_AREA = 1000 # Área mínima em pixels para considerar a presença de um objeto (ajuste experimentalmente)
# Valores entre 500 e 5000 pixels são comuns.
# Um valor muito baixo detecta poeira, um muito alto ignora objetos pequenos.


async def check_bed_clear(camera_stream_url: str, reference_image_path: str, threshold: float = 25.0) -> bool:
    """
    Verifica se a mesa de impressão está limpa de objetos, comparando o frame atual
    com uma imagem de referência de uma mesa vazia.

    Args:
        camera_stream_url (str): URL do stream da webcam (Ex: http://IP:PORT/stream).
        reference_image_path (str): Caminho para a imagem PNG/JPG da mesa vazia para referência.
        threshold (float): Limiar de diferença de pixel (0-255). Se a diferença média for maior que isso,
                           indica um objeto. Ajuste experimentalmente.

    Returns:
        bool: True se a mesa estiver clara, False se um objeto for detectado ou houver erro.
    """
    if not os.path.exists(reference_image_path):
        logging.critical(f"Erro: Imagem de referência '{reference_image_path}' não encontrada. Mesa não verificada.")
        return False # Não podemos verificar sem a referência

    # Carrega a imagem de referência (mesa vazia)
    try:
        reference_image = cv2.imread(reference_image_path, cv2.IMREAD_GRAYSCALE)
        if reference_image is None:
            logging.critical(f"Erro: Não foi possível carregar a imagem de referência '{reference_image_path}'. Verifique o caminho e o formato.")
            return False
        # Redimensiona a imagem de referência para um tamanho padrão (para consistência de comparação)
        # O tamanho (640, 480) é comum, mas pode ser ajustado para o da sua câmera.
        reference_image = cv2.resize(reference_image, (640, 480))
        logging.info(f"Imagem de referência '{os.path.basename(reference_image_path)}' carregada para comparação.")
    except Exception as e:
        logging.critical(f"Erro ao processar imagem de referência: {e}", exc_info=True)
        return False

    cap = cv2.VideoCapture(camera_stream_url)
    if not cap.isOpened():
        logging.error(f"Não foi possível acessar o stream da webcam em: {camera_stream_url}. Verifique o URL ou se a câmera está ativa.")
        return False

    try:
        logging.info("Capturando e analisando frames da webcam para verificar a mesa...")
        # Captura e analisa múltiplos frames para maior robustez
        num_frames_to_check = 5
        objects_detected_count = 0
        
        for i in range(num_frames_to_check):
            ret, frame = cap.read() # Captura um frame
            if not ret:
                logging.warning(f"Falha ao ler frame da webcam (tentativa {i+1}/{num_frames_to_check}).")
                await asyncio.sleep(0.5) # Pequena pausa antes de tentar novamente
                continue

            # Converte o frame capturado para escala de cinza e aplica blur
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_frame = cv2.resize(gray_frame, (reference_image.shape[1], reference_image.shape[0])) # Redimensiona para o mesmo tamanho

            # Calcula a diferença absoluta entre a referência e o frame atual
            frame_delta = cv2.absdiff(reference_image, gray_frame)
            
            # Aplica um limiar para destacar as diferenças (áreas com pixels muito diferentes)
            thresh = cv2.threshold(frame_delta, int(threshold), 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2) # Dilata para unir áreas próximas

            # Encontra contornos nas áreas de diferença
            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            object_found_in_frame = False
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > MIN_OBJECT_AREA: # Se a área for maior que o mínimo, é um objeto
                    (x, y, w, h) = cv2.boundingRect(contour)
                    logging.warning(f"Objeto detectado na mesa! Área: {area}px (Frame {i+1}). Posição aprox: ({x},{y}) - {w}x{h}.")
                    objects_detected_count += 1
                    object_found_in_frame = True
                    break # Basta um objeto para considerar a mesa não limpa neste frame
            
            if object_found_in_frame:
                # Pode adicionar uma pausa maior ou retornar False imediatamente se a detecção for crítica
                pass # ou break para sair do loop de frames se um objeto for encontrado

            await asyncio.sleep(0.1) # Pequena pausa entre frames
    finally:
        cap.release() # Sempre libera o recurso da câmera

    if objects_detected_count > 0:
        logging.critical(f"Verificação da mesa concluída: OBJETOS DETECTADOS em {objects_detected_count}/{num_frames_to_check} frames. Impressão abortada.")
        return False
    else:
        logging.info("Verificação da mesa concluída: Mesa de impressão parece estar limpa.")
        return True

# Exemplo de como você chamaria esta função (para teste isolado deste módulo)
async def main_camera_test():
    logging.info("Iniciando teste de câmera isolado...")
    # Lembre-se de ajustar WEBCAM_STREAM_URL e REFERENCE_IMAGE_PATH
    if await check_bed_clear(WEBCAM_STREAM_URL, REFERENCE_IMAGE_PATH):
        logging.info("Mesa vazia. Pode iniciar a impressão.")
    else:
        logging.warning("Mesa com objetos. Não iniciar a impressão.")

if __name__ == "__main__":
    # Importante: O ambiente Docker simulado não tem acesso a câmeras físicas.
    # Para testar este módulo, você precisaria de:
    # 1. Uma K1 Max real.
    # 2. Um Raspberry Pi com câmera conectada (e software de stream como MJPEG-Streamer/Crowsnest/Ustreamer).
    # 3. Ou um "mock" de stream de vídeo que serve imagens para o OpenCV.
    logging.info("Para testar este módulo, o WEBCAM_STREAM_URL deve ser de uma câmera real ou simulada.")
    logging.info(f"URL de teste configurada: {WEBCAM_STREAM_URL}")
    logging.info(f"Caminho da imagem de referência: {REFERENCE_IMAGE_PATH}")
    # asyncio.run(main_camera_test()) # Descomente para testar este módulo isoladamente