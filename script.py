import subprocess
import time
import pyautogui
import os 

# --- Configurações Essenciais ---
SLICER_PATH = r"C:\Program Files\Creality\Creality Print 6.1\CrealityPrint.exe"

# --- Pasta onde estão o script, as imagens dos botões e os arquivos STL ---
IMAGES_AND_STL_FOLDER = r"C:\Xbox_Games" 

# --- Lista de Caminhos dos Arquivos STL (ajuste os nomes conforme necessário) ---
STL_FILES_TO_IMPORT = [
    os.path.join(IMAGES_AND_STL_FOLDER, "obj_5_Tripod_fix_V2.STL.stl"),
    os.path.join(IMAGES_AND_STL_FOLDER, "obj_6_Tripod_leg_a_V2.STL.stl"), 
    os.path.join(IMAGES_AND_STL_FOLDER, "obj_7_Tripod_leg_b_V2.STL.stl")  
]

# --- Caminho do Arquivo de Preset de Configuração ---
PRESET_FILE_PATH = os.path.join(IMAGES_AND_STL_FOLDER, "Creality K1 Max 0.4 nozzle.creality_printer (1)")

# --- Nomes das Imagens dos Botões (Capturadas por VOCÊ e salvas em C:\Xbox_Games) ---
ARQUIVO_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'open_file_initial_button.png') 
IMPORTAR_MENU_ITEM_FIRST_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'file_menu_item.png') 
IMPORTAR_STL_SPECIFIC_ITEM_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'browse_button.png') 

# --- Imagem Opcional para a Barra de Endereço do Diálogo do Windows ---
ADDRESS_BAR_ICON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'address_bar_icon.png') 

# --- Imagem para Arranjar Objetos ---
ARRANGE_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'arrange_button.png')

# --- Imagem para Importar Configurações ---
IMPORT_CONFIG_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'import_config_button.png')
IMPORTAR_MENU_ITEM_SECOND_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'file_menu_item2.png') 

# --- AQUI: A variável OVERWRITE_PRESET_BUTTON_IMAGE foi removida ---

# --- Imagens para Fatiar e Imprimir ---
SLICE_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'slice_button.png') 
PRINT_SEND_BUTTON_IMAGE = os.path.join(IMAGES_AND_STL_FOLDER, 'print_send_button.png') 

# --- Função Auxiliar para Encontrar e Clicar ---
def find_and_click(image_path, timeout=30, confidence=0.9):
    location = None
    timeout_start = time.time()
    print(f"Procurando '{os.path.basename(image_path)}' na tela...") 
    
    while location is None and (time.time() - timeout_start) < timeout:
        try:
            location = pyautogui.locateOnScreen(image_path, confidence=confidence, grayscale=False)
        except Exception as e:
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

    # --- LOOP PARA CARREGAR MÚLTIPLOS ARQUIVOS STL ---
    for stl_file in STL_FILES_TO_IMPORT:
        print(f"\nCarregando arquivo STL: {os.path.basename(stl_file)}")
        if find_and_click(ARQUIVO_BUTTON_IMAGE): 
            time.sleep(1.5) 
            
            if find_and_click(IMPORTAR_MENU_ITEM_FIRST_IMAGE): 
                time.sleep(1.5) 
                
                if find_and_click(IMPORTAR_STL_SPECIFIC_ITEM_IMAGE): 
                    time.sleep(2.5) 
                    
                    print(f"Digitando o caminho completo do arquivo STL: {stl_file}") 
                    pyautogui.typewrite(stl_file) 
                    pyautogui.press('enter') 
                    time.sleep(15) 
                    print(f"Arquivo '{os.path.basename(stl_file)}' carregado (esperamos!).") 
                else:
                    print(f"Falha ao encontrar o item 'Importar 3MF/STL/...' ('{os.path.basename(IMPORTAR_STL_SPECIFIC_ITEM_IMAGE)}').") 
                    break 
            else:
                print(f"Falha ao encontrar o item de menu 'Importar' ('{os.path.basename(IMPORTAR_MENU_ITEM_FIRST_IMAGE)}').") 
                break
        else:
            print(f"Falha ao encontrar o botão/menu 'Arquivo' ('{os.path.basename(ARQUIVO_BUTTON_IMAGE)}').") 
            break
    
    # --- Continuação após o carregamento de TODOS os STLs ---
    print("\nTodos os arquivos STL carregados (esperamos!).")

    # --- Clicar no botão "Arranjar" / "Organizar" Objetos na Mesa (Primeira vez, após carregar STLs) ---
    if find_and_click(ARRANGE_BUTTON_IMAGE):
        time.sleep(5) 
        print("Objetos arranjados na mesa (primeira vez, após carregar STLs!).")
    else:
        print(f"Falha ao encontrar o botão de Arranjar Objetos (primeira vez) ('{os.path.basename(ARRANGE_BUTTON_IMAGE)}').")

    # --- INÍCIO DA SEÇÃO: IMPORTAR/SELECIONAR CONFIGURAÇÕES ---
    print("\nIniciando a importação/seleção de configurações...")
    
    if find_and_click(ARQUIVO_BUTTON_IMAGE): 
        time.sleep(1.5)
        if find_and_click(IMPORTAR_MENU_ITEM_FIRST_IMAGE): 
            time.sleep(1.5)
            if find_and_click(IMPORTAR_MENU_ITEM_SECOND_IMAGE): 
                time.sleep(1.5)
                if find_and_click(IMPORT_CONFIG_BUTTON_IMAGE): 
                    time.sleep(2.5) 
                    
                    print(f"Digitando o caminho completo do arquivo de preset: {PRESET_FILE_PATH}")
                    pyautogui.typewrite(PRESET_FILE_PATH) 
                    pyautogui.press('enter') 
                    
                    # --- AQUI: A lógica para o botão "Sobreviver" foi removida ---
                    # Se o diálogo "Importar exceção" ainda aparecer, o script não o tratará.
                    
                    time.sleep(5) 
                    print("Configurações importadas/selecionadas (esperamos!).")
                else:
                    print(f"Falha ao encontrar o botão de Importar Configurações ('{os.path.basename(IMPORT_CONFIG_BUTTON_IMAGE)}').")
            else:
                print(f"Falha ao encontrar o segundo item de menu 'Importar' ('{os.path.basename(IMPORTAR_MENU_ITEM_SECOND_IMAGE)}').")
        else:
            print(f"Falha ao encontrar o primeiro item de menu 'Importar' novamente ('{os.path.basename(IMPORTAR_MENU_ITEM_FIRST_IMAGE)}').")
    else:
        print(f"Falha ao encontrar o botão/menu 'Arquivo' novamente ('{os.path.basename(ARQUIVO_BUTTON_IMAGE)}').")
    # --- FIM DA SEÇÃO DE CONFIGURAÇÕES ---

    # --- Clicar no botão "Arranjar" / "Organizar" Objetos na Mesa (Segunda vez, após importar config) ---
    if find_and_click(ARRANGE_BUTTON_IMAGE):
        time.sleep(5) 
        print("Objetos reorganizados na mesa (segunda vez, após importar configurações!).")
    else:
        print(f"Falha ao encontrar o botão de Arranjar Objetos (segunda vez) ('{os.path.basename(ARRANGE_BUTTON_IMAGE)}').")

    # --- Clicar no botão "Fatiar" (Slice) MÚLTIPLAS VEZES ---
    num_clicks_slice = 2 
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
        time.sleep(15) 
        print("Fatiamento concluído (esperamos!).") 
        
        # --- Clicar no botão "Imprimir" ou "Enviar para Impressora" ---
        if find_and_click(PRINT_SEND_BUTTON_IMAGE): 
            time.sleep(5) 
            print("Comando de impressão enviado para a K1 Max!")
            print("\n--- Automação do fluxo completo (STL -> Fatiar -> Imprimir) finalizada ---")
        else:
            print(f"Falha ao encontrar o botão de Imprimir/Enviar ('{os.path.basename(PRINT_SEND_BUTTON_IMAGE)}').")
    else:
        print(f"Falha persistente ao encontrar e clicar no botão de Fatiar ('{os.path.basename(SLICE_BUTTON_IMAGE)}').") 

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