# Lara — Venta automatizada de seguros

Solución al **Reto 2 · Seguros** · Hackathon [Colsubsidio × 30X](https://innovacion.colsubsidio.com/) · Bogotá, julio de 2026

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Gemini_2.0_Flash-4285F4?logo=google&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-trazabilidad_total-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-listo-2496ED?logo=docker&logoColor=white)

**Lara** es una asesora digital que lleva a cada afiliado desde *"no sé qué seguro
necesito"* hasta *"ya quedé asegurado"*, sin intervención humana: identifica la
propensión desde la base real de afiliados, personaliza la oferta, explica cada
recomendación, cierra la vinculación y — como Colsubsidio distribuye pólizas, no
las emite — entrega al asesor humano un **perfil completo** para que finalice la
compra con la aseguradora.

## Dos agentes que trabajan juntos

| | Agente 1 · **Lara** (conversacional) | Agente 2 · **Ofertas** (proactivo) |
|---|---|---|
| **Cuándo actúa** | Cuando la persona llega y escribe | Solo, ante eventos de las bases de Colsubsidio |
| **Qué hace** | Identifica si es afiliado, diagnostica, recomienda, cotiza, contrata, firma, cobra y radica la vinculación | Detecta un cambio (crédito desembolsado, alza de ingreso, cumpleaños, inactividad) y envía la oferta pertinente |
| **Salida** | Perfil completo al asesor humano para cerrar con la aseguradora | Oferta de seguro **o** crédito por el canal correcto |
| **Aprendizaje** | Cada interacción **enriquece el perfil vivo** del usuario | Cada evento suma al mismo perfil, que se vuelve más claro |

Ambos comparten una **base viva**: la base de afiliados es la semilla, y cada
conversación y cada evento la enriquecen, de modo que Colsubsidio entiende cada
vez mejor a su gente. El agente 2 se orquesta con **n8n** (webhook →
`/api/eventos`); la inteligencia vive en la app.

---

## Ejecución en 2 minutos

```bash
pip install -r requirements.txt
copy .env.example .env        # pegar GEMINI_API_KEY (aistudio.google.com/apikey)
python server.py              # → http://localhost:8000
```

## Recorrido de la demo

0. **Identificación** — Al iniciar, Lara puede reconocer si la persona es afiliada:
   busca su número en la base y, si existe, carga su perfil y propensión; si no,
   sigue como no afiliada (y un asesor completará la vinculación). En la demo, el
   selector *"Perfil de la base de afiliados"* hace esa identificación; la opción
   *"Visitante anónimo"* recorre el camino de no afiliado.
1. En **Demo interactiva**, el selector *"Perfil de la base de afiliados"* carga
   perfiles reales (identificados por SERIE). Lara saluda personalizada según el
   perfil y el panel **"Propensión · por qué esta oferta"** muestra las razones
   exactas de la recomendación. Al cambiar de perfil, **la oferta cambia**:
   monoparental → Vida · joven sin grupo familiar → Accidentes · compra viajes →
   Asistencia en Viajes · usó el servicio de vivienda → Hogar · pensionado → Exequial.
2. El flujo también funciona para un **visitante anónimo**: ante *"no sé qué seguro
   necesito"*, Lara diagnostica con preguntas abiertas y adapta la recomendación a
   lo que la persona cuenta (mascotas, vehículo, viajes, dependientes…).
3. Elegido un producto, Lara reúne los datos, genera el **contrato en PDF**, captura
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
termina en una **bandeja de vinculaciones**: al firmarse el contrato, Lara
transmite la solicitud empaquetada — perfil de la base con segmentos
interpretados, propensión con razones, datos del tomador, contrato PDF, estado del
pago y resumen de vinculación — y el asesor la avanza por estados hasta que la
aseguradora emite la póliza:

```
pendiente_pago → pagada → enviada a aseguradora → emitida → cerrada
```

Cada avance **notifica a la sesión del afiliado**: si pregunta por su solicitud,
Lara responde con el estado real. Los escalamientos a humano también llegan a la
bandeja como tickets. El asesor recibe un **perfil completo** del usuario (lo de la
base + lo que contó + intereses + eventos de vida) para cerrar con contexto.

---

## Agente de ofertas (`/ofertas`) — el segundo agente

Mientras Lara atiende a quien llega, el **agente de ofertas** actúa por su cuenta.
Escucha **eventos** de las bases de Colsubsidio y, para cada uno, decide la oferta
más pertinente con una **regla explicable** (nada aleatorio) y la envía por el mejor
canal. Cruza dos portafolios: **seguros** y **créditos** (colsubsidio.com/creditos).

| Evento (otra base) | Oferta | Por qué |
|---|---|---|
| `credito_vivienda_desembolsado` | **Seguro de Hogar** (+ cross Vida) | Protege el patrimonio recién financiado |
| `credito_vehiculo_desembolsado` | Seguro de Autos | Cubre el vehículo financiado |
| `credito_libre_inversion_desembolsado` | Seguro de Vida | Protege del saldo pendiente |
| `nacimiento_hijo` | Seguro de Vida (+ Salud) | Un nuevo integrante cambia la prioridad |
| `alza_ingreso` | Crédito de Libre Inversión (+ Vida y Ahorro) | Más capacidad de pago |
| `consulta_vivienda` | Crédito de Vivienda (+ Hogar) | Interés detectado |
| *(cualquier otro)* | Mejor seguro por propensión | Re-enganche con base en el perfil |

La **inteligencia vive en la app** ([`app/ofertas.py`](app/ofertas.py)) y se dispara
con `POST /api/eventos`; **n8n** solo orquesta (webhook y envío). Así funciona sola
para el jurado y se integra con n8n en producción. En `/ofertas` puedes **simular un
evento** y ver la decisión. El workflow importable está en
[`n8n/agente-ofertas.workflow.json`](n8n/agente-ofertas.workflow.json).

> **Ejemplo insignia:** otra base marca que el afiliado adquirió un crédito de
> vivienda → el agente le ofrece el **seguro de hogar** citando ese evento como
> motivo, y suma un cross-sell de vida. Todo queda en el perfil vivo.

---

## Arquitectura: el modelo pone las palabras, el sistema pone la verdad

Vender seguros con un LLM tiene un riesgo crítico: que el modelo invente una
cobertura, un precio o una condición. Lara está diseñada para que no pueda pasar:

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
  Afiliado           Lara (Gemini)            Backend determinístico        Asesor
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
│   ├── main.py            # API FastAPI + checkout + paneles + webhooks de eventos
│   ├── agent.py           # Agente 1 (Lara): sesión, herramientas, guardrail, perfil vivo
│   ├── ofertas.py         # Agente 2: reglas evento → oferta (seguros + créditos)
│   ├── base_afiliados.py  # Lookup en la base: ¿es afiliado? carga su perfil
│   ├── propension.py      # Motor de propensión: 34 reglas explicables
│   ├── knowledge.py       # Catálogo de 14 productos, coberturas y cotizador
│   ├── llm.py             # Cliente Gemini (AI Studio / Vertex) + respaldo automático
│   ├── extraction.py      # Captura de datos: regex + salida estructurada
│   ├── payments.py        # Pasarela simulada (tarjetas de prueba, Luhn)
│   ├── pdfgen.py          # PDFs de resumen, contrato y vinculación
│   ├── notify.py          # Correo / WhatsApp (opcional; sin credenciales, simula)
│   ├── store.py           # SQLite: sesiones, auditoría, bandeja, perfil vivo, ofertas
│   └── config.py          # Configuración central (.env)
├── scripts/
│   └── perfilar_base.py   # Procesa la base (.xlsx/.csv) → mapa + stats + demo
├── static/                # Frontend: chat (index) + asesor + ofertas
├── data/                  # Mapa de segmentos, estadísticas y muestra demo (anonimizados)
├── n8n/                   # Workflow importable del agente de ofertas + guía
└── Dockerfile · requirements.txt · .env.example
```

### API principal

| Endpoint | Qué hace |
|---|---|
| `POST /api/session` · `POST /api/chat` | Conversación con Lara (agente 1) |
| `POST /api/identificar` | ¿Es afiliado? busca en la base y carga su perfil |
| `GET /api/perfil/{id}` · `GET /api/perfiles` | Perfil vivo (la base que se enriquece) |
| `POST /api/eventos` | **Agente de ofertas**: evento → oferta (lo llama n8n) |
| `GET /api/ofertas/salientes` · `/catalogo` | Ofertas generadas y catálogo de eventos/créditos |
| `GET /api/asesor/solicitudes` | Bandeja del asesor con el perfil completo |

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
| Identificación de afiliado | ✅ Funcional | Busca en la base; afiliado carga perfil, no afiliado sigue con perfil nuevo. |
| Motor de propensión | ✅ Funcional | 34 reglas sobre la base real de 500k; oferta y saludo cambian por perfil. |
| Perfil vivo (base que crece) | ✅ Funcional | Cada interacción y cada evento enriquecen el perfil en SQLite. |
| Conversación (Gemini) | ✅ Funcional | Function-calling, escucha activa, atajos por petición directa. |
| Flujo end-to-end | ✅ Funcional | Identificación → diagnóstico → recomendación → contrato → firma → pago → vinculación. |
| Agente de ofertas (2.º) | ✅ Funcional | Evento → oferta explicable (seguro/crédito); disparable por n8n. |
| Panel del asesor | ✅ Funcional | Bandeja con **perfil completo**, estados y notificación al afiliado. |
| PDFs y persistencia | ✅ Funcional | Contrato y resumen de vinculación reales (fpdf2); SQLite sobrevive reinicios. |
| Orquestación n8n | 🟡 Listo para importar | Workflow cableado a los webhooks; requiere `CLARA_BASE_URL`. |
| Pago (estilo Wompi) | 🟡 Sandbox | Checkout con tarjetas de prueba y validación Luhn. |
| Correo / WhatsApp | 🟡 Simulado | Con credenciales SMTP/Twilio envía de verdad. |

Fuera de alcance por diseño del reto: integración real con aseguradoras, firma con
validez legal, gestión de siniestros/renovaciones y pasarela de pago en producción.

---

## Autora

**Mariana Sinisterra** · [@MarianaCodebase](https://github.com/MarianaCodebase)

Hackathon Colsubsidio × 30X · Bogotá, 23 de julio de 2026.
Prototipo demostrativo. Datos tratados conforme a la Ley 1581 de 2012.
