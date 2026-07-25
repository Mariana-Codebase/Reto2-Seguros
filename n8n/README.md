# Orquestación con n8n — Agente de ofertas

El **agente de ofertas** (segundo agente) reacciona a eventos de las bases de
Colsubsidio y envía la oferta pertinente. La **inteligencia** (qué ofrecer y por
qué) vive en la app, en [`app/ofertas.py`](../app/ofertas.py), y se expone como
webhook. **n8n** solo orquesta el disparo y el envío — así la lógica es
determinística, versionada y testeable, y la demo funciona incluso sin n8n.

## Importar el workflow

1. En tu n8n (`https://marianacodebase.app.n8n.cloud/`): **Workflows → Import from File**
   y elige [`agente-ofertas.workflow.json`](agente-ofertas.workflow.json).
2. Define la variable de entorno **`CLARA_BASE_URL`** con la URL pública de la app
   (en local, `http://localhost:8000`; en Spaces/hosting, la URL del despliegue).
3. Activa el workflow.

## Qué hace

- **Rama A · Webhook `POST /webhook/colsubsidio-evento`** — cuando otra base de
  Colsubsidio detecta un cambio (crédito desembolsado, alza de ingreso, nacimiento…),
  llama a este webhook con `{ "serie": "123", "evento": "credito_vivienda_desembolsado" }`.
  n8n reenvía a `POST /api/eventos` y el agente decide y envía la oferta.
- **Rama B · Programado (cada día 9:00)** — barre inactivos y dispara el evento
  `sin_interaccion_30d` para re-enganche con la mejor oferta por propensión.

## El endpoint que orquesta

```
POST /api/eventos
{ "serie": "123", "evento": "credito_vivienda_desembolsado", "datos": {}, "enviar": true }
```

Efecto: enriquece el perfil vivo con el evento, decide la oferta (regla
evento→producto explicable), la registra y la envía por el canal del cliente.
Respuesta: la oferta con su razón. Ver eventos soportados en
`GET /api/ofertas/catalogo`.

> Ejemplo insignia: `credito_vivienda_desembolsado` → **Seguro de Hogar** (protege
> el patrimonio recién financiado) + cross-sell de **Seguro de Vida** (cubre el saldo).

---

# Flujo de actualización de afiliados

Mientras el agente de ofertas **reacciona a eventos**, el **flujo de actualización**
mantiene el **perfil 360 en Mongo al día**: cuando otra base de Colsubsidio cambia
los datos de un cliente (subió el salario, cambió de empresa o ciudad, se
activó/desactivó), este flujo aplica el cambio y vuelve a evaluar si desbloquea una
oferta nueva.

## Importar el workflow

1. En tu n8n: **Workflows → Import from File** y elige
   [`agente-actualizacion.workflow.json`](agente-actualizacion.workflow.json).
2. Reutiliza la misma variable de entorno **`CLARA_BASE_URL`**.
3. Activa el workflow.

## Qué hace

- **Webhook `POST /webhook/colsubsidio-actualizacion`** — otra base llama con la
  serie y los campos a cambiar:
  ```json
  { "serie": "123", "campos": { "rango_salarial": "Entre 4 y 6 SMLV", "ciudad": "MEDELLIN" } }
  ```
- **`PATCH /api/afiliados/{serie}`** — aplica la actualización parcial en Mongo. La
  app solo acepta campos editables y registra el cambio en la bitácora `eventos`.
- **`GET /api/afiliados/{serie}/ofertas`** — re-evalúa ofertas y alertas con el
  perfil ya actualizado (un alza de salario o una vivienda nueva puede desbloquear
  una oferta que antes no aplicaba).
- **Respuesta** — `{ ok, actualizado, ofertas, alertas }` con el afiliado ya
  actualizado y las ofertas recalculadas.

## Campos editables

`genero` · `rango_edad` · `rango_salarial` · `categoria` · `segmento_familiar` ·
`segmento_poblacional` · `piramide` · `empresa` · `ciudad` · `marcas` (dict de
booleanos) · `afiliado_activo`. Cualquier otro campo enviado se ignora de forma
segura.

> Ejemplo: un afiliado sin vivienda al que otra base le marca `"marcas": { "vivienda": true }`
> pasa, en la misma llamada, a recibir la oferta de **Seguro de Hogar** en la respuesta.
