"""US regular-session completion and freshness; never substitute weekdays for holidays."""
from functools import lru_cache
import pandas as pd
import exchange_calendars as xc

@lru_cache(maxsize=1)
def calendar():
    return xc.get_calendar('XNYS')

def clock(now=None):
    stamp=pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz='UTC')
    stamp=stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')
    schedule=calendar().schedule.loc[(stamp-pd.Timedelta(days=21)).date():stamp.date()]
    # Delay allows publication after regular / early close. Daily sources are not ticks.
    done=schedule[schedule['close']+pd.Timedelta(minutes=15)<=stamp]
    if done.empty: raise ValueError('交易日历不可用')
    return {'expected_session':str(done.index[-1].date()),'checked_at':stamp.isoformat(),
            'calendar':'XNYS regular sessions','publication_buffer_minutes':15}

def freshness(as_of,now=None):
    status=clock(now)
    try:
        day=pd.Timestamp(as_of).date().isoformat()
        status.update(fresh=day==status['expected_session'],as_of=day)
    except (ValueError,TypeError): status.update(fresh=False,as_of=None)
    return status


def weekly_freshness(as_of, now=None):
    status = clock(now)
    last = pd.Timestamp(status['expected_session'])
    week_end = last.to_period('W-FRI').end_time.normalize()
    if last != calendar().schedule.loc[last:week_end].index[-1]:
        last = calendar().schedule.loc[:week_end - pd.Timedelta(days=7)].index[-1]
    session = last.date().isoformat()
    status.update(expected_session=session, fresh=as_of == session, as_of=as_of)
    return status

def completed(raw,now=None):
    status=clock(now)
    d=raw.copy();d.index=pd.to_datetime(d.index)
    if d.index.tz is not None: d.index=d.index.tz_convert('America/New_York').tz_localize(None)
    dates=d.index.normalize()
    status['incomplete_rows']=int((dates>pd.Timestamp(status['expected_session'])).sum())
    d=d.loc[dates<=pd.Timestamp(status['expected_session'])]
    return d,status
