---
title: Clara - Seguros Colsubsidio
emoji: 🛡️
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Agente conversacional de venta de seguros (Reto 2 - 30X)
---

# Clara — Venta automatizada de seguros 🛡️

**Reto 2 · Venta automatizada de seguros** — [Hackathon Colsubsidio × 30X](https://innovacion.colsubsidio.com/)
· 22–26 de julio de 2026 · Club La Colina, Bogotá.

Repositorio: [github.com/Mariana-Codebase/Venta-automatizada-de-seguros---Clara](https://github.com/Mariana-Codebase/Venta-automatizada-de-seguros---Clara)

> **El reto:** hoy adquirir un seguro en Colsubsidio depende de un asesor que
> identifique la necesidad, cotice, explique y cierre. Ese modelo no escala, no
> opera 24/7 y depende del equipo comercial. **Clara lleva al afiliado desde
> _"no sé qué seguro necesito"_ hasta _"ya quedé asegurado"_ sin un solo humano
> en el medio.**

---

## Qué es Clara

Clara es una **asesora digital de seguros** que conversa en lenguaje natural, en
español colombiano. En una sola conversación:

1. **Perfila desde la base real de afiliados**: un motor de propensión 100%
   explicable puntúa los productos con las variables reales del afiliado
   (segmento familiar, edad, categoría, pirámide y marcas de consumo) y define
   **por qué**, **cuándo** y **por qué canal** ofrecerle protección.
2. **Diagnostica** la vida del afiliado con preguntas abiertas (con quién vive, si
   tiene carro, moto, mascota, viajes, dependientes…) — o **confirma** lo que la
   base ya sugiere, sin interrogar de cero.
3. **Recomienda** el mejor producto de **todo el portafolio Colsubsidio** (14
   productos), explicando por qué encaja, qué cubre y **qué NO cubre**.
4. **Contrata**: reúne los datos, genera el **contrato en PDF**, captura la
   **firma electrónica** y entrega un **enlace de pago** (checkout tipo Wompi).
5. **Emite** la **póliza en PDF** en el instante en que el pago se aprueba y hace
   post-venta (número de póliza, cómo usarla, encuesta de satisfacción).
6. **Transmite al asesor**: como Colsubsidio **distribuye** seguros (no los
   emite), cada vinculación queda **empaquetada** — perfil, propensión explicada,
   contrato firmado, pago y póliza — en la **bandeja del asesor** (`/asesor`),
   lista para gestionarse con la aseguradora.

Todo el recorrido queda en un **registro de auditoría** persistente. La demo web
muestra, en vivo y al lado del chat, **cada decisión, herramienta y escritura en
base de datos** que ocurre detrás — para que un juez vea que no hay magia: hay
arquitectura.

---

## Por qué Clara gana: una arquitectura en la que se puede confiar

Vender seguros con un LLM tiene un riesgo mortal: **que el modelo alucine una
cobertura, un precio o una condición**. En seguros eso no es un bug, es una
**responsabilidad legal y financiera**. Clara está diseñada, de raíz, para que
eso **no pueda pasar**:

| Principio | Cómo lo garantiza Clara |
|-----------|-------------------------|
| **El LLM solo conversa** | Gemini nunca calcula ni inventa. Solo dialoga y **llama herramientas** (function-calling). Toda la lógica dura vive en el backend. |
| **Coberturas ⇒ base de conocimiento (RAG)** | Cada afirmación de amparo/exclusión/condición sale de `consultar_coberturas`, **con cita de la fuente** (cláusula de las condiciones). |
| **Precios ⇒ motor de reglas determinístico** | Ninguna cifra la produce el modelo: salen de un motor auditable (`cotizar`) con factores por edad y dependientes. |
| **Emisión ⇒ backend, no el modelo** | Contrato, firma, pago y póliza los ejecuta el código de forma determinística; el modelo solo confirma en lenguaje natural. |
| **Guardrail de salida** | Una capa basada en reglas revisa cada respuesta: si menciona cobertura o precio sin respaldo en el turno, lo marca en la auditoría. |
| **Cumplimiento por diseño** | Aviso de tratamiento de datos (**Ley 1581 de 2012**) desde el saludo; el prompt rechaza temas fuera de alcance y resiste intentos de jailbreak. |
| **Trazabilidad total** | Cada perfil, cotización, contrato, pago y póliza se registra en SQLite y se muestra en vivo en la interfaz. |

> En una frase: **el modelo pone las palabras, el sistema pone la verdad.**

---

## Propensión explicable desde la base real de afiliados

El insumo del reto es la base real de afiliados Colsubsidio
(`Usos_Productos_Afiliados_SIN_ID.xlsx`, **500.000 registros** identificados por
**SERIE** — sin nombres ni cédulas). La pregunta del jurado — *¿por qué a esta
persona le mostraste este seguro y no otro?* — se responde con una **tabla de
reglas auditable** ([`app/propension.py`](app/propension.py)), nada de caja negra:

| Variable de la base | Ejemplo de regla | Producto | Por qué |
|---|---|---|---|
| Segmento familiar | Familia monoparental | Vida (+30) | Hijos que dependen de un solo ingreso |
| Segmento familiar | Sin grupo familiar | Accidentes (+18) | Su mayor riesgo es su propia incapacidad |
| Marca VIVIENDA | Usó el servicio de vivienda | Hogar (+40) | Estrena patrimonio que proteger |
| Marca AGENCIAS/HOTELES | Compra viajes u hoteles | Viajes (+35/30) | Ya viaja: protege lo que ya hace |
| Marca DROGUERÍA | Gasto recurrente en droguería | Salud (+15) | Necesidad de salud activa (17.6% de la base) |
| Rango salarial | Más de 4 SMLV | Vida y Ahorro (+10) | Capacidad real de proteger y ahorrar |
| Rango de edad | Mayor de 55 años | Exequial (+20) | Anticipar evita cargas a la familia |
| Pirámide | Independiente | Accidentes (+10) | Sin ARL de empleador |

- **34 reglas** en total; el puntaje de un producto es la **suma de las reglas
  que aplican** y cada recomendación viaja con su desglose (variable → puntos →
  razón). Se consultan en vivo en `GET /api/propension/reglas`. El comportamiento
  observado (marcas de consumo) **pesa más** que la demografía: una marca activa
  es evidencia directa de la necesidad, no una inferencia.
- **Etiquetas anonimizadas, correspondencia documentada.** Colsubsidio entregó
  las clasificaciones internas (categoría, segmentos, pirámide) anonimizadas con
  letras griegas (SIGMA, LAMBDA, RHO…). Su interpretación vive en
  [`data/mapa_segmentos.json`](data/mapa_segmentos.json): correspondencia por
  coincidencia de participaciones con la distribución pública del insumo del
  reto, **validada con evidencia interna** — SIGMA→categoría A: el 99.2% gana
  ≤2 SMLV; KAPPA→pensionado: el 95.5% es mayor de 55; ETA→joven: el 83.2% tiene
  20-35 años. Es un archivo editable: ante el diccionario oficial, se corrige
  ahí y el motor no cambia.
- **La oferta cambia por perfil**: en la demo, el selector *"Perfil de la base
  de afiliados"* permite comparar — la monoparental ve Vida, el joven solo ve
  Accidentes, quien compra viajes ve Asistencia en Viajes, quien usó Vivienda ve
  Hogar, el pensionado ve Exequial/Salud.
- **Momento y canal**: el motor también sugiere *cuándo* y *por dónde* contactar
  (tras la compra en droguería, al confirmar la reserva, al desembolso de
  vivienda, con la mesada pensional…), visible en el panel de propensión.
- **Lo que la persona dice prevalece**: la propensión es el punto de partida;
  la conversación (prioridad expresada, producto pedido) siempre le gana a la base.
- **Privacidad**: la base completa **no se versiona**; la demo usa una muestra
  ([`data/afiliados_demo.json`](data/afiliados_demo.json)) con solo SERIE +
  variables. Para regenerar mapa, estadísticas y muestra desde la base:
  `python scripts/perfilar_base.py <ruta al .xlsx o .csv>`.

## Panel del asesor (`/asesor`)

Colsubsidio **no fabrica pólizas: las distribuye**. Por eso la venta autónoma
termina en una **bandeja de vinculaciones**: al firmarse el contrato, Clara
transmite la solicitud empaquetada (perfil de la base, propensión con razones,
datos del tomador, contrato PDF, estado del pago y póliza interna) y el asesor
la avanza por estados: `pendiente_pago → pagada → enviada a aseguradora →
emitida → cerrada`. Los escalamientos a humano también llegan aquí como tickets.

---

## El recorrido del afiliado

```
  Afiliado                Clara (Gemini)              Backend determinístico
     │                         │                              │
     │  "no sé qué necesito"   │                              │
     ├────────────────────────▶│  diagnóstico (preguntas      │
     │                         │  abiertas, escucha activa)   │
     │                         ├─ registrar_perfil ──────────▶│ SQLite (perfil)
     │                         │                              │
     │                         ├─ recomendar ────────────────▶│ RAG + motor de reglas
     │◀── opciones con precio  │◀─ coberturas + precio real ──┤
     │    y exclusiones reales │                              │
     │                         ├─ consultar_coberturas ──────▶│ RAG (cita fuente)
     │  "quiero ese"           │                              │
     │                         ├─ registrar_datos ───────────▶│ SQLite (contratante)
     │                         ├─ generar_contrato ──────────▶│ PDF contrato
     │  [ firma con botón ] ───┼─────────────────────────────▶│ firma + enlace de pago
     │  [ paga en checkout ] ──┼─────────────────────────────▶│ webhook aprobado
     │◀── "ya quedaste         │◀─ emisión determinística ────┤ PDF póliza + auditoría
     │     asegurado 🎉"       │                              │
```

Estados de la sesión: `DIAGNOSTICO → RECOMENDACION → DUDAS → CIERRE → EMITIDA`.
La conversación soporta un **atajo**: si el afiliado ya sabe lo que quiere
("solo quiero seguro de viaje"), Clara no lo interroga — va directo al producto.

---

## Portafolio cubierto (14 productos reales de Colsubsidio)

Vida · Vida y Ahorro · Plan Complementario de Salud · Asistencias Médicas
Familiares · Accidentes Personales · Exequial · Accidentes + Exequial · Asesorías
Jurídicas · Asistencias Múltiples (hogar, vehículo, salud y mascotas 24/7) ·
Asistencia Médica en Viajes · Hogar · Autos · Moto · Mascotas.

Cada uno con sus amparos, exclusiones, condiciones, fuente citable y prima base
en `app/knowledge.py`. El recomendador **rankea por ajuste al perfil, no por
precio**, y no se limita a vida o mascotas: considera todo el portafolio.

---

## Probar la demo en 2 minutos

```powershell
python -m pip install -r requirements.txt
copy .env.example .env        # y pega tu GEMINI_API_KEY (gratis, sin tarjeta)
python server.py
```

→ Abre **http://localhost:8000** y entra a la pestaña **Demo interactiva**.

Guion sugerido para el jurado:
1. En la demo, elige un **perfil de la base de afiliados** (p. ej. la cabeza de
   familia monoparental) → Clara saluda ya personalizada y el panel *Propensión*
   muestra por qué le ofrece eso. Cambia de perfil y compara: **la oferta cambia**.
2. O empieza como visitante: *"Hola, no sé qué seguro necesito."* → deja que
   Clara diagnostique. Cuéntale algo real: *"vivo con mi pareja y tengo un gato"*
   → mira cómo aparece el seguro de mascotas en la recomendación.
3. Elige un producto, da tus datos, **firma** con el botón y **paga** con la
   tarjeta de prueba `4242 4242 4242 4242` (la `4111…` simula rechazo).
4. Observa cómo se **emite la póliza en PDF** y todo queda en el panel de auditoría.
5. Abre el **Panel del asesor** (`/asesor`): la vinculación llegó empaquetada
   con la propensión explicada, lista para gestionarse con la aseguradora.

> **Clave Gemini:** usa una de **Google AI Studio** (`AIza...`,
> [aistudio.google.com/apikey](https://aistudio.google.com/apikey)), gratis y sin
> tarjeta. Evita claves Vertex (`AQ.`) salvo que tengas facturación en Google Cloud.

---

## Estado de ejecución (honestidad de ingeniería)

Esto es un **MVP demostrable** para la hackathon, no un producto en producción.
El flujo principal se recorre completo en local; algunas piezas son
**simulaciones** conscientes que se dejan listas para evolucionar.

| Área | Estado | Notas |
|------|--------|-------|
| **Conversación con Gemini** | ✅ Funcional | Function-calling, escucha activa, manejo de peticiones directas. |
| **Motor de propensión** | ✅ Funcional | 32 reglas explicables sobre variables reales de la base; oferta y saludo cambian por perfil. |
| **Panel del asesor** | ✅ Funcional | Bandeja de vinculaciones con paquete completo y flujo de estados hacia la aseguradora. |
| **Flujo end-to-end** | ✅ Funcional | Diagnóstico → recomendación → contrato → firma → pago → emisión, cableado y recorrible. |
| **Frontend (chat + paneles)** | ✅ Funcional | Chat, estado, perfil y auditoría en vivo. |
| **PDFs (resumen/contrato/póliza)** | ✅ Funcional | Generación real con `fpdf2`, descarga por `/docs/{archivo}`. |
| **Persistencia** | ✅ Funcional | Sesiones y auditoría en SQLite; sobrevive reinicios. |
| **Pago (Wompi)** | 🟡 Simulación | Checkout con tarjetas de prueba y validación Luhn. **No** es la API real de Wompi (webhooks firmados, producción). |
| **Correo / WhatsApp** | 🟡 Simulación | Sin `SMTP_*`/Twilio, la entrega se registra como `[SIMULADO]`. Con credenciales, envía de verdad. |
| **Despliegue** | 🟡 Preparado | Dockerfile + variables de entorno listos; falta hardening cloud. |

---

## Roadmap corto

- **Agente:** pulir tono, consistencia de fases y edge cases de peticiones directas.
- **Pago:** integración real con Wompi (referencias, estados, reintentos, webhook firmado).
- **Entrega:** envío real de PDF por SMTP y WhatsApp (Twilio) con pruebas end-to-end.
- **RAG / catálogo:** enriquecer condiciones desde fuentes oficiales (`data/reference/`).
- **Calidad:** tests automatizados + CI, y observabilidad (métricas de sesión, errores LLM, latencias).

---

## Arquitectura y estructura

```
├── server.py              # Punto de entrada (python server.py)
├── app/                   # Backend (paquete Python)
│   ├── main.py            #   API FastAPI + checkout de pago + panel del asesor
│   ├── config.py          #   Configuración central (.env)
│   ├── agent.py           #   Sesión, herramientas y bucle de tool-calling + guardrail
│   ├── propension.py      #   Motor de propensión: 32 reglas explicables sobre la base de afiliados
│   ├── llm.py             #   Cliente Gemini (AI Studio + Vertex Express)
│   ├── extraction.py      #   Captura de datos: regex + responseSchema (Gemini)
│   ├── knowledge.py       #   Catálogo, RAG y motor de cotización (fuente de verdad)
│   ├── payments.py        #   Pasarela simulada (tarjetas de prueba, Luhn)
│   ├── pdfgen.py          #   PDFs de resumen, contrato y póliza (fpdf2)
│   ├── notify.py          #   Entrega por correo SMTP / WhatsApp Twilio (opcional)
│   └── store.py           #   SQLite (sesiones + auditoría + bandeja del asesor)
├── scripts/
│   └── perfilar_base.py   # Procesa el CSV de ~1.5M afiliados → stats + muestra demo anonimizada
├── static/                # Frontend (chat + paneles de estado/perfil/propensión/auditoría)
│   ├── index.html · asesor.html · css/styles.css · js/app.js · img/
├── data/                  # Muestra demo anonimizada + documentos de referencia del reto
├── var/                   # Runtime: PDFs y DB (ignorado en git)
├── Dockerfile · requirements.txt
```

**Stack:** Python · FastAPI · Gemini (function-calling) · fpdf2 · SQLite · Docker.

---

## Desplegar (Docker / Hugging Face Space)

```powershell
docker build -t clara .
docker run -p 7860:7860 -e GEMINI_API_KEY=AIza... clara
```

En un **Space** (SDK Docker): define `GEMINI_API_KEY` como *secret*. **Nunca**
subas el `.env` real al repo ni al hosting.

### Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `GEMINI_API_KEY` | — | **Obligatoria.** Preferir clave AI Studio (`AIza...`). |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Modelo Gemini. |
| `APP_ENV` | `development` | `production` desactiva docs OpenAPI y autoreload. |
| `PORT` | `8000` / `7860` (Docker) | Puerto HTTP. |
| `PUBLIC_BASE_URL` | auto | Base para enlaces de pago y PDFs (en Spaces se autodetecta). |
| `SMTP_*` | — | Correo real con PDF adjunto (opcional). |
| `TWILIO_*` | — | WhatsApp/SMS (opcional). |

---

## Autora

**Mariana Sinisterra** · [@MarianaCodebase](https://github.com/MarianaCodebase)

Prototipo para el **Reto 2 · Venta automatizada de seguros** —
Hackathon [Colsubsidio × 30X](https://innovacion.colsubsidio.com/).
</content>
