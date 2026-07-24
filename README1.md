# Clara — Asesora digital de seguros

**Reto 2 · Seguros** · Hackathon [Colsubsidio × 30X](https://innovacion.colsubsidio.com/) · Bogotá, julio de 2026

`Python` · `FastAPI` · `Gemini` · `SQLite` · `Docker`

---

## La idea en una frase

**Clara** conversa como una asesora real: perfila a cada persona, encuentra el seguro que le encaja y entrega al vendedor humano un expediente **listo para cerrar** — más rápido, con contexto y sin inventar coberturas ni precios.

No reemplaza al asesor en el cobro ni en la facturación. **Prepara el terreno** para que el cierre comercial sea humano, regulado y eficiente.

---



## Por qué destaca


| Diferencial                        | Qué significa en la práctica                                                                                            |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Diálogo primero, venta después** | No empuja un producto: entiende la vida de la persona (hogar, dependientes, viajes, riesgos) y recién entonces orienta. |
| **Base real de 500.000 afiliados** | La recomendación nace de reglas auditables sobre datos de Colsubsidio, no de intuición del modelo.                      |
| **Cada “por qué” es explicable**   | El panel de propensión muestra *variable → puntos → razón*. Nada de caja negra.                                         |
| **El LLM no inventa la verdad**    | Clara solo conversa y llama herramientas; coberturas, precios y propensión salen del backend.                           |
| **Cierre donde debe estar**        | Pago y facturación los hace el asesor. Clara escala cuando el caso ya esta practicamente definido.                      |
| **Dos agentes, una base viva**     | Quien llega habla con Clara; los eventos de otras bases disparan ofertas proactivas. El perfil crece con ambos.         |


Colsubsidio **distribuye** pólizas; no las emite. El valor de Clara está en la **calidad del perfil y de la recomendación** que llega a la bandeja — no en emitir ni cobrar.

---



## Cómo trabaja Clara

Clara recibe un mensaje en el chat e interactúa de la forma más humana posible. El objetivo operativo es uno: **perfilar** y dejar al vendedor un proceso más ameno y rápido.


| Situación del usuario          | Qué hace Clara                                                               |
| ------------------------------ | ---------------------------------------------------------------------------- |
| **Aún no sabe** qué necesita   | Guía con preguntas naturales hasta el seguro que mejor encaja con su perfil. |
| **Ya tiene claro** el producto | Corrobora requisitos; si aplica, **escala a un humano** para el cierre.      |
| **Afiliado conocido**          | Confirma o actualiza lo que ya hay en la base.                               |
| **Nuevo / visitante**          | Construye el perfil desde cero, pregunta a pregunta.                         |




### Flujo de punta a punta

```
Chat → perfilado (nuevo o actualización)
     → recomendación / validación de requisitos
     → escalado a asesor humano
     → el asesor cierra: facturación, pago y trámite con la aseguradora
```

El asesor recibe un **perfil completo**: datos de la base + lo contado en el chat + intereses + razones de propensión. No empieza de cero.

---



## Dos agentes, una misma base viva


|                  | Agente 1 · **Clara** (conversacional)                                                                                                              | Agente 2 · **Ofertas** (proactivo)                                                                               |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Cuándo actúa** | Cuando la persona llega y escribe                                                                                                                  | Ante eventos de las bases de Colsubsidio                                                                         |
| **Qué hace**     | Identifica afiliado o visitante, perfila por diálogo, recomienda con respaldo, cotiza para orientar y **escala al asesor** con el expediente listo | Detecta un cambio (crédito desembolsado, alza de ingreso, cumpleaños, inactividad…) y envía la oferta pertinente |
| **Salida**       | Perfil vivo + propensión explicada + producto sugerido o validado → bandeja humana                                                                 | Oferta de seguro **o** crédito por el canal correcto                                                             |
| **Aprendizaje**  | Cada interacción **enriquece el perfil vivo**                                                                                                      | Cada evento suma al mismo perfil                                                                                 |


El agente 2 se orquesta con **n8n** (`POST /api/eventos`); la inteligencia vive en la app (`[app/ofertas.py](app/ofertas.py)`).

---



## Qué se ve en la solución

1. **Identificación** — Clara reconoce si la persona es afiliada: busca en la base, carga perfil y propensión; si no existe, continúa como visitante con perfil nuevo. En la interfaz, el selector *“Perfil de la base de afiliados”* (identificado por SERIE) o *“Visitante anónimo”* elige ese camino.
2. **Oferta que cambia con la persona** — Con un perfil real, el saludo y la recomendación se personalizan. El panel **“Propensión · por qué esta oferta”** muestra las razones exactas. Ejemplos: monoparental → Vida · joven sin grupo familiar → Accidentes · compra viajes → Asistencia en Viajes · usó vivienda → Hogar · pensionado → Exequial.
3. **Diálogo y auditoría en vivo** — Preguntas naturales (hogar, dependientes, vehículo, viajes, preocupaciones…). Cada decisión relevante queda registrada junto al chat. Cuando el caso está listo, **escala a humano** con el contexto completo.

El **pago, la firma comercial y la facturación** no los ejecuta el agente: quedan en manos del asesor, con el expediente ya preparado.

---



## Propensión explicable (base real)

Insumo: `Usos_Productos_Afiliados_SIN_ID.xlsx` — **500.000 registros** por **SERIE** (sin nombres ni cédulas).

La pregunta *¿por qué este seguro y no otro?* se responde con una **tabla de reglas auditables** (`[app/propension.py](app/propension.py)`):


| Variable de la base      | Ejemplo de regla              | Producto            | Fundamento                                   |
| ------------------------ | ----------------------------- | ------------------- | -------------------------------------------- |
| Segmento familiar        | Familia monoparental          | Vida (+30)          | Hijos que dependen de un solo ingreso        |
| Segmento familiar        | Sin grupo familiar            | Accidentes (+18)    | Su mayor riesgo es su propia incapacidad     |
| Marca VIVIENDA           | Usó el servicio de vivienda   | Hogar (+40)         | Estrena patrimonio que proteger              |
| Marca AGENCIAS / HOTELES | Compra viajes u hoteles       | Viajes (+35/30)     | Ya viaja: se protege lo que ya hace          |
| Marca DROGUERÍA          | Gasto recurrente en droguería | Salud (+15)         | Necesidad de salud activa (17.6% de la base) |
| Rango salarial           | Más de 4 SMLV                 | Vida y Ahorro (+10) | Capacidad real de proteger y ahorrar         |
| Rango de edad            | Mayor de 55 años              | Exequial (+20)      | Anticipar evita cargas a la familia          |
| Pirámide                 | Independiente                 | Accidentes (+10)    | Sin ARL de empleador                         |


- **34 reglas.** El puntaje es la suma de las que aplican; el desglose acompaña cada recomendación. En vivo: `GET /api/propension/reglas`.
- El **comportamiento observado pesa más que la demografía**.
- El motor sugiere también **momento y canal** de contacto.
- **La conversación prevalece**: lo que la persona dice en el chat tiene prioridad sobre la base.



### Etiquetas anonimizadas (mapa documentado)

Las clasificaciones internas llegan con letras griegas. Su lectura está en `[data/mapa_segmentos.json](data/mapa_segmentos.json)`, validada contra la propia base:


| Etiqueta          | Interpretación | Evidencia                                         |
| ----------------- | -------------- | ------------------------------------------------- |
| SIGMA             | Categoría A    | El **99.2%** gana ≤ 2 SMLV                        |
| KAPPA             | Pensionado     | El **95.5%** es mayor de 55 años                  |
| ETA (poblacional) | Segmento Joven | El **83.2%** tiene 20–35 años                     |
| EMP_000002        | Empresa foco   | 18.3% de la base ≈ 16.8% de la referencia pública |


El mapa es **editable** sin tocar el motor. Regeneración: `python scripts/perfilar_base.py <ruta .xlsx o .csv>`.

---



## Panel del asesor (`/asesor`)

Clara termina cuando el caso está listo para un humano:

- perfil de la base (segmentos interpretados),
- propensión con razones,
- lo capturado en la conversación,
- producto orientado o validado.

Los **escalamientos** llegan como tickets. El asesor usa ese expediente para **facturar, cobrar y coordinar con la aseguradora**.

---



## Agente de ofertas (`/ofertas`)

Mientras Clara atiende a quien llega, el segundo agente escucha **eventos** y responde con ofertas explicables (seguros y créditos):


| Evento                                 | Oferta                                       | Por qué                                 |
| -------------------------------------- | -------------------------------------------- | --------------------------------------- |
| `credito_vivienda_desembolsado`        | **Seguro de Hogar** (+ cross Vida)           | Protege el patrimonio recién financiado |
| `credito_vehiculo_desembolsado`        | Seguro de Autos                              | Cubre el vehículo financiado            |
| `credito_libre_inversion_desembolsado` | Seguro de Vida                               | Protege el saldo pendiente              |
| `nacimiento_hijo`                      | Seguro de Vida (+ Salud)                     | Cambia la prioridad del hogar           |
| `alza_ingreso`                         | Crédito de Libre Inversión (+ Vida y Ahorro) | Más capacidad de pago                   |
| `consulta_vivienda`                    | Crédito de Vivienda (+ Hogar)                | Interés detectado                       |
| *(otro)*                               | Mejor seguro por propensión                  | Re-enganche con el perfil               |


Ejemplo: crédito de vivienda desembolsado → oferta de **hogar** citando ese evento, con cross-sell de vida. Todo queda en el perfil vivo.

Interfaz de simulación: `/ofertas`. Workflow n8n: `[n8n/agente-ofertas.workflow.json](n8n/agente-ofertas.workflow.json)`.

---



## Arquitectura: el modelo habla; el sistema decide


| Principio                          | Cómo se garantiza                                                         |
| ---------------------------------- | ------------------------------------------------------------------------- |
| **El LLM solo conversa**           | Gemini dialoga y llama herramientas; la lógica dura vive en el backend.   |
| **Coberturas ⇒ conocimiento**      | `consultar_coberturas` con cita de fuente.                                |
| **Precios ⇒ motor determinístico** | `cotizar` con factores auditables (orientan; el cobro lo hace el asesor). |
| **Propensión ⇒ reglas**            | 34 reglas sobre variables reales.                                         |
| **Cierre comercial ⇒ humano**      | Escalado con perfil masticado; pago y facturación fuera del agente.       |
| **Guardrail de salida**            | Cobertura o precio sin respaldo queda marcado en auditoría.               |
| **Cumplimiento por diseño**        | Aviso Ley 1581 de 2012 desde el saludo; alcance restringido.              |
| **Trazabilidad**                   | Perfil, cotización y eventos en SQLite, visibles en la interfaz.          |


```
  Afiliado / visitante     Clara (Gemini)           Backend                 Asesor humano
         │                      │                      │                         │
         │  mensaje en chat     │                      │                         │
         ├─────────────────────▶│ propensión + diálogo │                         │
         │                      │ de perfilado         │                         │
         │◀── preguntas /       ├─ recomendar ────────▶│ reglas + coberturas     │
         │    oferta con porqué │                      │                         │
         │  “quiero este” o     ├─ escalar_a_humano ──▶│ ticket / expediente ───▶│ cierra:
         │  “no sé cuál”        │                      │ (perfil masticado)      │ factura,
         │                      │                      │                         │ pago,
         │                      │                      │                         │ aseguradora
```

---



## Cómo levantarlo

```bash
pip install -r requirements.txt
copy .env.example .env        # pegar GEMINI_API_KEY (aistudio.google.com/apikey)
python server.py              # → http://localhost:8000
```


| Variable              | Por defecto              | Descripción                                                                        |
| --------------------- | ------------------------ | ---------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`      | —                        | **Obligatoria.** [AI Studio](https://aistudio.google.com/apikey) o Vertex Express. |
| `GEMINI_MODEL`        | `gemini-2.0-flash`       | Modelo Gemini.                                                                     |
| `ANTHROPIC_API_KEY`   | —                        | Opcional: Claude primario, Gemini de respaldo.                                     |
| `PORT`                | `8000` / `7860` (Docker) | Puerto HTTP.                                                                       |
| `SMTP_*` / `TWILIO_*` | —                        | Correo / WhatsApp reales (sin ellas, se simula).                                   |


```bash
docker build -t clara .
docker run -p 7860:7860 -e GEMINI_API_KEY=AIza... clara
```

---



## Estructura y API

```
├── server.py · app/main.py · app/agent.py · app/ofertas.py
├── app/base_afiliados.py · propension.py · knowledge.py · llm.py · store.py
├── static/          # chat, asesor, ofertas
├── data/            # mapa, stats, muestra demo (anonimizados)
├── n8n/             # workflow del agente de ofertas
└── Dockerfile · requirements.txt · .env.example
```


| Endpoint                                     | Qué hace                   |
| -------------------------------------------- | -------------------------- |
| `POST /api/session` · `POST /api/chat`       | Conversación con Clara     |
| `POST /api/identificar`                      | ¿Es afiliado? carga perfil |
| `GET /api/perfil/{id}` · `GET /api/perfiles` | Perfil vivo                |
| `POST /api/eventos`                          | Agente de ofertas (n8n)    |
| `GET /api/ofertas/salientes` · `/catalogo`   | Ofertas y catálogo         |
| `GET /api/asesor/solicitudes`                | Bandeja del asesor         |


**Privacidad:** la base completa **no se versiona**. En `data/` solo hay agregados, mapa y muestra por SERIE.

---



## Qué está en el núcleo de la solución


| Capacidad | Estado |
| --- | --- |
| Identificación de afiliado | ✅ |
| Motor de propensión (34 reglas, base 500k) | ✅ |
| Perfil vivo que se enriquece | ✅ |
| Conversación con Gemini + herramientas | ✅ |
| Escalado a humano con expediente completo | ✅ |
| Agente de ofertas (evento → oferta / n8n) | ✅ |

---

## Equipo

- **Mariana Sinisterra** · [@MarianaCodebase](https://github.com/MarianaCodebase)
- **Michael Daniel** · [@MaicolD0930](https://github.com/MaicolD0930)
- **Jorge Martinez** · [@JorgeAMS](https://github.com/GeorgeAMS)

Hackathon Colsubsidio × 30X · Bogotá, julio de 2026.  
Prototipo demostrativo. Datos tratados conforme a la Ley 1581 de 2012.