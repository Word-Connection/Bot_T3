# scripts/deudas-test.py
import sys
import json
import base64
import time
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

def generate_fake_image(text: str, width: int = 800, height: int = 600) -> str:
    """Genera una imagen simulada con texto."""
    img = Image.new('RGB', (width, height), color=(240, 240, 245))
    draw = ImageDraw.Draw(img)
    
    # Dibujar borde
    draw.rectangle([(10, 10), (width-10, height-10)], outline=(100, 100, 200), width=3)
    
    # Agregar texto
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        font = ImageFont.load_default()
    
    # Centrar texto
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    draw.text((x, y), text, fill=(50, 50, 100), font=font)
    
    # Convertir a base64
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    return base64.b64encode(buffer.getvalue()).decode()

def main():
    print("INFO: Iniciando deudas-test.py (MODO SIMULACIÓN)", file=sys.stderr)
    
    try:
        if len(sys.argv) < 2:
            result = {"error": "DNI requerido"}
            print(json.dumps(result))
            sys.exit(1)

        dni = sys.argv[1]
        print(f"INFO: Procesando DNI {dni} (simulado)", file=sys.stderr)

        stages = []
        
        # Simular diferentes etapas con delays
        etapas = [
            ("Conectando a sistema AFIP", 2),
            ("Autenticando credenciales", 1.5),
            ("Consultando deudas tributarias", 3),
            ("Obteniendo historial de pagos", 2),
            ("Generando reporte final", 1.5)
        ]
        
        for i, (descripcion, delay) in enumerate(etapas, 1):
            print(f"INFO: Etapa {i}/{len(etapas)}: {descripcion}", file=sys.stderr)
            time.sleep(delay)
            
            # Generar imagen para esta etapa
            img_text = f"Etapa {i}\n{descripcion}\nDNI: {dni}"
            img_base64 = generate_fake_image(img_text)
            
            stages.append({
                "info": descripcion,
                "image": img_base64,
                "timestamp": int(time.time()),
                "progress": int((i / len(etapas)) * 100)
            })

        # Score simulado
        score = random.randint(500, 900)
        
        # Imagen final con score
        final_img_text = f"SCORE FINAL\n{score}\nDNI: {dni}"
        final_img = generate_fake_image(final_img_text, 1000, 700)
        
        stages.append({
            "info": f"Score obtenido: {score}",
            "image": final_img,
            "timestamp": int(time.time()),
            "progress": 100
        })

        result = {
            "dni": dni,
            "score": str(score),
            "stages": stages,
            "success": True,
            "test_mode": True
        }
        
        print(json.dumps(result))
        sys.stdout.flush()
        
        print("INFO: Simulación completada", file=sys.stderr)

    except Exception as e:
        result = {"error": f"Excepción: {str(e)}", "dni": dni, "stages": []}
        print(json.dumps(result))
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()