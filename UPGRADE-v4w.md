# scholar. v4w — analytics view hides the top bar

**No schema change → no DB reset.** One-line behaviour fix.

In the Analytics view the entire two-tier top bar is now hidden, leaving just
the Analytics / Cushion / Timeline tab bar (and the left rail). The ⌂ rail
button still brings you back to the calendar, which restores the top bar.

Note: the running-timer pill lives in the top bar, so it isn't shown while
you're on the analytics page — the timer keeps running server-side regardless;
it reappears when you return to the calendar.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4w kit
docker compose build --no-cache hive-api && docker compose up -d
```
Hard-refresh.

## Up next
- Pass 2: Future analytics (available study time, tasks due, workload pie, etc.).
- Then Cushion + Timeline sub-tabs.
