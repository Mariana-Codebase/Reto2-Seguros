# Clara — Venta automatizada de seguros

Solución al **Reto 2 · Seguros** · Hackathon [Colsubsidio × 30X](https://innovacion.colsubsidio.com/) · Bogotá, julio de 2026

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Gemini_2.0_Flash-4285F4?logo=google&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-trazabilidad_total-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-listo-2496ED?logo=docker&logoColor=white)

**Clara** es una asesora digital que lleva a cada afiliado desde *"no sé qué seguro
necesito"* hasta *"ya quedé asegurado"*, sin intervención humana: identifica la
propensión desde la base real de afiliados, personaliza la oferta, explica cada
recomendación, cierra la vinculación y — como Colsubsidio distribuye pólizas, no
las emite — entrega cada venta empaquetada a la bandeja del asesor para su gestión
con la aseguradora.

---

## Ejecución en 2 minutos

```bash
pip install -r requirements.txt
copy .env.example .env        # pegar GEMINI_API_KEY (aistudio.google.com/apikey)
python server.py              # → http://localhost:8000
```

## Recorrido de la demo

1. En **Demo interactiva**, el selector *"Perfil de la base de afiliados"* carga
   perfiles reales (identificados por SERIE). Clara saluda personalizada según el
   perfil y el panel **"Propensión · por qué esta oferta"** muestra las razones
   exactas de la recomendación. Al cambiar de perfil, **la oferta cambia**:
   monoparental → Vida · joven sin grupo familiar → Accidentes · compra viajes →
   Asistencia en Viajes · usó el servicio de vivienda → Hogar · pensionado → Exequial.
2. El flujo también funciona para un **visitante anónimo**: ante *"no sé qué seguro
   necesito"*, Clara diagnostica con preguntas abiertas y adapta la recomendación a
   lo que la persona cuenta (mascotas, vehículo, viajes, dependientes…).
3. Elegido un producto, Clara reúne los datos, genera el **contrato en PDF**, captura
   la **firma electrónica** y entrega el enlace de **pago** (sandbox: la tarjeta
   `4242 4242 4242 4242` aprueba; la `4111…` simula rechazo).
4. Con el pago aprobado, la **vinculación queda confirmada y radicada** y se genera
   su **resumen en PDF**. Colsubsidio distribuye —no emite pólizas—, así que la
   solicitud se transmite a la aseguradora, que expide la póliza. Cada decisión
   queda registrada en el panel de auditoría, en vivo junto al chat.
5. En el **Panel del asesor** (`/asesor`) la vinculación llega empaquetada — perfil,
   propensión explicada, contrato firmado y pago — y avanza por estados hasta la
   emisión oficial en la aseguradora. Cada avance notifica a la sesión del afiliado.

---

## Propensión explicable desde la base real de afiliados

El insumo es la base real de afiliados (`Usos_Productos_Afiliados_SIN_ID.xlsx`,
**500.000 registros** identificados por **SERIE** — sin nombres ni cédulas). La
pregunta central — *¿por qué a esta persona este seguro y no otro?* — se responde
con una **tabla de reglas auditable** ([`app/propension.py`](app/propension.py)),
sin cajas negras:

| Variable de la base | Ejemplo de regla | Producto | Fundamento |
|---|---|---|---|
| Segmento familiar | Familia monoparental | Vida (+30) | Hijos que dependen de un solo ingreso |
| Segmento familiar | Sin grupo familiar | Accidentes (+18) | Su mayor riesgo es su propia incapacidad |
| Marca VIVIENDA | Usó el servicio de vivienda | Hogar (+40) | Estrena patrimonio que proteger |
| Marca AGENCIAS / HOTELES | Compra viajes u hoteles | Viajes (+35/30) | Ya viaja: se protege lo que ya hace |
| Marca DROGUERÍA | Gasto recurrente en droguería | Salud (+15) | Necesidad de salud activa (17.6% de la base) |
| Rango salarial | Más de 4 SMLV | Vida y Ahorro (+10) | Capacidad real de proteger y ahorrar |
| Rango de edad | Mayor de 55 años | Exequial (+20) | Anticipar evita cargas a la familia |
| Pirámide | Independiente | Accidentes (+10) | Sin ARL de empleador |

- **34 reglas** en total. El puntaje de un producto es la **suma de las reglas que
  aplican**, y el desglose completo (variable → puntos → razón) acompaña cada
  recomendación en la interfaz, la auditoría y el panel del asesor. Las reglas se
  consultan en vivo en `GET /api/propension/reglas`.
- El **comportamiento observado pesa más que la demografía**: una marca de consumo
  activa es evidencia directa de la necesidad, no una inferencia.
- **Momento y canal**: el motor sugiere además *cuándo* y *por dónde* contactar
  (tras la compra en droguería, al confirmar una reserva, al desembolso de
  vivienda, con la mesada pensional…).
- **La conversación prevalece**: la propensión es el punto de partida; lo que la
  persona expresa en el diálogo siempre tiene prioridad sobre la base.

### Etiquetas anonimizadas, correspondencia documentada

Las clasificaciones internas de la base (categoría, segmentos, pirámide) llegan
anonimizadas con letras griegas (SIGMA, LAMBDA, RHO…). Su interpretación está
documentada en [`data/mapa_segmentos.json`](data/mapa_segmentos.json), construida
por coincidencia de participaciones con la distribución pública del insumo del
reto y **validada con evidencia interna de la propia base**:

| Etiqueta | Interpretación | Evidencia de validación |
|---|---|---|
| SIGMA | Categoría A | El **99.2%** gana ≤ 2 SMLV (definición legal de la categoría A) |
| KAPPA | Pensionado | El **95.5%** es mayor de 55 años |
| ETA (poblacional) | Segmento Joven | El **83.2%** tiene 20–35 años |
| EMP_000002 | Empresa foco | 18.3% de la base ≈ 16.8% de la referencia pública |

El mapa es un archivo **editable**: con el diccionario oficial de Colsubsidio se
corrige ahí, sin tocar el motor. Para regenerar mapa, estadísticas y muestra demo:
`python scripts/perfilar_base.py <ruta a la base .xlsx o .csv>`.

---

## Panel del asesor (`/asesor`)

Colsubsidio **no fabrica pólizas: las distribuye**. Por eso la venta autónoma
termina en una **bandeja de vinculaciones**: al firmarse el contrato, Clara
transmite la solicitud empaquetada — perfil de la base con segmentos
interpretados, propensión con razones, datos del tomador, contrato PDF, estado del
pago y resumen de vinculación — y el asesor la avanza por estados hasta que la
aseguradora emite la póliza:

```
pendiente_pago → pagada → enviada a aseguradora → emitida → cerrada
```

Cada avance **notifica a la sesión del afiliado**: si pregunta por su solicitud,
Clara responde con el estado real. Los escalamientos a humano también llegan a la
bandeja como tickets.

---

## Arquitectura: el modelo pone las palabras, el sistema pone la verdad

Vender seguros con un LLM tiene un riesgo crítico: que el modelo invente una
cobertura, un precio o una condición. Clara está diseñada para que no pueda pasar:

| Principio | Cómo se garantiza |
|---|---|
| **El LLM solo conversa** | Gemini nunca calcula ni inventa: dialoga y **llama herramientas** (function-calling). La lógica dura vive en el backend. |
| **Coberturas ⇒ base de conocimiento** | Cada afirmación sale de `consultar_coberturas`, **con cita de la fuente**. |
| **Precios ⇒ motor determinístico** | Ninguna cifra la produce el modelo: salen de `cotizar`, con factores auditables. |
| **Propensión ⇒ reglas explicables** | 34 reglas documentadas sobre variables reales; nada de puntajes opacos. |
| **Cierre ⇒ backend** | Contrato, firma, pago y radicación de la vinculación los ejecuta código determinístico; la póliza la emite la aseguradora, no Colsubsidio. |
| **Guardrail de salida** | Cada respuesta se verifica: cobertura o precio sin respaldo queda marcado en auditoría. |
| **Cumplimiento por diseño** | Aviso de tratamiento de datos (Ley 1581 de 2012) desde el saludo; alcance restringido; resistencia a manipulación del prompt. |
| **Trazabilidad total** | Perfil, cotización, contrato, pago y vinculación quedan en SQLite y a la vista en la interfaz. |

```
  Afiliado           Clara (Gemini)            Backend determinístico        Asesor
     │  "no sé qué       │                              │                      │
     │   necesito"       │                              │                      │
     ├──────────────────▶│ propensión (base 500k) +     │                      │
     │                   │ diagnóstico conversacional   │                      │
     │◀── oferta por     ├─ recomendar ────────────────▶│ reglas + coberturas  │
     │    perfil, con    │                              │                      │
     │    el porqué      ├─ generar_contrato ──────────▶│ PDF + firma          │
     │  [firma y pago] ──┼─────────────────────────────▶│ checkout + webhook   │
     │◀── "ya quedaste   │◀─ vinculación radicada ──────┤ resumen PDF          │
     │     asegurado"    │                              ├─ paquete completo ──▶│ bandeja
     │                   │                              │      la aseguradora emite la póliza ▲
     │◀── estado de su solicitud ◀──────────────────────┴── avances ───────────┤
```

---

## Estructura del proyecto

```
├── server.py              # Punto de entrada (python server.py)
├── app/
│   ├── main.py            # API FastAPI + checkout + panel del asesor
│   ├── agent.py           # Sesión, herramientas, bucle del agente y guardrail
│   ├── propension.py      # Motor de propensión: 34 reglas explicables
│   ├── knowledge.py       # Catálogo de 14 productos, coberturas y cotizador
│   ├── llm.py             # Cliente Gemini (AI Studio / Vertex) + respaldo automático
│   ├── extraction.py      # Captura de datos: regex + salida estructurada
│   ├── payments.py        # Pasarela simulada (tarjetas de prueba, Luhn)
│   ├── pdfgen.py          # PDFs de resumen, contrato y vinculación
│   ├── notify.py          # Correo / WhatsApp (opcional; sin credenciales, simula)
│   ├── store.py           # SQLite: sesiones, auditoría y bandeja del asesor
│   └── config.py          # Configuración central (.env)
├── scripts/
│   └── perfilar_base.py   # Procesa la base (.xlsx/.csv) → mapa + stats + demo
├── static/                # Frontend: chat, paneles y panel del asesor
├── data/                  # Mapa de segmentos, estadísticas y muestra demo (anonimizados)
└── Dockerfile · requirements.txt · .env.example
```

**Privacidad:** la base completa de afiliados **nunca se versiona** (protegida en
`.gitignore`). En `data/` solo hay agregados estadísticos, el mapa documentado y
una muestra identificada por SERIE.

---

## Configuración

| Variable | Por defecto | Descripción |
|---|---|---|
| `GEMINI_API_KEY` | — | **Obligatoria.** Clave de [AI Studio](https://aistudio.google.com/apikey) (`AIza…`) o Vertex Express (`AQ.…`). |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Modelo Gemini. |
| `ANTHROPIC_API_KEY` | — | Opcional. Con ella, Claude es primario y Gemini queda de respaldo automático. |
| `APP_ENV` | `development` | `production` desactiva docs y autoreload. |
| `PORT` | `8000` (local) / `7860` (Docker) | Puerto HTTP. |
| `PUBLIC_BASE_URL` | auto | Base para enlaces de pago y PDFs. |
| `SMTP_*` / `TWILIO_*` | — | Entrega real por correo / WhatsApp (opcional; sin ellas, se simula). |

**Docker:**

```bash
docker build -t clara .
docker run -p 7860:7860 -e GEMINI_API_KEY=AIza... clara
```

---

## Alcance del prototipo

El flujo principal se recorre completo de inicio a fin. Componentes y su estado:

| Área | Estado | Notas |
|---|---|---|
| Motor de propensión | ✅ Funcional | 34 reglas sobre la base real de 500k; oferta y saludo cambian por perfil. |
| Conversación (Gemini) | ✅ Funcional | Function-calling, escucha activa, atajos por petición directa. |
| Flujo end-to-end | ✅ Funcional | Diagnóstico → recomendación → contrato → firma → pago → emisión. |
| Panel del asesor | ✅ Funcional | Bandeja con paquete completo, estados y notificación al afiliado. |
| PDFs y persistencia | ✅ Funcional | Contrato y resumen de vinculación reales (fpdf2); SQLite sobrevive reinicios. |
| Pago (estilo Wompi) | 🟡 Sandbox | Checkout con tarjetas de prueba y validación Luhn. |
| Correo / WhatsApp | 🟡 Simulado | Con credenciales SMTP/Twilio envía de verdad. |

Fuera de alcance por diseño del reto: integración real con aseguradoras, firma con
validez legal, gestión de siniestros/renovaciones y pasarela de pago en producción.

---

## Autora

**Mariana Sinisterra** · [@MarianaCodebase](https://github.com/MarianaCodebase)

Hackathon Colsubsidio × 30X · Bogotá, 23 de julio de 2026.
Prototipo demostrativo. Datos tratados conforme a la Ley 1581 de 2012.
