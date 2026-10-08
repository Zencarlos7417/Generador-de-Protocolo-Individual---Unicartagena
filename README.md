# Generador de Protocolo Individual -- Unicartagena

Es un pequeño proyecto que genera el texto de un protocolo individual a partir de los módulos y lecturas de la universidad, usando inteligencia artificial para resumir y estructurar la información.

## Descripción general

Automatiza el análisis de un PDF académico y el llenado de un protocolo individual en Word, conservando el diseño institucional exacto (logos, encabezado, tabla y estilos).

## Stack

- **Flask** – app web mínima
- **pdfplumber** – extracción de texto del PDF
- **google-genai (Gemini API, modelo `gemini-2.5-flash`)** – análisis y redacción de las 9 secciones, devuelve JSON estricto
- **docxtpl** – inyecta el JSON en la plantilla Word sin tocar el diseño

## 1. Instalación

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copia `.env.example` a `.env` y pega tu clave real de la API de Gemini:

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=tu-clave-real
```

## 2. Preparar la plantilla Word

1. Abre tu documento institucional ya diseñado con logos, encabezado y la tabla de 9 secciones.
2. En cada celda de contenido, escribe el tag correspondiente de una sola vez:

   | Sección | Tag |
   |---|---|
   | Descripción | `{{ descripcion }}` |
   | Palabras clave | `{{ palabras_clave }}` |
   | Objetivos | `{{r objetivos }}` |
   | Conceptos clave y definiciones | `{{r conceptos_clave }}` |
   | Resumen | `{{ resumen }}` |
   | Metodología de trabajo | `{{ metodologia }}` |
   | Conclusiones | `{{ conclusiones }}` |
   | Discusiones y recomendaciones | `{{ discusiones }}` |
   | Bibliografía (APA) | `{{r bibliografia }}` |

3. Guarda el archivo como `plantilla_protocolo.docx` y colócalo en la raíz del proyecto.

## 3. Ejecutar la aplicación

```bash
python app.py
```

Abre `http://localhost:5000`, sube el PDF y el navegador descargará automáticamente el documento final en Word.

## 4. Estructura del proyecto

```text
protocolo-app/
├── app.py                    # Rutas Flask y orquestación del flujo
├── pdf_reader.py            # Extracción de texto del PDF
├── ai_processor.py          # Prompt del sistema + llamada a Gemini + validación JSON
├── docx_filler.py          # Inyección de datos en la plantilla (docxtpl)
├── templates/index.html    # Formulario de subida
├── plantilla_protocolo.docx # Plantilla institucional
├── plantilla_protocolo_colaborativo.docx
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 5. Notas y mejoras

- **Costo/velocidad**: `gemini-2.5-flash` es el balance recomendado.
- **PDFs escaneados**: si el PDF es una imagen, `pdfplumber` no extraerá texto.
- **Múltiples plantillas**: puedes usar una plantilla colaborativa o individual según el tipo.
- **Producción**: `debug=True` debe desactivarse antes del despliegue.

