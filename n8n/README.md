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
