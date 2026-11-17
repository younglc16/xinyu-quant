"""Synthetic, deterministic OHLCV for the local demo."""
import hashlib
import os

import numpy as np
import pandas as pd

from market_clock import calendar, clock

SOURCE = '合成演示行情'


def enabled():
    return os.environ.get('XINYU_DEMO') == '1'


def daily(symbol, days):
    end = pd.Timestamp(clock()['expected_session'])
    start = max(calendar().first_session, pd.Timestamp('2016-01-01'))
    dates = calendar().sessions_in_range(start, end)
    seed = int.from_bytes(hashlib.sha256(symbol.upper().encode()).digest()[:8], 'big')
    rng = np.random.default_rng(seed)
    t = np.arange(len(dates))
    values = (21 if symbol == 'VIX' else 50 + seed % 105)
    values *= np.exp(.00015*t + .16*np.sin(t/29) + .08*np.sin(t/8) + rng.normal(0, .012, len(t)))
    opening = values * np.exp(rng.normal(0, .006, len(t)))
    frame = pd.DataFrame({
        'open': opening, 'high': np.maximum(opening, values) * 1.014,
        'low': np.minimum(opening, values) * .986, 'close': values,
        'volume': rng.integers(1_000_000, 6_000_000, len(t)).astype(float),
    }, index=dates).tail(days)
    frame.attrs['data_source'] = SOURCE
    return frame
