"""Regression checks for stalled providers, partial responses and manual recovery."""
import sys
import tempfile
import os
import threading
import time
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TEMP = tempfile.TemporaryDirectory()
os.environ['XINYU_DATA_DIR'] = TEMP.name
import data_provider as dp
import market_pulse as pulse
import v3_store as store
import v3_api as api


def wait_for(predicate):
    end = time.monotonic() + 2
    while not predicate():
        if time.monotonic() > end:
            raise AssertionError('background task did not finish')
        threading.Event().wait(.01)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        pulse._ITEMS.clear()
        dp._TTL_CACHE.clear()
        self.today = datetime.now(pulse.NY).date()

    def test_fast_vix_is_returned_while_qqq_is_blocked_and_refresh_is_coalesced(self):
        release = threading.Event()
        entered = threading.Event()

        def slow(*_):
            entered.set()
            release.wait(2)
            return {'as_of': self.today.isoformat(), 'temperature': 50}

        with patch.object(pulse, '_qqq', side_effect=slow) as q, \
             patch.object(pulse, '_vix', return_value={'as_of': self.today.isoformat(), 'value': 18}), \
             patch.object(store, 'snapshot', return_value=None), \
             patch.object(store, 'put_snapshot'):
            try:
                start = time.monotonic()
                first = pulse.current()
                self.assertLess(time.monotonic() - start, .2)
                self.assertTrue(first['loading'])
                self.assertTrue(entered.wait(1))
                wait_for(lambda: pulse._ITEMS['vix']['state'] == 'ready')
                partial = pulse.current()
                self.assertEqual(partial['vix']['value'], 18)
                self.assertIsNone(partial['qqq'])
                pulse.current(force=True)
                self.assertEqual(q.call_count, 1)
            finally:
                release.set()
                wait_for(lambda: all(i['state'] != 'loading' for i in pulse._ITEMS.values()))
            self.assertFalse(pulse.current()['loading'])

    def test_failure_preserves_dated_snapshot_and_recomputes_freshness(self):
        old = {'as_of': (self.today - timedelta(days=12)).isoformat(),
               'temperature': 50, 'value': 18, 'fresh': True,
               'fetched_at': '2000-01-01T00:00:00+00:00'}
        with patch.object(store, 'snapshot', return_value=old), \
             patch.object(pulse, '_qqq', side_effect=TimeoutError), \
             patch.object(pulse, '_vix', side_effect=TimeoutError):
            pulse.current()
            wait_for(lambda: all(i['state'] == 'error' for i in pulse._ITEMS.values()))
            result = pulse.current()
            self.assertFalse(result['qqq']['fresh'])
            self.assertTrue(result['qqq']['refresh_failed'])
            self.assertEqual(result['qqq']['fetched_at'], old['fetched_at'])
            self.assertEqual(len(result['errors']), 2)

    def test_manual_retry_evicts_failed_reads_but_keeps_successful_reads(self):
        now = datetime.now()
        dp._TTL_CACHE.update({'daily_tv:QQQ:220': (now, None),
                              'daily_tv:NVDA:320': (now, None),
                              'daily:QQQ:220': (now, 'real cached result')})
        dp.clear_failed_cache('QQQ')
        self.assertNotIn('daily_tv:QQQ:220', dp._TTL_CACHE)
        self.assertIn('daily_tv:NVDA:320', dp._TTL_CACHE)
        self.assertIn('daily:QQQ:220', dp._TTL_CACHE)

    def test_failed_cache_expires_earlier_than_successful_data(self):
        old = datetime.now() - timedelta(seconds=61)
        dp._TTL_CACHE['daily_tv:QQQ:220'] = (old, None)
        self.assertEqual(dp._cached('daily_tv:QQQ:220', 600, lambda: 'recovered'), 'recovered')

    def test_concurrent_requests_share_one_provider_read(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def producer():
            calls.append(1)
            entered.set()
            release.wait(1)
            return 'same result'
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(dp._cached, 'test', 300, producer) for _ in range(3)]
            self.assertTrue(entered.wait(1))
            release.set()
            self.assertEqual([f.result() for f in futures], ['same result'] * 3)
        self.assertEqual(len(calls), 1)

    def test_old_cached_trade_signal_is_not_presented_as_current(self):
        day = (self.today - timedelta(days=12)).isoformat()
        cache = {'confluence': {'as_of': day, 'stale': False, 'state': 'long',
                                'latest_signal': {'direction': 'long'}}}
        api.JOBS['NVDA:daily:QQQ'] = {'state': 'error', 'updated': time.monotonic(), 'error': 'offline'}
        with patch.object(store, 'snapshot', return_value=cache):
            result = api.analysis('NVDA')
        self.assertEqual(result['data']['confluence']['state'], 'stale')
        self.assertIsNone(result['data']['confluence']['latest_signal'])


if __name__ == '__main__':
    unittest.main()
