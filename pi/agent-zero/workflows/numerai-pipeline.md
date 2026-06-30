# Workflow: Numerai ML Pipeline

## Trigger
Schedule: Weekly (Numerai tournament rounds close Saturday)
And on-demand via `/numerai` command

## Overview
Numerai is a hedge fund that hosts a tournament. Participants train ML models on encrypted data and submit predictions. Top models earn payouts.

## Pipeline Steps

### 1. Fetch Latest Tournament Data
```bash
kaggle datasets download svendaj/numerai-latest-tournament-data
```
Data includes:
- `train.parquet` — training features + targets
- `validation.parquet` — validation set
- `live.parquet` — current tournament data (prediction target)
- `example_predictions.csv` — format reference

### 2. Feature Engineering
- Numerai provides `feature_*` columns (encrypted)
- Additional features from yfinance (for Numerai Signals)
- Kaggle dataset: `code1110/yfinance-stock-price-data-for-numerai-signals`

### 3. Model Training
Using the local ML stack:
```python
# Options:
# - LightGBM (fast, good for tabular)
# - XGBoost (alternative)
# - PyTorch MLP (deep learning)
# - Ensemble of multiple models
```

### 4. Prediction
Generate predictions for:
- **Core tournament** — `prediction` column (classification target)
- **Numerai Signals** — stock market signals (if applicable)

### 5. Submit
```bash
kaggle competitions submit -c numerai -f predictions.csv -m "Auto submit"
```

### 6. Monitor Performance
- Track correlation score on validation
- Monitor live performance on leaderboard
- Log all submissions for analysis

## Integration with SMC Trading
- Top Numerai predictions → watchlist for SMC analysis
- High-conviction signals get priority in TradingView workflow
- Correlation between Numerai signals and SMC setups → increased position confidence

## Tools Used
- Kaggle API (authenticated as `lungelo-luda`)
- Python ML stack (LightGBM/XGBoost/sklearn)
- A0 CLI for data processing
- Agent Zero for analysis and report generation

## Checkpoints
1. **Data integrity check** — verify downloaded data before training
2. **Model validation** — check correlation score before submission
3. **Submission confirmation** — verify on Numerai website

## Push Right
Data download, feature engineering, training, and submission run automated. User only reviews performance metrics.
