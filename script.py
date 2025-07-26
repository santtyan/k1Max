import subprocess
import time
import pyautogui
import os 

# --- Configurações Essenciais ---
SLICER_PATH = r"C:\Program Files\Creality\Creality Print 6.1\CrealityPrint.exe"
STL_FILE_PATH = r"C:\Xbox_Games\obj_5_Tripod_fix_V2.STL.stl" 
IMAGES_AND_STL_FOLDER = r"C:\Xbox_Games" 

# --- Nomes das Imagens dos Botões (Capturadas por VOCÊ e salvas em C:\Xbox_Games) ---
# Certifique-se de que seus arquivos PNG correspondem a estes nomes exatos na sua pasta C:\Xbox_Games.
ARQUIVO_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'open_file_initial_button.png') 
IMPORTAR_MENU_ITEM_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'file_menu_item.png') 
IMPORTAR_STL_SPECIFIC_ITEM_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'browse_button.png') 

# --- Imagem Opcional para a Barra de Endereço do Diálogo do Windows ---
ADDRESS_BAR_ICON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'address_bar_icon.png') 

# --- Imagens para Fatiar e Imprimir (AGORA ATIVAS) ---
SLICE_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'slice_button.png') 
PRINT_SEND_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'print_send_button.png') # ESTA LINHA ESTÁ ATIVA AGORA

# --- Função Auxiliar para Encontrar e Clicar ---
def find_and_click(image_path, timeout=30, confidence=0.9):
    location = None
    timeout_start = time.time()
    print(f"Procurando '{os.path.basename(image_path)}' na tela...") 
    
    while location is None and (time.time() - timeout_start) < timeout:
        try:
            location = pyautogui.locateOnScreen(image_path, confidence=confidence, grayscale=False)
        except Exception as e:
            # O erro de leitura de imagem agora deve estar resolvido.
            print(f"Erro ao tentar ler ou procurar imagem '{os.path.basename(image_path)}': {e}") 
        time.sleep(0.5) 

    if location:
        print(f"Elemento '{os.path.basename(image_path)}' encontrado em: {location}. Clicando...")
        center_x = location.left + location.width / 2
        center_y = location.top + location.height / 2
        pyautogui.click(center_x, center_y)
        return True
    else:
        print(f"Erro: Elemento '{os.path.basename(image_path)}' não encontrado na tela após {timeout} segundos.")
        return False

# --- Bloco Principal de Execução ---
slicer_process = None 
try:
    print(f"Iniciando o slicer: {SLICER_PATH}")
    slicer_process = subprocess.Popen([SLICER_PATH])
    time.sleep(25) # Tempo para o slicer carregar completamente

    print("Iniciando a automação do fluxo STL -> Fatiamento -> Impressão no slicer...")

    # --- SEQUÊNCIA DE CLIQUES PARA ABRIR O ARQUIVO STL ---
    if find_and_click(ARQUIVO_BUTTON_IMAGE):
        time.sleep(1.5) 
        
        if find_and_click(IMPORTAR_MENU_ITEM_IMAGE):
            time.sleep(1.5) 
            
            if find_and_click(IMPORTAR_STL_SPECIFIC_ITEM_IMAGE):
                time.sleep(2.5) 
                
                print(f"Digitando o caminho completo do arquivo STL: {STL_FILE_PATH}") 
                pyautogui.typewrite(STL_FILE_PATH) 
                pyautogui.press('enter') 
                time.sleep(15) # Tempo para o arquivo STL ser carregado e renderizado. AJUSTE se for modelo grande!
                print("Arquivo STL carregado (esperamos!).") 

                # --- Clicar no botão "Fatiar" (Slice) MÚLTIPLAS VEZES ---
                num_clicks_slice = 2 # Dois cliques no botão Fatiar
                slice_clicked_successfully = False 

                for i in range(num_clicks_slice):
                    print(f"Tentando clicar no botão Fatiar (tentativa {i+1}/{num_clicks_slice})...")
                    if find_and_click(SLICE_BUTTON_IMAGE):
                        slice_clicked_successfully = True
                        if i < num_clicks_slice - 1: 
                            time.sleep(0.5) 
                    else:
                        print(f"Falha ao encontrar o botão de Fatiar na tentativa {i+1}. Parando os múltiplos cliques.")
                        break 

                if slice_clicked_successfully:
                    time.sleep(15) # Espera o processo de fatiamento. Pode precisar ser MUITO mais longo para modelos complexos!
                    print("Fatiamento concluído (esperamos!).") 
                    
                    # --- ATIVADO: Clicar no botão "Imprimir" ou "Enviar para Impressora" ---
                    if find_and_click(PRINT_SEND_BUTTON_IMAGE): # LÓGICA ATIVA AQUI
                        time.sleep(5) # Tempo para o comando ser enviado para a impressora e a impressão iniciar
                        print("Comando de impressão enviado para a K1 Max!")
                        print("\n--- Automação do fluxo completo (STL -> Fatiar -> Imprimir) finalizada ---")
                    else:
                        print(f"Falha ao encontrar o botão de Imprimir/Enviar ('{os.path.basename(PRINT_SEND_BUTTON_IMAGE)}').")
                else:
                    print(f"Falha persistente ao encontrar e clicar no botão de Fatiar ('{os.path.basename(SLICE_BUTTON_IMAGE)}').") 
            else:
                print(f"Falha ao encontrar o item 'Importar 3MF/STL/...' ('{os.path.basename(IMPORTAR_STL_SPECIFIC_ITEM_IMAGE)}').") 
        else:
            print(f"Falha ao encontrar o item de menu 'Importar' ('{os.path.basename(IMPORTAR_MENU_ITEM_IMAGE)}').") 
    else:
        print(f"Falha ao encontrar o botão/menu 'Arquivo' ('{os.path.basename(ARQUIVO_BUTTON_IMAGE)}').") 

except FileNotFoundError:
    print(f"Erro: Slicer não encontrado em '{SLICER_PATH}'. Verifique o caminho. O arquivo 'CrealityPrint.exe' realmente existe lá?") 
except Exception as e:
    print(f"Ocorreu um erro inesperado durante a automação: {e}") 
finally:
    if slicer_process is not None and slicer_process.poll() is None: 
        print("\nFechando o slicer...")
        slicer_process.terminate()
        time.sleep(5) 
        if slicer_process.poll() is None: 
            slicer_process.kill() 
        print("Slicer fechado.")
    elif slicer_process is None:
        print("Slicer não foi iniciado ou já estava fechado.")