# Ollama Prompt Studio

Aplicación moderna de escritorio para Windows para trabajar con Ollama y modelos MiniMax/Qwen.

## Funcionalidades

- Pestaña "MiniMax H3":
  - Entrada de texto libre.
  - Carga de varias imágenes mediante explorador o arrastrando archivos a la zona de carga.
  - Eliminación individual o global de imágenes cargadas.
  - Elección del modelo `agent-minimax` o `agent-minimax-lite`.
  - Generación de un prompt optimizado para MiniMax H3.
  - Vista previa visual de las imágenes cargadas.
  - Botón para copiar todo el texto generado.

- Pestaña "Descripción visual":
  - Selección del modelo `Pro` (`orcarouter/Qwen3.8-27B-Uncensored:latest`) o `Lite` (`lukey03/qwen3.5-9b-abliterated-vision:latest`).
  - Carga de una sola imagen.
  - Opciones de precisión: Básica, Equilibrada, Detallada o Muy detallada.
  - Caja de texto para un prompt personalizado.
  - Resultado de la descripción según la precisión elegida.

## Tecnologías

- PySide6 para una interfaz moderna y nativa de Windows.
- Requests para la conexión con la API de Ollama.
- Pillow para previsualización de imágenes.

## Requisitos

- Windows 10/11.
- Python 3.10 o superior.
- Ollama ejecutándose localmente en `http://localhost:11434`.
- Modelos descargados en Ollama:
  - `agent-minimax`
  - `agent-minimax-lite`
  - `orcarouter/Qwen3.8-27B-Uncensored:latest`
  - `lukey03/qwen3.5-9b-abliterated-vision:latest`

## Instalación

1. Abre una terminal en la carpeta del proyecto.
2. Ejecuta:

   ```powershell
   py -m pip install -r requirements.txt
   ```

3. Inicia Ollama con los modelos necesarios.
4. Lanza la aplicación:

   ```powershell
   py main.py
   ```

   O bien:

   ```powershell
   .\run_app.bat
   ```

## Ejecutable Windows

También puedes generar el archivo `.exe` con icono personalizado con este comando:

```powershell
.\build_exe.bat
```

El ejecutable final queda en la carpeta `dist` con el nombre `MiniMaxPromptStudio.exe`.

## Nota

La interfaz se conecta directamente a Ollama usando la API local. Si el servidor no está disponible, la app mostrará un aviso en la barra de estado.
