"""
Database utilities for saving valuation predictions.

This module stores predictions in the valuation_results table, which is the
database source of truth for all model outputs.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from invest.data.db import get_connection


def get_db_connection(db_path=None):
    """Get database connection. db_path accepted for backward compatibility but ignored."""
    return get_connection()


def save_classic_prediction(
    conn,
    model_name: str,
    ticker: str,
    fair_value: float,
    current_price: float,
    margin_of_safety: Optional[float] = None,
    upside_pct: Optional[float] = None,
    suitable: bool = True,
    failure_reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    prediction_date: Optional[datetime] = None,
    confidence: Optional[float] = None,
    error_message: Optional[str] = None
) -> None:
    """Save classic valuation prediction to database."""
    if prediction_date is None:
        prediction_date = datetime.now()

    if margin_of_safety is None and current_price and current_price > 0:
        margin_of_safety = (fair_value - current_price) / current_price

    if upside_pct is None and current_price and current_price > 0:
        upside_pct = ((fair_value / current_price) - 1) * 100

    details_json = json.dumps(details) if details else None

    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO valuation_results (
                ticker, model_name, timestamp,
                fair_value, current_price, margin_of_safety, upside_pct,
                suitable, error_message, failure_reason, details_json, confidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, model_name) DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                fair_value = EXCLUDED.fair_value,
                current_price = EXCLUDED.current_price,
                margin_of_safety = EXCLUDED.margin_of_safety,
                upside_pct = EXCLUDED.upside_pct,
                suitable = EXCLUDED.suitable,
                error_message = EXCLUDED.error_message,
                failure_reason = EXCLUDED.failure_reason,
                details_json = EXCLUDED.details_json,
                confidence = EXCLUDED.confidence
        ''', (
            ticker,
            model_name,
            prediction_date,
            fair_value,
            current_price,
            margin_of_safety,
            upside_pct,
            suitable,
            error_message,
            failure_reason,
            details_json,
            confidence
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f'Failed to save prediction for {ticker} ({model_name}): {e}')


def save_nn_prediction(
    conn,
    model_name: str,
    ticker: str,
    fair_value: float,
    current_price: float,
    margin_of_safety: float,
    upside_pct: float,
    confidence: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
    suitable: bool = True,
    error_message: Optional[str] = None,
    failure_reason: Optional[str] = None,
    prediction_date: Optional[datetime] = None
) -> None:
    """Save neural network prediction to database."""
    if prediction_date is None:
        prediction_date = datetime.now()
    details_json = json.dumps(details) if details else None

    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO valuation_results (
                ticker, model_name, timestamp,
                fair_value, current_price, margin_of_safety, upside_pct,
                suitable, error_message, failure_reason, details_json, confidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, model_name) DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                fair_value = EXCLUDED.fair_value,
                current_price = EXCLUDED.current_price,
                margin_of_safety = EXCLUDED.margin_of_safety,
                upside_pct = EXCLUDED.upside_pct,
                suitable = EXCLUDED.suitable,
                error_message = EXCLUDED.error_message,
                failure_reason = EXCLUDED.failure_reason,
                details_json = EXCLUDED.details_json,
                confidence = EXCLUDED.confidence
        ''', (
            ticker,
            model_name,
            prediction_date,
            fair_value,
            current_price,
            margin_of_safety,
            upside_pct,
            suitable,
            error_message,
            failure_reason,
            details_json,
            confidence
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f'Failed to save NN prediction for {ticker} ({model_name}): {e}')


def get_latest_predictions(
    conn,
    ticker: str,
    model_name: Optional[str] = None
) -> Dict[str, Any]:
    """Get latest predictions for a ticker."""
    cursor = conn.cursor()

    results = {}

    query = '''
        SELECT model_name, fair_value, margin_of_safety, upside_pct,
               suitable, error_message, failure_reason, details_json,
               confidence, timestamp
        FROM valuation_results
        WHERE ticker = %s
    '''
    params = [ticker]

    if model_name:
        query += ' AND model_name = %s'
        params.append(model_name)

    query += ' ORDER BY timestamp DESC'

    cursor.execute(query, params)
    for row in cursor.fetchall():
        name, fair_value, margin, upside, suitable, error_message, reason, details_json, confidence, timestamp = row
        if name in results:
            continue
        details = details_json if isinstance(details_json, dict) else (json.loads(details_json) if details_json else {})
        results[name] = {
            'fair_value': fair_value,
            'margin_of_safety': margin,
            'upside_pct': upside,
            'confidence': confidence,
            'suitable': bool(suitable),
            'error_message': error_message,
            'failure_reason': reason,
            'details': details,
            'timestamp': timestamp
        }

    return results
