from datetime import timedelta
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

def time_features(index):
    return pd.DataFrame({"hour": index.hour, "day": index.day, "dow": index.day_of_week, "month": index.month,
                         "weekend": (index.day_of_week >= 5).astype(int)}, index=index)

def forecast(values, horizon=7, timestamps=None):
    series = pd.Series(values, dtype=float).dropna()
    if len(series) < 48:
        return {"available": False, "reason": "At least 48 hourly records are required to evaluate a forecast.", "points": [], "metrics": None}
    if timestamps is None:
        idx = pd.date_range(end=pd.Timestamp.utcnow().floor("h"), periods=len(series), freq="h")
    else:
        idx = pd.DatetimeIndex(pd.to_datetime(timestamps))
        if len(idx) != len(series):
            return {"available": False, "reason": "Timestamp and reading counts do not match.", "points": [], "metrics": None}
    X = time_features(idx)
    X["lag_1"] = series.shift(1).to_numpy()
    X["lag_24"] = series.shift(24).to_numpy()
    X["rolling_24"] = series.shift(1).rolling(24).mean().to_numpy()
    data = X.assign(target=series.to_numpy()).dropna()
    split = max(24, int(len(data) * .8))
    if len(data) - split < 12:
        return {"available": False, "reason": "Not enough held-out observations for a meaningful evaluation.", "points": [], "metrics": None}
    model = RandomForestRegressor(n_estimators=100, max_depth=8, min_samples_leaf=2, random_state=42, n_jobs=1)
    model.fit(data.drop(columns="target").iloc[:split], data.target.iloc[:split])
    actual = data.target.iloc[split:]
    predicted = model.predict(data.drop(columns="target").iloc[split:])
    metrics = {"mae": round(float(mean_absolute_error(actual, predicted)), 3), "rmse": round(float(np.sqrt(mean_squared_error(actual, predicted))), 3), "r2": round(float(r2_score(actual, predicted)), 3)}
    fitted = RandomForestRegressor(n_estimators=100, max_depth=8, min_samples_leaf=2, random_state=42, n_jobs=1)
    fitted.fit(data.drop(columns="target"), data.target)
    latest = series.iloc[-1]
    future = []
    interval = pd.Series(idx).diff().dropna().median()
    if pd.isna(interval) or interval <= pd.Timedelta(0):
        interval = pd.Timedelta(hours=1)
    for i in range(1, min(horizon, 30) + 1):
        ts = idx[-1] + interval * i
        row = time_features(pd.DatetimeIndex([ts]))
        row["lag_1"] = latest
        row["lag_24"] = float(series.iloc[-24]) if len(series) >= 24 else latest
        row["rolling_24"] = float(series.tail(24).mean())
        val = max(0, float(fitted.predict(row)[0]))
        future.append({"timestamp": ts.isoformat(), "value": round(val, 3)})
        latest = val
    return {"available": True, "method": "Random Forest with calendar, lag and rolling features", "training_records": len(data), "test_records": len(actual), "sampling_interval_seconds": float(interval.total_seconds()), "metrics": metrics, "points": future}

def detect_anomalies(records):
    if len(records) < 24:
        return []
    frame = pd.DataFrame(records)
    baseline = frame.value.rolling(24, min_periods=12).median()
    spread = (frame.value - baseline).abs().rolling(24, min_periods=12).median()
    threshold = np.maximum(3 * 1.4826 * spread, baseline.abs() * .35)
    mask = (frame.value - baseline).abs() > threshold
    rows = []
    for i in np.flatnonzero(mask.fillna(False).to_numpy())[-100:]:
        deviation = float(frame.value.iloc[i] - baseline.iloc[i])
        rows.append({"timestamp": str(frame.timestamp.iloc[i]), "observed": round(float(frame.value.iloc[i]), 3), "baseline": round(float(baseline.iloc[i]), 3), "deviation": round(deviation, 3), "severity": "high" if abs(deviation) > 2 * float(threshold.iloc[i]) else "moderate", "method": "24-hour rolling median and MAD threshold", "explanation": "A statistical deviation from recent readings. Investigate context; this does not by itself establish wastage."})
    return rows
