# Forex Strategy Framework V2 (Session-Optimized)

## Core Philosophy
* **Pure Python Execution**: No AI API calls during runtime.
* **Session-Gated**: Every setup has a hard time window. **Zero execution during London hours.**
* **Score Gate**: Minimum 5/7 required for entry.
* **Hard News Block**: 30 min before to 15 min after high-impact releases.
* **Live Spread Check**: Reject signal if spread exceeds threshold at entry time.

---

## Session Windows & Operational Hours

| Session | ET Time | Permitted Action | Primary Pairs |
| :--- | :--- | :--- | :--- |
| **Asia Session** | 7:00 PM - 10:00 PM | **ACTIVE EXECUTION** | USD/JPY, AUD/USD |
| Overnite / London | 10:00 PM - 9:00 AM | *Passive Tracking Only* | None (Execution Blocked) |
| **New York Open** | 9:00 AM - 12:00 PM | **ACTIVE EXECUTION** | EUR/USD, GBP/USD, AUD/USD |
| **NY Afternoon** | 12:00 PM - 4:55 PM | **ACTIVE EXECUTION** | EUR/USD only |
| **Rollover Block** | 4:55 PM - 6:05 PM | *Strict Blackout* | None (Spread Trap) |

---

## Setup 1 - Asian Range Break (EUR/USD, GBP/USD, AUD/USD)

**Concept**: During the Asian/early London session, price consolidates. We passively track this range overnight and trade the first pullback after the breakout during the New York open.

**Rules**:
* **Define Range**: Highest high and lowest low between 12:00 AM - 6:00 AM ET.
* **Range Filters**: Width must be 20 to 60 pips.
* **LONG**: Price closes above range high on 15M candle -> wait for pullback to range high -> enter on bounce.
* **SHORT**: Price closes below range low on 15M candle -> wait for pullback to range low -> enter on bounce.
* **Active Execution Window**: 9:00 AM - 11:00 AM ET strictly.
* **Stop Loss**: Below range low (LONG) / above range high (SHORT) + 0.5x ATR buffer.
* **Targets**: TP1 at 1x range width projected; TP2 at 1.618x range width.

**Score Factors (Min 5/7)**:
1. Daily EMA50 trend aligns with trade direction (+1)
2. 4H EMA50 trend aligns (+1)
3. 1H DEMA direction aligns (+1)
4. RSI 14 (1H) not in extreme zone (longs: RSI < 65, shorts: RSI > 35) (+1)
5. ATR14 within normal range (0.7x - 1.4x of 20-period average) (+1)
6. Breakout candle body > 60% of total candle (+1)
7. No open trade in USD-quote group (+1)

---

## Setup 2 - NY Open Liquidity Sweep (EUR/USD, GBP/USD)

**Concept**: At NY open, market makers sweep the London session high/low to trigger stops, then reverse sharply.

**Rules**:
* **Passive Tracking**: Record London session high and low (3:00 AM - 8:30 AM ET).
* **SHORT**: Price spikes above London high between 9:00-10:00 AM ET by at least 5 pips, then closes back below London high on 5M -> enter short.
* **LONG**: Price spikes below London low between 9:00-10:00 AM ET by at least 5 pips, then closes back above London low on 5M -> enter long.
* **Active Execution Window**: 9:00 AM - 10:30 AM ET strictly.
* **Stop Loss**: Beyond the sweep wick extreme + 0.3x ATR.
* **Targets**: TP1 at 50% retracement of London range; TP2 at full London range retracement.
* **Limit**: Max 1 signal per day per pair.

**Score Factors (Min 5/7)**:
1. Sweep wick exceeds London extreme by 5-25 pips (+1)
2. Reversal closes back inside London range within 2 candles (+1)
3. 4H trend supports reversal direction (+1)
4. Daily trend supports reversal direction (+1)
5. RSI 14 (15M) shows divergence at sweep extreme (+1)
6. No FVG in direction of sweep (+1)
7. ATR normal, not spiked (+1)

---

## Setup 3 - PDH/PDL Sweep + Reversal (All Pairs)

**Concept**: Price sweeps Prior Day High (PDH) or Prior Day Low (PDL), taking liquidity, then reverses.

**Rules**:
* **SHORT**: Price trades above PDH by 3-20 pips, closes back below PDH on 15M -> enter short.
* **LONG**: Price trades below PDL by 3-20 pips, closes back above PDL on 15M -> enter long.
* **Active Execution Windows**: 
  * EUR/USD, GBP/USD, AUD/USD: 9:00 AM - 12:00 PM ET.
  * USD/JPY: 7:00 PM - 10:00 PM ET.
* **Stop Loss**: Beyond the sweep extreme + 0.5x ATR.
* **Targets**: TP1 at 0.75x risk; TP2 at previous session midpoint.
* **Limit**: Max 1 signal per day per pair.

**Score Factors (Min 5/7)**:
1. Sweep amount is strictly 3-20 pips (+1)
2. Reversal candle body > 60% of total candle (+1)
3. 4H trend supports reversal (+1)
4. 1H structure shows previous support/resistance at PDH/PDL (+1)
5. RSI not already at reversal extreme before sweep (+1)
6. DEMA on 15M turns in reversal direction (+1)
7. No major news within 2 hours (+1)

---

## Setup 4 - EMA50 Trend Continuation (USD/JPY, EUR/USD)

**Concept**: In a clearly trending market, price pulls back to the 1H EMA50 and bounces.

**Rules**:
* **Trend Requirement**: Daily + 4H must agree (both Bullish or both Bearish).
* **LONG**: Price touches 1H EMA50 from above, RSI 14 is in 40-50 zone -> enter long at EMA50.
* **SHORT**: Price touches 1H EMA50 from below, RSI 14 is in 50-60 zone -> enter short at EMA50.
* **Active Execution Windows**: 9:00 AM - 4:55 PM ET & 7:00 PM - 10:00 PM ET.
* **Stop Loss**: 1.0x ATR beyond EMA50.
* **Targets**: TP1 at previous swing extreme; TP2 at 2x ATR from entry.

**Score Factors (Min 5/7)**:
1. Daily trend aligned (+1)
2. 4H trend aligned (+1)
3. 1H trend aligned (+1)
4. RSI in specific pullback zone (+1)
5. Price has not crossed EMA50 more than once in last 4 candles (+1)
6. ATR14 within normal range (+1)
7. No major news within 2 hours (+1)

---

## Risk, Exposure & Exit Management

### 1. Hard Filters
* **News Block**: Block execution 30 minutes before and 15 minutes after high-impact events (ECB, Fed, NFP, CPI, BoJ). Block 15 min before to 10 min after medium-impact events.
* **Spread Filters (Live API Check)**: 
  * EUR/USD max spread: 1.5 pips
  * GBP/USD max spread: 2.0 pips
  * AUD/USD max spread: 1.8 pips
  * USD/JPY max spread: 1.5 pips
* **ATR Regime Filter**: 
  * If 1H ATR14 > 1.5x of 20 SMA -> Block Setup 4 (EMA Bounce).
  * If 1H ATR14 < 0.6x of 20 SMA -> Block ALL setups (dead market).

### 2. Exposure Manager (Crucial)
* **USD-Quote Bucket (EUR/USD, GBP/USD, AUD/USD)**: Maximum ONE open trade across this entire group at any time to prevent correlation risk.
* **USD/JPY Bucket**: Independent exposure. Can run simultaneously alongside one USD-quote trade.

### 3. Exit Management
* **Take Profit Logic**: When TP1 hits, move Stop Loss to breakeven immediately. Let TP2 run.
* **Time-Based Session Kills (Hard Exits)**:
  * All active New York session trades MUST force-close at market by **4:55 PM ET** (to avoid the 5:00 PM rollover spread trap).
  * All active Asia session trades MUST force-close at market by **10:00 PM ET** (end of your designated active window).
