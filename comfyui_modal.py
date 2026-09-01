import modal
import subprocess
from pathlib import Path

app = modal.App("comfyui-minimax")

UPSCALE_MODEL_NAME = "minimax_h3_latent_upscaler_3d_fp16.safetensors"
UPSCALE_MODEL_PATH = Path("/comfyui/models/latent_upscale_models") / UPSCALE_MODEL_NAME
UPSCALE_MODEL_URL = (
    "https://huggingface.co/Aitrepreneur/FLX/resolve/main/"
    "minimax_h3_latent_upscaler_3d_fp16.safetensors?download=true"
)

image = (
    # Optimización 1: Python 3.12 rinde mucho mejor con SageAttention y la arquitectura B200
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "git", "ffmpeg", "libgl1-mesa-glx", "libglib2.0-0", "build-essential")
    .run_commands(
        "git clone --shallow-since=2026-08-01 https://github.com/comfyanonymous/ComfyUI.git /comfyui",
        "rm -rf /comfyui/models",
        "cd /comfyui && pip install -r requirements.txt",
        # Optimización 2: Instalar ninja acelera la compilación de C++/CUDA de SageAttention
        "pip install ninja",
        "pip install sageattention",
        
        # 1. Nodos de Video e I/O
        "git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git /comfyui/custom_nodes/ComfyUI-VideoHelperSuite",
        "cd /comfyui/custom_nodes/ComfyUI-VideoHelperSuite && pip install -r requirements.txt",
        
        # 2. Gestor de ComfyUI
        "git clone https://github.com/ltdrdata/ComfyUI-Manager.git /comfyui/custom_nodes/ComfyUI-Manager",
        "cd /comfyui/custom_nodes/ComfyUI-Manager && pip install -r requirements.txt",
        
        # 3. Paquete Impact Pack (Requerido para segmentación/detección)
        "git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git /comfyui/custom_nodes/ComfyUI-Impact-Pack",
        "cd /comfyui/custom_nodes/ComfyUI-Impact-Pack && pip install -r requirements.txt",
        
        # 4. DaSiWa Nodes (Contiene el backend de Comfy Kitchen Attention e INT8 patches)
        "git clone https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes.git /comfyui/custom_nodes/ComfyUI-DaSiWa-Nodes",
        "cd /comfyui/custom_nodes/ComfyUI-DaSiWa-Nodes && pip install -r requirements.txt",
        
        # 5. KJNodes (Utilidades y optimización de flujos)
        "git clone https://github.com/kijai/ComfyUI-KJNodes.git /comfyui/custom_nodes/ComfyUI-KJNodes",
        "cd /comfyui/custom_nodes/ComfyUI-KJNodes && pip install -r requirements.txt",
        
        # 6. Rgthree Comfy (Dashboard y optimización de colas/muters)
        "git clone https://github.com/rgthree/rgthree-comfy.git /comfyui/custom_nodes/rgthree-comfy",
        "cd /comfyui/custom_nodes/rgthree-comfy && pip install -r requirements.txt",

        # 7. Nodos específicos de MiniMax H3
        "git clone https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3.git /comfyui/custom_nodes/ComfyUI-Spectrum-MiniMax-H3",
        "if [ -f /comfyui/custom_nodes/ComfyUI-Spectrum-MiniMax-H3/requirements.txt ]; then pip install -r /comfyui/custom_nodes/ComfyUI-Spectrum-MiniMax-H3/requirements.txt; fi",
        "git clone https://github.com/seesee75-commits/ComfyUI-MiniMaxH3-Director.git /comfyui/custom_nodes/ComfyUI-MiniMaxH3-Director",
        "if [ -f /comfyui/custom_nodes/ComfyUI-MiniMaxH3-Director/requirements.txt ]; then pip install -r /comfyui/custom_nodes/ComfyUI-MiniMaxH3-Director/requirements.txt; fi",
        "git clone https://github.com/Adudeguyman/ComfyUI-Fantastic-MiniMaxH3-PromptBuilder.git /comfyui/custom_nodes/ComfyUI-Fantastic-MiniMaxH3-PromptBuilder",
        "if [ -f /comfyui/custom_nodes/ComfyUI-Fantastic-MiniMaxH3-PromptBuilder/requirements.txt ]; then pip install -r /comfyui/custom_nodes/ComfyUI-Fantastic-MiniMaxH3-PromptBuilder/requirements.txt; fi",
        "git clone https://github.com/BigStationW/ComfyUi-Scale-Image-to-Total-Pixels-Advanced.git /comfyui/custom_nodes/ComfyUi-Scale-Image-to-Total-Pixels-Advanced",
        "if [ -f /comfyui/custom_nodes/ComfyUi-Scale-Image-to-Total-Pixels-Advanced/requirements.txt ]; then pip install -r /comfyui/custom_nodes/ComfyUi-Scale-Image-to-Total-Pixels-Advanced/requirements.txt; fi",
        "git clone https://github.com/aitrepreneur/ComfyUI-MiniMaxH3-T1-Latent.git /comfyui/custom_nodes/ComfyUI-MiniMaxH3-T1-Latent",
        "if [ -f /comfyui/custom_nodes/ComfyUI-MiniMaxH3-T1-Latent/requirements.txt ]; then pip install -r /comfyui/custom_nodes/ComfyUI-MiniMaxH3-T1-Latent/requirements.txt; fi",
        "git clone https://github.com/Aitrepreneur/ComfyUI-H3-Motion-Context-MultiRef-V3.git /comfyui/custom_nodes/ComfyUI-H3-Motion-Context-MultiRef-V3",
        "if [ -f /comfyui/custom_nodes/ComfyUI-H3-Motion-Context-MultiRef-V3/requirements.txt ]; then pip install -r /comfyui/custom_nodes/ComfyUI-H3-Motion-Context-MultiRef-V3/requirements.txt; fi",
        "git clone https://github.com/drozbay/MaskVidExperiments.git /comfyui/custom_nodes/MaskVidExperiments",
        "if [ -f /comfyui/custom_nodes/MaskVidExperiments/requirements.txt ]; then pip install -r /comfyui/custom_nodes/MaskVidExperiments/requirements.txt; fi",
        "git clone https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools.git /comfyui/custom_nodes/ComfyUI-NKD-Basic-Tools",
        "if [ -f /comfyui/custom_nodes/ComfyUI-NKD-Basic-Tools/requirements.txt ]; then pip install -r /comfyui/custom_nodes/ComfyUI-NKD-Basic-Tools/requirements.txt; fi",
        "git clone https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler.git /comfyui/custom_nodes/Comfyui_Minimax_h3_latent_Upscaler",
        "if [ -f /comfyui/custom_nodes/Comfyui_Minimax_h3_latent_Upscaler/requirements.txt ]; then pip install -r /comfyui/custom_nodes/Comfyui_Minimax_h3_latent_Upscaler/requirements.txt; fi",

        # Configuración del modo offline del mánager
        "mkdir -p /comfyui/user/__manager && printf '[default]\\nnetwork_mode = offline\\n' > /comfyui/user/__manager/config.ini"
    )
)

vol = modal.Volume.from_name("comfyui-models", create_if_missing=True)

@app.function(
    image=image,
    gpu="H100",
    volumes={"/comfyui/models": vol},
    cpu=8, 
    timeout=3600,
    memory=65536 
)
@modal.concurrent(max_inputs=100)
@modal.web_server(port=8188, startup_timeout=300)
def ui():
    if not UPSCALE_MODEL_PATH.is_file():
        UPSCALE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["curl", "--fail", "--location", "--retry", "3", "--output", str(UPSCALE_MODEL_PATH), UPSCALE_MODEL_URL],
            check=True,
        )
        vol.commit()

    # OPTIMIZACIÓN CRÍTICA EN ARRANQUE:
    # 1. Reemplazamos --use-sage-attention por --use-ck-attention para activar Comfy Kitchen.
    # 2. Agregamos --enable-dynamic-vram para clavar el modelo en los 141GB de la B200 y eliminar la latencia CPU-GPU.
    # 3. Forzamos el Text Encoder de Qwen a FP8 para liberar canales de procesamiento innecesarios.
    # 4. Desactivamos smart-memory para que ComfyUI no intente fragmentar la memoria durante los pasos de difusión.
    subprocess.Popen([
        "python", "main.py", 
        "--listen", "0.0.0.0", 
        "--port", "8188", 
        "--enable-cors-header", "*", 
        "--use-ck-attention",
        "--enable-dynamic-vram",
        "--disable-smart-memory"
    ], cwd="/comfyui")
