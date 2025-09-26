import sys
import time
import json
import base64
import random

def fake_image(text: str) -> str:
    """Genera un string base64 simulado a partir de texto."""
    return base64.b64encode(text.encode()).decode()

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "DNI requerido"}))
        sys.exit(1)

    dni = sys.argv[1]

    stages = []

    # Etapa 1: Validación de DNI
    time.sleep(random.uniform(1, 2))
    stages.append({
        "info": f"DNI {dni} validado correctamente",
        "image": fake_image(f"validacion_{dni}")
    })

    # Etapa 2: Consulta de deudas activas
    time.sleep(random.uniform(2, 4))
    stages.append({
        "info": f"Encontradas {random.randint(0, 3)} deudas registradas",
        "image": fake_image(f"deudas_{dni}")
    })

    # Etapa 3: Detalle de la deuda (si hay)
    time.sleep(random.uniform(2, 4))
    stages.append({
        "info": "Detalle de deudas: Banco X, Tarjeta Y, Préstamo Z",
        "image": fake_image(f"detalle_{dni}")
    })

    # Etapa 4: Resumen final
    time.sleep(random.uniform(1, 2))
    stages.append({
        "info": "Scraping finalizado correctamente",
        "image": fake_image(f"final_{dni}")
    })

    result = {"dni": dni, "stages": stages}
    print(json.dumps(result))

if __name__ == "__main__":
    main()
