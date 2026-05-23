# Active Strategy Reference — Gemini V2
**Version:** V2  
**Last Updated:** 2026-05-23  
**Status:** Active — 3 pairs, 3 setups only  

---

## Overview

| Item              | Value                                    |
|-------------------|------------------------------------------|
| Pairs             | EUR/USD, GBP/USD, AUD/USD               |
| Excluded          | USD/JPY (27% WR, -$992/yr, removed)     |
| Active Setups     | S1 + S2 + S3                            |
| Removed Setups    | Setup 4 — EMA50 Continuation (removed)  |
| Account Size      | $10,000                                  |
| Risk Per Trade    | $100 (1%)                               |
| TP1 Target        | 0.75R (half position)                   |
| TP2 Target        | 2.0R (S2/S3) / 1.618R (S1)             |
| After TP1         | SL moves to breakeven                   |

---

## Score Gate (7 Factors — minimum 5/7 to take trade)

| # | Factor                          | Long Condition          | Short Condition         |
|---|----------------------------------|-------------------------|-------------------------|
| 1 | Daily EMA50 alignment           | Price > Daily EMA50     | Price < Daily EMA50     |
| 2 | 4H EMA50 alignment              | Price > 4H EMA50        | Price < 4H EMA50        |
| 3 | 1H DEMA9 direction              | DEMA9 rising            | DEMA9 falling           |
| 4 | RSI14 not extreme               | RSI < 65                | RSI > 35                |
| 5 | ATR vs 20-bar ATR SMA           | ATR ratio 0.7–1.4×      | ATR ratio 0.7–1.4×      |
| 6 | Breakout candle body            | Body > 60% of ATR       | Body > 60% of ATR       |
| 7 | No conflicting USD exposure     | Auto +1 (managed)       | Auto +1 (managed)       |

**Pass threshold: 5 or more factors = trade taken**

---

## Blocked Windows (No Trade Entry)

| Window       | ET Time              | Reason                  |
|--------------|----------------------|-------------------------|
| Rollover     | 16:55 – 18:05 ET     | Spread spike / thin liquidity |
| London open  | 03:00 – 09:00 ET     | Volatile, pre-NY filter  |

**Session Kill:** All open trades closed/flat at 16:55 ET (4H 55min mark).

---

## Setup 1 — Asian Range Break

**Eligible Pairs:** EUR/USD, GBP/USD, AUD/USD  
**Execution Window:** 09:00 – 11:00 ET  

**Rules:**
1. Define Asian range: all 1H bars from 00:00–06:00 ET
2. Range width must be 20–60 pips (filter: too tight = no trade, too wide = no trade)
3. Wait for NY open 09:00 ET
4. **Long:** 1H close breaks above range high → entry at range high
   - SL: range low − 0.5×ATR
   - TP1: entry + range width
   - TP2: entry + 1.618×range width
5. **Short:** 1H close breaks below range low → entry at range low
   - SL: range high + 0.5×ATR
   - TP1: entry − range width
   - TP2: entry − 1.618×range width
6. Score gate must pass (≥5/7)
7. No existing USD-correlated position open

**12-Month Results:**
- EUR/USD: 109 trades, 28% WR (high frequency, lower WR — scalp R profile)
- GBP/USD: 129 trades, 29% WR
- AUD/USD: 75 trades, 21% WR

---

## Setup 2 — NY Open Liquidity Sweep

**Eligible Pairs:** EUR/USD, GBP/USD  
**Execution Window:** 09:00 – 10:30 ET  

**Rules:**
1. Define London session range: all bars 03:00–08:30 ET (high + low)
2. Calculate London mid = (high + low) / 2
3. At NY open (09:00–10:30 ET), look for liquidity sweep:
   - **SHORT:** Bar spikes 5–25 pips above London high AND closes back below → entry at London high
     - SL: bar high + 0.3×ATR
     - TP1: London mid
     - TP2: London low
   - **LONG:** Bar spikes 5–25 pips below London low AND closes back above → entry at London low
     - SL: bar low − 0.3×ATR
     - TP1: London mid
     - TP2: London high
4. Score gate must pass (≥5/7)

**Note:** AUD/USD not eligible (AUD session overlap conflicts with London definition).

**12-Month Results:**
- EUR/USD: 32 trades, 53% WR
- GBP/USD: 38 trades, 50% WR
- AUD/USD: 0 trades (not eligible)

---

## Setup 3 — Previous Day High/Low (PDH/PDL) Sweep

**Eligible Pairs:** EUR/USD, GBP/USD, AUD/USD  
**Execution Window:** 09:00 – 12:00 ET  

**Rules:**
1. Identify previous trading day's high (PDH) and low (PDL)
2. During 09:00–12:00 ET, look for a sweep of either level:
   - **SHORT:** Bar spikes 3–20 pips above PDH AND closes back below PDH
     - Entry: PDH
     - SL: bar high + 0.5×ATR
     - Risk = |entry − SL|
     - TP1: entry − 0.75×risk
     - TP2: PDH − 1.5×ATR
   - **LONG:** Bar spikes 3–20 pips below PDL AND closes back above PDL
     - Entry: PDL
     - SL: bar low − 0.5×ATR
     - Risk = |entry − SL|
     - TP1: entry + 0.75×risk
     - TP2: PDL + 1.5×ATR
3. Score gate must pass (≥5/7)
4. Maximum one Setup 3 signal per pair per day

**12-Month Results:**
- EUR/USD: 45 trades, 73% WR (highest WR of all setups)
- GBP/USD: 45 trades, 78% WR
- AUD/USD: 41 trades, 71% WR

---

## Setup 4 — EMA50 Continuation (REMOVED)

Setup 4 has been permanently removed from all pairs.

**Reason:** Drove losses on USD/JPY (27% WR overall) and contributed to flat/losing months on EUR/USD. The EMA50 touch condition coincides with mid-trend pullbacks that frequently extend further than TP2 could capture before the session kill at 16:55 ET.

---

## Exposure Management

- Treat EUR/USD, GBP/USD, AUD/USD as correlated (all quote in USD)
- Track `usd_quote_open` flag: once one trade is live, no new signals are taken on other pairs until the position closes (SL hit, TP2 hit, or session flat)
- This prevents over-exposure to a single USD directional move

---

## Indicators Required

| Indicator      | Timeframe | Period | Purpose                        |
|----------------|-----------|--------|--------------------------------|
| EMA            | Daily     | 50     | Macro trend filter (Factor 1)  |
| EMA            | 4H        | 50     | Intermediate trend (Factor 2)  |
| DEMA           | 1H        | 9      | Short-term momentum (Factor 3) |
| RSI            | 1H        | 14     | Momentum extreme filter (F4)   |
| ATR            | 1H        | 14     | Volatility / SL sizing         |
| ATR SMA        | 1H        | 20     | ATR ratio filter (Factor 5)    |

DEMA formula: `DEMA(n) = 2 × EMA(n) − EMA(EMA(n))`

---

## 12-Month Verified Performance (May 2025 – May 2026)

| Pair    | Trades | WR   | Net R    | Net P&L   | Max DD  |
|---------|--------|------|----------|-----------|---------|
| EUR/USD | 186    | 43%  | +56.23R  | +$5,497   | -$267   |
| GBP/USD | 212    | 43%  | +69.59R  | +$6,750   | -$204   |
| AUD/USD | 116    | 39%  | +37.20R  | +$3,630   | -$304   |
| **ALL** | **514**| **42%** | **+163.01R** | **+$15,876** | — |

**All 12 months were profitable across the combined portfolio.**  
**Best combined month:** Mar 2026 +$2,121  
**Worst combined month:** May 2025 +$592 (still positive)
