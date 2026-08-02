from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


SHAPE_NAMES = {
    "steady_rise": "持续上行",
    "choppy_rise": "震荡上行",
    "sideways": "区间震荡",
    "choppy_fall": "震荡下行",
    "steady_fall": "持续下行",
}


@dataclass(frozen=True)
class AnalogConfig:
    horizon_days: int = 5
    lookback_days: int = 20
    analog_count: int = 50
    min_analog_count: int = 30
    validation_origins: int = 180
    calibration_neighbor_count: int = 60
    interval_coverage: float = 0.80
    sideways_threshold: float = 0.01
    min_market_improvement: float = 0.01
    force_market_conditioning: bool = False

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "AnalogConfig":
        values = settings.get("prediction", {})
        return cls(**{
            field: values.get(field, getattr(cls(), field))
            for field in cls.__dataclass_fields__
        })

    def validate(self) -> None:
        if self.horizon_days < 2:
            raise ValueError("预测天数至少为2个交易日。")
        if self.lookback_days < 10:
            raise ValueError("历史形态窗口至少为10个交易日。")
        if self.analog_count < self.min_analog_count:
            raise ValueError("相似样本数量不能小于最低样本数量。")
        if not 0.5 <= self.interval_coverage < 1:
            raise ValueError("概率区间覆盖率必须位于[0.5, 1)之间。")


@dataclass
class PreparedSeries:
    dates: np.ndarray
    stock_close: np.ndarray
    market_close: np.ndarray | None
    states: np.ndarray


@dataclass
class ForecastSample:
    median_path: np.ndarray
    raw_lower: np.ndarray
    raw_upper: np.ndarray
    stock_paths: np.ndarray
    market_median_path: np.ndarray | None
    analog_origins: np.ndarray
    analog_distances: np.ndarray


def _clean_bars(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    required = {"trade_date", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{value_name}行情缺少字段: {sorted(missing)}")
    cleaned = frame[["trade_date", "close"]].copy()
    cleaned["trade_date"] = pd.to_datetime(cleaned["trade_date"]).dt.normalize()
    cleaned["close"] = pd.to_numeric(cleaned["close"], errors="coerce")
    cleaned = (
        cleaned.dropna()
        .loc[lambda item: item["close"] > 0]
        .drop_duplicates("trade_date", keep="last")
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    if cleaned.empty:
        raise ValueError(f"{value_name}行情为空。")
    return cleaned


def _clean_ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", "open", "high", "low", "close"]
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f"个股行情缺少K线字段: {sorted(missing)}")
    cleaned = frame[columns].copy()
    cleaned["trade_date"] = pd.to_datetime(
        cleaned["trade_date"], errors="coerce"
    ).dt.normalize()
    for column in columns[1:]:
        cleaned[column] = pd.to_numeric(
            cleaned[column], errors="coerce"
        )
    cleaned = (
        cleaned.replace([np.inf, -np.inf], np.nan)
        .dropna()
        .loc[lambda item: (
            (item[["open", "high", "low", "close"]] > 0).all(axis=1)
            & (
                item["high"]
                >= item[["open", "close", "low"]].max(axis=1)
            )
            & (
                item["low"]
                <= item[["open", "close", "high"]].min(axis=1)
            )
        )]
        .drop_duplicates("trade_date", keep="last")
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    if cleaned.empty:
        raise ValueError("个股K线行情为空。")
    return cleaned


def _build_analog_forecast_candles(
    stock_bars: pd.DataFrame,
    series: PreparedSeries,
    sample: ForecastSample,
    config: AnalogConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    aligned = pd.DataFrame({
        "trade_date": pd.to_datetime(series.dates).normalize(),
    }).merge(
        _clean_ohlc(stock_bars),
        on="trade_date",
        how="left",
        validate="one_to_one",
    )
    if aligned[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("共同历史中存在无法匹配的个股K线。")
    representative_position = int(np.argmin(np.sqrt(np.mean(
        (sample.stock_paths - sample.median_path[None, :]) ** 2,
        axis=1,
    ))))
    representative_origin = int(
        sample.analog_origins[representative_position]
    )
    origin_close = float(aligned.iloc[representative_origin]["close"])
    base_price = float(series.stock_close[-1])
    candles: list[dict[str, Any]] = []
    for index in range(config.horizon_days):
        close_price = base_price * (
            1.0 + sample.median_path[index]
        )
        source = aligned.iloc[representative_origin + index + 1]
        source_close_scaled = (
            base_price * float(source["close"]) / origin_close
        )
        close_alignment = close_price / source_close_scaled
        open_price = (
            base_price * float(source["open"]) / origin_close
            * close_alignment
        )
        high_price = (
            base_price * float(source["high"]) / origin_close
            * close_alignment
        )
        low_price = (
            base_price * float(source["low"]) / origin_close
            * close_alignment
        )
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)
        candles.append({
            "day": index + 1,
            "label": f"T+{index + 1}",
            "open": float(open_price),
            "high": float(high_price),
            "low": float(low_price),
            "close": float(close_price),
            "derivation": "analog_medoid_shape_on_median_close",
            "representative_origin_date": (
                aligned.iloc[representative_origin]["trade_date"]
                .date()
                .isoformat()
            ),
        })
    recent = [
        {
            "trade_date": row.trade_date.date().isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        }
        for row in aligned.tail(config.lookback_days).itertuples()
    ]
    return candles, recent


def _state_row(
    stock_returns: np.ndarray,
    market_returns: np.ndarray | None,
    origin: int,
    lookback: int,
) -> np.ndarray:
    stock_window = stock_returns[origin - lookback + 1: origin + 1]
    components = [
        stock_window,
        np.array([
            np.sum(stock_window[-5:]),
            np.sum(stock_window),
            np.std(stock_window, ddof=1),
        ]),
    ]
    if market_returns is not None:
        market_window = market_returns[origin - lookback + 1: origin + 1]
        correlation = (
            np.corrcoef(stock_window, market_window)[0, 1]
            if np.std(stock_window) > 0 and np.std(market_window) > 0
            else 0.0
        )
        market_variance = np.var(market_window, ddof=1)
        beta = (
            np.cov(stock_window, market_window, ddof=1)[0, 1]
            / market_variance
            if market_variance > 0
            else 0.0
        )
        components.extend([
            market_window,
            stock_window - market_window,
            np.array([
                np.sum(market_window[-5:]),
                np.sum(market_window),
                np.std(market_window, ddof=1),
                correlation,
                beta,
            ]),
        ])
    return np.concatenate(components)


def _prepare_series(
    stock_bars: pd.DataFrame,
    market_bars: pd.DataFrame | None,
    config: AnalogConfig,
) -> PreparedSeries:
    stock = _clean_bars(stock_bars, "个股")
    if market_bars is None:
        aligned = stock.rename(columns={"close": "stock_close"})
        market_close = None
    else:
        market = _clean_bars(market_bars, "指数").rename(
            columns={"close": "market_close"}
        )
        aligned = stock.rename(columns={"close": "stock_close"}).merge(
            market, on="trade_date", how="inner", validate="one_to_one"
        )
        market_close = aligned["market_close"].to_numpy(dtype=float)
    stock_close = aligned["stock_close"].to_numpy(dtype=float)
    minimum_rows = config.lookback_days + config.horizon_days + config.min_analog_count
    if len(aligned) < minimum_rows:
        raise ValueError(
            f"共同历史仅{len(aligned)}条，至少需要{minimum_rows}条。"
        )
    stock_returns = np.empty(len(stock_close), dtype=float)
    stock_returns[0] = np.nan
    stock_returns[1:] = np.diff(np.log(stock_close))
    market_returns = None
    if market_close is not None:
        market_returns = np.empty(len(market_close), dtype=float)
        market_returns[0] = np.nan
        market_returns[1:] = np.diff(np.log(market_close))
    states = np.full((len(aligned), _state_row(
        stock_returns,
        market_returns,
        config.lookback_days,
        config.lookback_days,
    ).size), np.nan)
    for origin in range(config.lookback_days, len(aligned)):
        states[origin] = _state_row(
            stock_returns, market_returns, origin, config.lookback_days
        )
    return PreparedSeries(
        dates=aligned["trade_date"].to_numpy(),
        stock_close=stock_close,
        market_close=market_close,
        states=states,
    )


def _candidate_origins(
    series: PreparedSeries,
    origin: int,
    config: AnalogConfig,
) -> np.ndarray:
    latest_candidate = origin - config.horizon_days
    candidates = np.arange(config.lookback_days, latest_candidate + 1)
    if candidates.size == 0:
        return candidates
    valid = np.isfinite(series.states[candidates]).all(axis=1)
    return candidates[valid]


def _forecast_at(
    series: PreparedSeries,
    origin: int,
    config: AnalogConfig,
) -> ForecastSample:
    candidates = _candidate_origins(series, origin, config)
    if len(candidates) < config.min_analog_count:
        raise ValueError(
            f"可用历史相似样本仅{len(candidates)}条，"
            f"至少需要{config.min_analog_count}条。"
        )
    candidate_states = series.states[candidates]
    target = series.states[origin]
    median = np.nanmedian(candidate_states, axis=0)
    mad = np.nanmedian(np.abs(candidate_states - median), axis=0) * 1.4826
    standard_deviation = np.nanstd(candidate_states, axis=0, ddof=1)
    scale = np.where(mad > 1e-8, mad, standard_deviation)
    scale = np.where(scale > 1e-8, scale, 1.0)
    distances = np.sqrt(np.mean(((candidate_states - target) / scale) ** 2, axis=1))
    take = min(config.analog_count, len(candidates))
    nearest_positions = np.argsort(distances, kind="stable")[:take]
    nearest = candidates[nearest_positions]
    steps = np.arange(1, config.horizon_days + 1)
    future_indexes = nearest[:, None] + steps[None, :]
    stock_paths = (
        series.stock_close[future_indexes]
        / series.stock_close[nearest, None]
        - 1.0
    )
    alpha = (1.0 - config.interval_coverage) / 2.0
    market_median = None
    if series.market_close is not None:
        market_paths = (
            series.market_close[future_indexes]
            / series.market_close[nearest, None]
            - 1.0
        )
        market_median = np.median(market_paths, axis=0)
    return ForecastSample(
        median_path=np.median(stock_paths, axis=0),
        raw_lower=np.quantile(stock_paths, alpha, axis=0),
        raw_upper=np.quantile(stock_paths, 1.0 - alpha, axis=0),
        stock_paths=stock_paths,
        market_median_path=market_median,
        analog_origins=nearest,
        analog_distances=distances[nearest_positions],
    )


def _shape_key(path: np.ndarray, threshold: float) -> str:
    final_return = float(path[-1])
    daily_moves = np.diff(np.concatenate(([0.0], path)))
    if final_return > threshold:
        return "steady_rise" if np.mean(daily_moves > 0) >= 0.6 else "choppy_rise"
    if final_return < -threshold:
        return "steady_fall" if np.mean(daily_moves < 0) >= 0.6 else "choppy_fall"
    return "sideways"


def _shape_distribution(paths: np.ndarray, threshold: float) -> dict[str, float]:
    counts = {key: 0 for key in SHAPE_NAMES}
    for path in paths:
        counts[_shape_key(path, threshold)] += 1
    total = float(len(paths))
    return {key: value / total for key, value in counts.items()}


def _walk_forward(
    series: PreparedSeries,
    config: AnalogConfig,
) -> dict[str, Any]:
    earliest = config.lookback_days + config.horizon_days + config.min_analog_count
    latest = len(series.dates) - config.horizon_days - 1
    origins = np.arange(earliest, latest + 1)
    if len(origins) > config.validation_origins:
        origins = origins[-config.validation_origins:]
    predictions: list[np.ndarray] = []
    actuals: list[np.ndarray] = []
    raw_shapes: list[list[float]] = []
    actual_shapes: list[str] = []
    kept_origins: list[int] = []
    shape_keys = list(SHAPE_NAMES)
    for origin in origins:
        try:
            sample = _forecast_at(series, int(origin), config)
        except ValueError:
            continue
        future = (
            series.stock_close[origin + 1: origin + config.horizon_days + 1]
            / series.stock_close[origin]
            - 1.0
        )
        distribution = _shape_distribution(
            sample.stock_paths, config.sideways_threshold
        )
        predictions.append(sample.median_path)
        actuals.append(future)
        raw_shapes.append([distribution[key] for key in shape_keys])
        actual_shapes.append(_shape_key(future, config.sideways_threshold))
        kept_origins.append(int(origin))
    if len(predictions) < 30:
        raise ValueError("历史滚动验证样本不足30次，拒绝输出概率预测。")
    predicted = np.asarray(predictions)
    actual = np.asarray(actuals)
    raw_shape_array = np.asarray(raw_shapes)
    residuals = np.abs(actual - predicted)
    calibration_cut = max(20, int(len(predicted) * 0.7))
    calibration_residuals = residuals[:calibration_cut]
    evaluation_residuals = residuals[calibration_cut:]
    calibration_radius = np.quantile(
        calibration_residuals,
        config.interval_coverage,
        axis=0,
        method="higher",
    )
    evaluation_coverage = (
        float(np.mean(evaluation_residuals <= calibration_radius))
        if len(evaluation_residuals)
        else float("nan")
    )
    full_radius = np.quantile(
        residuals,
        config.interval_coverage,
        axis=0,
        method="higher",
    )
    predicted_final = predicted[:, -1]
    actual_final = actual[:, -1]
    direction_accuracy = float(np.mean(
        np.sign(predicted_final) == np.sign(actual_final)
    ))
    positive_rate = float(np.mean(actual_final > 0))
    negative_rate = float(np.mean(actual_final < 0))
    direction_baseline = max(positive_rate, negative_rate)
    naive_mae = float(np.mean(np.abs(actual_final)))
    model_mae = float(np.mean(np.abs(predicted_final - actual_final)))
    return {
        "origins": np.asarray(kept_origins),
        "predicted": predicted,
        "actual": actual,
        "raw_shape_probabilities": raw_shape_array,
        "actual_shapes": actual_shapes,
        "calibration_radius": full_radius,
        "metrics": {
            "sample_count": int(len(predicted)),
            "direction_accuracy": direction_accuracy,
            "direction_baseline_accuracy": direction_baseline,
            "direction_edge": direction_accuracy - direction_baseline,
            "mae_final": model_mae,
            "naive_mae_final": naive_mae,
            "mae_skill": 1.0 - model_mae / max(naive_mae, 1e-8),
            "median_error_final": float(np.median(
                np.abs(predicted_final - actual_final)
            )),
            "interval_target_coverage": config.interval_coverage,
            "interval_evaluation_coverage": evaluation_coverage,
            "evaluation_sample_count": int(len(evaluation_residuals)),
        },
    }


def _calibrated_shape_probabilities(
    current_raw: dict[str, float],
    validation: dict[str, Any],
    config: AnalogConfig,
) -> tuple[dict[str, float], int]:
    keys = list(SHAPE_NAMES)
    target = np.array([current_raw[key] for key in keys])
    historical = validation["raw_shape_probabilities"]
    distances = np.sqrt(np.mean((historical - target) ** 2, axis=1))
    take = min(config.calibration_neighbor_count, len(distances))
    nearest = np.argsort(distances, kind="stable")[:take]
    counts = {key: 1.0 for key in keys}
    for position in nearest:
        counts[validation["actual_shapes"][int(position)]] += 1.0
    denominator = sum(counts.values())
    return {key: counts[key] / denominator for key in keys}, take


def _model_result(
    stock_bars: pd.DataFrame,
    market_bars: pd.DataFrame | None,
    config: AnalogConfig,
) -> tuple[PreparedSeries, ForecastSample, dict[str, Any]]:
    series = _prepare_series(stock_bars, market_bars, config)
    validation = _walk_forward(series, config)
    current = _forecast_at(series, len(series.dates) - 1, config)
    return series, current, validation


def _market_value_score(
    joint_metrics: dict[str, float],
    stock_metrics: dict[str, float],
) -> float:
    baseline_mae = max(float(stock_metrics["mae_final"]), 1e-8)
    mae_improvement = (
        float(stock_metrics["mae_final"]) - float(joint_metrics["mae_final"])
    ) / baseline_mae
    direction_improvement = (
        float(joint_metrics["direction_accuracy"])
        - float(stock_metrics["direction_accuracy"])
    )
    return float(mae_improvement + direction_improvement)


def generate_stock_forecast(
    *,
    code: str,
    name: str,
    stock_bars: pd.DataFrame,
    benchmarks: dict[str, tuple[str, pd.DataFrame]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Generate a calibrated, walk-forward-tested forecast artifact."""
    config = AnalogConfig.from_settings(settings)
    config.validate()
    stock_series, stock_current, stock_validation = _model_result(
        stock_bars, None, config
    )
    stock_latest_date = pd.to_datetime(
        stock_bars["trade_date"]
    ).max().date()
    benchmark_results: list[dict[str, Any]] = []
    joint_models: dict[str, tuple[PreparedSeries, ForecastSample, dict[str, Any]]] = {}
    for benchmark_code, (benchmark_name, benchmark_bars) in benchmarks.items():
        benchmark_latest_date = pd.to_datetime(
            benchmark_bars["trade_date"]
        ).max().date()
        if benchmark_latest_date < stock_latest_date:
            benchmark_results.append({
                "code": benchmark_code,
                "name": benchmark_name,
                "usable": False,
                "reason": (
                    f"指数行情仅到 {benchmark_latest_date.isoformat()}，"
                    f"落后于个股 {stock_latest_date.isoformat()}"
                ),
            })
            continue
        try:
            joint = _model_result(stock_bars, benchmark_bars, config)
        except ValueError as exc:
            benchmark_results.append({
                "code": benchmark_code,
                "name": benchmark_name,
                "usable": False,
                "reason": str(exc),
            })
            continue
        joint_models[benchmark_code] = joint
        metrics = joint[2]["metrics"]
        score = _market_value_score(metrics, stock_validation["metrics"])
        benchmark_results.append({
            "code": benchmark_code,
            "name": benchmark_name,
            "usable": True,
            "value_score": score,
            **metrics,
        })
    usable = [item for item in benchmark_results if item["usable"]]
    best = max(usable, key=lambda item: item["value_score"]) if usable else None
    use_market = bool(
        best
        and (
            config.force_market_conditioning
            or best["value_score"] >= config.min_market_improvement
        )
    )
    if use_market and best is not None:
        selected_code = str(best["code"])
        selected_name = str(best["name"])
        series, current, validation = joint_models[selected_code]
        model_mode = "market_conditioned"
        market_value_conclusion = "历史走查显示大盘信息有增益，已纳入预测。"
    else:
        selected_code = None
        selected_name = None
        series, current, validation = (
            stock_series, stock_current, stock_validation
        )
        model_mode = "stock_only"
        market_value_conclusion = (
            "历史走查未证明大盘信息有稳定增益，本次不强行纳入预测。"
        )
    raw_shapes = _shape_distribution(
        current.stock_paths, config.sideways_threshold
    )
    calibrated_shapes, calibration_count = _calibrated_shape_probabilities(
        raw_shapes, validation, config
    )
    radius = validation["calibration_radius"]
    lower = current.median_path - radius
    upper = current.median_path + radius
    base_price = float(series.stock_close[-1])
    horizon = list(range(1, config.horizon_days + 1))
    forecast_path = [
        {
            "day": day,
            "median_return": float(current.median_path[index]),
            "lower_return": float(lower[index]),
            "upper_return": float(upper[index]),
            "median_price": float(base_price * (1.0 + current.median_path[index])),
            "lower_price": float(base_price * (1.0 + lower[index])),
            "upper_price": float(base_price * (1.0 + upper[index])),
            "market_median_return": (
                None
                if current.market_median_path is None
                else float(current.market_median_path[index])
            ),
        }
        for index, day in enumerate(horizon)
    ]
    forecast_candles, recent_history = _build_analog_forecast_candles(
        stock_bars,
        series,
        current,
        config,
    )
    metrics = validation["metrics"]
    coverage_floor = config.interval_coverage - 0.10
    reliability_checks = {
        "enough_validation_samples": metrics["sample_count"] >= 100,
        "beats_direction_baseline": metrics["direction_edge"] > 0,
        "beats_zero_return_mae": metrics["mae_skill"] > 0,
        "interval_coverage_acceptable": (
            metrics["interval_evaluation_coverage"] >= coverage_floor
        ),
    }
    passed_checks = sum(reliability_checks.values())
    if passed_checks == len(reliability_checks):
        reliability_status = "limited"
        reliability_message = (
            "已通过最低历史可靠性门槛，但仍属于研究型概率，不代表未来收益。"
        )
    else:
        reliability_status = "rejected"
        check_names = {
            "enough_validation_samples": "滚动验证次数不足",
            "beats_direction_baseline": "方向命中未超过简单基线",
            "beats_zero_return_mae": "误差未优于零收益基线",
            "interval_coverage_acceptable": "概率区间覆盖不足",
        }
        failed_names = [
            check_names[key]
            for key, passed in reliability_checks.items()
            if not passed
        ]
        reliability_message = (
            "未通过最低历史可靠性门槛，不应据此形成交易判断。"
            f"未通过项：{'、'.join(failed_names)}。"
        )
    return {
        "schema_version": 1,
        "engine": settings["prediction"].get(
            "engine", "historical_joint_analog_v1"
        ),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "code": code,
        "name": name,
        "input": {
            "adjust_type": "qfq",
            "as_of_trade_date": pd.Timestamp(series.dates[-1]).date().isoformat(),
            "history_rows": int(len(series.dates)),
            "base_price": base_price,
            "lookback_days": config.lookback_days,
            "horizon_days": config.horizon_days,
            "analog_count": int(len(current.stock_paths)),
        },
        "selection": {
            "mode": model_mode,
            "benchmark_code": selected_code,
            "benchmark_name": selected_name,
            "market_value_conclusion": market_value_conclusion,
            "minimum_value_score": config.min_market_improvement,
            "benchmark_evaluations": benchmark_results,
        },
        "probability": {
            "method": "walk_forward_local_calibration_v1",
            "calibration_sample_count": calibration_count,
            "shape_probabilities": {
                SHAPE_NAMES[key]: float(calibrated_shapes[key])
                for key in SHAPE_NAMES
            },
            "raw_analog_shape_frequencies": {
                SHAPE_NAMES[key]: float(raw_shapes[key])
                for key in SHAPE_NAMES
            },
        },
        "validation": metrics,
        "reliability": {
            "status": reliability_status,
            "message": reliability_message,
            "checks": reliability_checks,
            "passed_check_count": passed_checks,
            "total_check_count": len(reliability_checks),
        },
        "forecast_path": forecast_path,
        "forecast_candles": forecast_candles,
        "recent_history": recent_history,
        "controls": {
            "research_only": True,
            "auto_trading": False,
            "probabilities_are_calibrated": True,
            "interval_is_conformal_style": True,
        },
    }
