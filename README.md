# Clara — Venta automatizada de seguros

**Reto 2 · Seguros** · Hackathon [Colsubsidio × 30X](https://innovacion.colsubsidio.com/) · 22–26 de julio de 2026 · Club La Colina, Bogotá
**Última actualización:** 23 de julio de 2026

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Gemini_2.0_Flash-4285F4?logo=google&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-auditoría_total-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-listo-2496ED?logo=docker&logoColor=white)

> **El reto:** hoy adquirir un seguro en Colsubsidio depende de un asesor comercial que
> detecte la necesidad, cotice, explique y cierre. Ese modelo no escala, no opera 24/7
> y genera experiencias inconsistentes. **Clara lleva al afiliado desde
> _"no sé qué seguro necesito"_ hasta _"ya quedé asegurado"_ sin hablar con nadie** —
> y como Colsubsidio distribuye pólizas (no las emite), cada venta cerrada llega
> empaquetada a la bandeja del asesor para su gestión con la aseguradora.

---

## Demo en 2 minutos

```bash
pip install -r requirements.txt
copy .env.example .env        # pega tu GEMINI_API_KEY (aistudio.google.com/apikey)
python server.py              # → http://localhost:8000
```

**Guion sugerido para el jurado:**

1. Entra a **Demo interactiva** y elige un **perfil de la base de afiliados** (p. ej.
   la cabeza de familia monoparental). Clara saluda ya personalizada y el panel
   **"Propensión · por qué esta oferta"** muestra las razones exactas. Cambia de
   perfil y compara: **la oferta cambia**.
2. O empieza como visitante anónimo: *"no sé qué seguro necesito"* → Clara diagnostica
   con preguntas abiertas. Cuéntale algo real (*"vivo con mi pareja y tengo un gato"*)
   y mira cómo la recomendación se adapta.
3. Elige un producto, entrega tus datos, **firma** el contrato con el botón y **paga**
   con la tarjeta de prueba `4242 4242 4242 4242` (la `4111…` simula rechazo).
4. La **póliza se emite en PDF** al instante y todo queda en el panel de auditoría.
5. Abre el **Panel del asesor** (`/asesor`): la vinculación llegó empaquetada — perfil,
   propensión explicada, contrato firmado y pago — lista para gestionarse con la
   aseguradora. Avanza su estado y verás que la sesión del afiliado queda notificada.

---

## Cómo responde Clara a la rúbrica del reto

| Criterio | Peso | Cómo lo resuelve Clara |
|---|---|---|
| **Lógica de propensión** | 25% | Motor de **34 reglas auditables** sobre la base real de 500.000 afiliados; cada recomendación viaja con su desglose variable → puntos → razón. Cero caja negra. |
| **Variación por perfil** | 20% | Selector con perfiles reales (por SERIE): monoparental→Vida, joven solo→Accidentes, quien compra viajes→Viajes, vivienda nueva→Hogar, pensionado→Exequial. |
| **Flujo completo funcional** | 20% | Diagnóstico → recomendación → contrato PDF → firma electrónica → pago → emisión → bandeja del asesor. Autogestionado de punta a punta. |
| **Experiencia y confianza** | 15% | Conversación cálida en español colombiano, exclusiones siempre visibles, aviso Ley 1581 de 2012, auditoría en vivo junto al chat. |
| **Innovación** | 20% | Propensión con **momento y canal** de contacto, mapa de segmentos anonimizados **validado con evidencia**, lazo asesor↔afiliado, guardrails en código. |

---

## Propensión explicable desde la base real de afiliados

El insumo es la base real (`Usos_Productos_Afiliados_SIN_ID.xlsx`, **500.000
registros** identificados por **SERIE** — sin nombres ni cédulas). La pregunta del
jurado — *¿por qué a esta persona le mostraste este seguro y no otro?* — se responde
con una **tabla de reglas auditable** ([`app/propension.py`](app/propension.py)):

| Variable de la base | Ejemplo de regla | Producto | Por qué |
|---|---|---|---|
| Segmento familiar | Familia monoparental | Vida (+30) | Hijos que dependen de un solo ingreso |
| Segmento familiar | Sin grupo familiar | Accidentes (+18) | Su mayor riesgo es su propia incapacidad |
| Marca VIVIENDA | Usó el servicio de vivienda | Hogar (+40) | Estrena patrimonio que proteger |
| Marca AGENCIAS / HOTELES | Compra viajes u hoteles | Viajes (+35/30) | Ya viaja: protege lo que ya hace |
| Marca DROGUERÍA | Gasto recurrente en droguería | Salud (+15) | Necesidad de salud activa (17.6% de la base) |
| Rango salarial | Más de 4 SMLV | Vida y Ahorro (+10) | Capacidad real de proteger y ahorrar |
| Rango de edad | Mayor de 55 años | Exequial (+20) | Anticipar evita cargas a la familia |
| Pirámide | Independiente | Accidentes (+10) | Sin ARL de empleador |

- El puntaje de un producto es la **suma de las reglas que aplican**; el desglose
  completo acompaña cada recomendación (interfaz, auditoría y panel del asesor).
  Reglas consultables en vivo: `GET /api/propension/reglas`.
- El **comportamiento observado pesa más que la demografía**: una marca de consumo
  activa es evidencia directa de la necesidad, no una inferencia.
- **Momento y canal**: el motor sugiere *cuándo* y *por dónde* contactar (tras la
  compra en droguería, al confirmar la reserva, al desembolso de vivienda, con la
  mesada pensional…).
- **Lo que la persona dice prevalece**: la propensión es el punto de partida; la
  conversación siempre le gana a la base.

### Etiquetas anonimizadas, correspondencia documentada

Colsubsidio entregó las clasificaciones internas (categoría, segmentos, pirámide)
anonimizadas con letras griegas (SIGMA, LAMBDA, RHO…). Su interpretación vive en
[`data/mapa_segmentos.json`](data/mapa_segmentos.json): correspondencia por
coincidencia de participaciones con la distribución pública del insumo del reto,
**validada con evidencia interna de la propia base**:

| Etiqueta | Interpretación | Evidencia de validación |
|---|---|---|
| SIGMA | Categoría A | El **99.2%** gana ≤ 2 SMLV (definición legal de la categoría A) |
| KAPPA | Pensionado | El **95.5%** es mayor de 55 años |
| ETA (poblacional) | Segmento Joven | El **83.2%** tiene 20–35 años |
| EMP_000002 | Empresa foco | 18.3% de la base ≈ 16.8% de la referencia pública |

Es un archivo **editable**: si Colsubsidio entrega el diccionario oficial, se
corrige ahí y el motor no cambia. Para regenerar mapa, estadísticas y muestra demo:
`python scripts/perfilar_base.py <ruta a la base .xlsx o .csv>`.

---

## Panel del asesor (`/asesor`)

Colsubsidio **no fabrica pólizas: las distribuye**. Por eso la venta autónoma
termina en una **bandeja de vinculaciones**: al firmarse el contrato, Clara
transmite la solicitud empaquetada — perfil de la base con segmentos
interpretados, propensión con razones, datos del tomador, contrato PDF, estado del
pago y póliza interna — y el asesor la avanza por estados:

```
pendiente_pago → pagada → enviada a aseguradora → emitida → cerrada
```

Cada avance **notifica a la sesión del afiliado**: si pregunta "¿cómo va mi
solicitud?", Clara le responde con el estado real. Los escalamientos a humano
también llegan a la bandeja como tickets.

---

## Arquitectura: el modelo pone las palabras, el sistema pone la verdad

Vender seguros con un LLM tiene un riesgo mortal: **que el modelo alucine una
cobertura, un precio o una condición**. Clara está diseñada para que no pueda pasar:

| Principio | Cómo lo garantiza Clara |
|---|---|
| **El LLM solo conversa** | Gemini nunca calcula ni inventa: dialoga y **llama herramientas** (function-calling). La lógica dura vive en el backend. |
| **Coberturas ⇒ base de conocimiento** | Cada afirmación sale de `consultar_coberturas`, **con cita de la fuente**. |
| **Precios ⇒ motor determinístico** | Ninguna cifra la produce el modelo: salen de `cotizar`, con factores auditables. |
| **Propensión ⇒ reglas explicables** | 34 reglas documentadas sobre variables reales; nada de puntajes opacos. |
| **Emisión ⇒ backend** | Contrato, firma, pago y póliza los ejecuta código determinístico. |
| **Guardrail de salida** | Cada respuesta se verifica: cobertura o precio sin respaldo queda marcado en auditoría. |
| **Cumplimiento por diseño** | Aviso Ley 1581 de 2012 desde el saludo; alcance restringido; resistencia a jailbreaks. |
| **Trazabilidad total** | Perfil, cotización, contrato, pago, póliza y solicitud quedan en SQLite y a la vista. |

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
     │◀── "ya quedaste   │◀─ emisión ───────────────────┤ póliza PDF           │
     │     asegurado"    │                              ├─ paquete completo ──▶│ bandeja
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
│   ├── pdfgen.py          # PDFs de resumen, contrato y póliza
│   ├── notify.py          # Correo / WhatsApp (opcional; sin credenciales, simula)
│   ├── store.py           # SQLite: sesiones, auditoría y bandeja del asesor
│   └── config.py          # Configuración central (.env)
├── scripts/
│   └── perfilar_base.py   # Procesa la base (.xlsx/.csv) → mapa + stats + demo
├── static/                # Frontend: chat, paneles y panel del asesor
├── data/                  # Mapa de segmentos, estadísticas y muestra demo (anonimizados)
└── Dockerfile · requirements.txt · .env.example
```

**Privacidad:** la base completa **nunca se versiona** (protegida en `.gitignore`).
Lo que sí va en `data/` son agregados, el mapa documentado y una muestra por SERIE.

---

## Configuración

| Variable | Por defecto | Descripción |
|---|---|---|
| `GEMINI_API_KEY` | — | **Obligatoria.** Clave de [AI Studio](https://aistudio.google.com/apikey) (`AIza…`) o Vertex Express (`AQ.…`). |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Modelo Gemini. |
| `ANTHROPIC_API_KEY` | — | Opcional. Si está presente, Claude es primario y **Gemini queda de respaldo automático**. |
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

## Estado de ejecución (honestidad de ingeniería)

MVP demostrable para la hackathon: el flujo principal se recorre completo en local.

| Área | Estado | Notas |
|---|---|---|
| Motor de propensión | ✅ Funcional | 34 reglas sobre la base real de 500k; oferta y saludo cambian por perfil. |
| Conversación (Gemini) | ✅ Funcional | Function-calling, escucha activa, atajos por petición directa. |
| Flujo end-to-end | ✅ Funcional | Diagnóstico → recomendación → contrato → firma → pago → emisión. |
| Panel del asesor | ✅ Funcional | Bandeja con paquete completo, estados y notificación al afiliado. |
| PDFs y persistencia | ✅ Funcional | Contrato/póliza reales (fpdf2); SQLite sobrevive reinicios. |
| Pago (estilo Wompi) | 🟡 Simulación | Checkout sandbox con validación Luhn; sin API real de producción. |
| Correo / WhatsApp | 🟡 Simulación | Con credenciales SMTP/Twilio envía de verdad. |

**Qué NO cubre (por diseño del reto):** integración real con aseguradoras, firma con
validez legal, siniestros/renovaciones y pasarela de pago en producción.

---

## Autora

**Mariana Sinisterra** · [@MarianaCodebase](https://github.com/MarianaCodebase)

Reto 2 · Seguros — Hackathon Colsubsidio × 30X · Bogotá, julio de 2026.
Prototipo demostrativo. Datos tratados conforme a la Ley 1581 de 2012.
