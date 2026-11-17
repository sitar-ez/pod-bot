"""How long to wait before Rory's next run: every 2 hours during work hours (9, 11, 1, 3), otherwise until
9am Eastern. GitHub jobs can last at most 6 hours, so long waits are split into hops."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import settings

MAX_WAIT = 5 * 3600 + 30 * 60

now = datetime.now(ZoneInfo(settings.WORK_TIMEZONE))
start = now.replace(hour=settings.WORK_START_HOUR, minute=1, second=0, microsecond=0)
end = now.replace(hour=settings.WORK_END_HOUR, minute=0, second=0, microsecond=0)
nxt = now + timedelta(minutes=settings.RUN_EVERY_MINUTES)
if now < start:
    nxt = start
elif nxt >= end:
    nxt = start + timedelta(days=1)
print(int(min(MAX_WAIT, max(60, (nxt - now).total_seconds()))))
