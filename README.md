# Criptonite 🪨

Modelo avanzado para la evaluación de precios de mercado, historia y atributos clave de las **10 criptomonedas más rentables y con menor riesgo**.  
Propone y/o ejecuta la compra de activos al menor precio posible y la venta al mayor precio posible, maximizando la rentabilidad neta (descontando comisiones) para inversiones iniciales entre **$50 y $500 USD**.

---

## Características

| Módulo | Descripción |
|---|---|
| `fetcher.py` | Obtiene cotizaciones en tiempo real e histórico de 90 días vía CoinGecko API (gratuita, sin clave) |
| `analyzer.py` | Calcula RSI, MACD, Bandas de Bollinger, SMA/EMA, Sharpe Ratio, drawdown máximo y tendencia de volumen |
| `ranker.py` | Puntúa y ordena las monedas usando una combinación ponderada de Sharpe (35 %), momentum (30 %), volatilidad inversa (20 %) y volumen (15 %) |
| `strategy.py` | Genera señales **BUY / SELL / HOLD** con precio de entrada sugerido, objetivo de ganancia, stop-loss y rentabilidad neta estimada (con comisiones) |
| `portfolio.py` | Ledger en memoria con persistencia JSON para gestión de posiciones abiertas y cerradas (paper trading) |
| `reporter.py` | Reporte enriquecido en terminal con tablas y paneles por moneda |

---

## Instalación

```bash
pip install -r requirements.txt
```

> Requiere Python ≥ 3.10.

---

## Uso

```bash
# Análisis con $100 por posición y comisión estándar 0.10 % (sin guardar portafolio)
python main.py --dry-run

# Análisis con $250 por posición
python main.py --investment 250

# Comisión personalizada (p. ej. 0.05 % de Binance VIP)
python main.py --investment 150 --fee 0.0005

# Ver todas las opciones
python main.py --help
```

### Opciones

| Argumento | Descripción | Valor por defecto |
|---|---|---|
| `--investment USD` | Capital a desplegar por posición ($50–$500) | `100` |
| `--fee RATE` | Tasa de comisión taker (fracción) | `0.001` (0.10 %) |
| `--dry-run` | Solo análisis; no escribe `portfolio.json` | `False` |
| `--verbose` | Habilita logging DEBUG | `False` |

---

## Lógica de señales

### BUY
Se recomienda compra cuando hay más señales alcistas que bajistas entre:
- RSI < 35 (sobreventa)
- Histograma MACD positivo (cruce alcista)
- Precio cerca de la banda inferior de Bollinger
- Golden cross (SMA20 > SMA50)
- Caída de 30 días > 10 % (oportunidad de dip)

### SELL
Se recomienda venta cuando predominan señales bajistas:
- RSI > 65 (sobrecompra)
- MACD bajista
- Precio cerca de la banda superior de Bollinger
- Death cross (SMA20 < SMA50)

### Precio de entrada
Se propone una orden límite con un **0.5 % de descuento** sobre el precio actual para compras, capturando micro-correcciones sin perder la oportunidad.

### Objetivo de ganancia
El mayor valor entre:
- Mínimo de rentabilidad neta objetivo (1.5 % tras comisiones)
- Banda superior de Bollinger (si está por encima)

### Stop-loss
El mayor valor entre:
- Banda inferior de Bollinger
- 5 % por debajo del precio de entrada

---

## Ejecución de pruebas

```bash
python -m pytest tests/ -v
```

---

## Estructura del proyecto

```
criptonite/
├── main.py              # Punto de entrada CLI
├── requirements.txt     # Dependencias
├── README.md
├── criptonite/
│   ├── __init__.py
│   ├── config.py        # Constantes y umbrales configurables
│   ├── fetcher.py       # Cliente CoinGecko API
│   ├── analyzer.py      # Motor de indicadores técnicos
│   ├── ranker.py        # Sistema de puntuación y ranking
│   ├── strategy.py      # Generador de señales y sizing de posiciones
│   ├── portfolio.py     # Gestor de portafolio (paper trading)
│   └── reporter.py      # Reporte en terminal (Rich)
└── tests/
    ├── test_analyzer.py
    ├── test_ranker.py
    ├── test_strategy.py
    ├── test_portfolio.py
    └── test_integration.py
```

---

## Descargo de responsabilidad

Esta herramienta es únicamente para fines educativos y de investigación.  
**No constituye asesoramiento financiero.** El trading de criptomonedas implica riesgo de pérdida de capital.  
Use siempre su propio juicio y consulte con un asesor financiero certificado antes de invertir.
