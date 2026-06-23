# Cloud migration helper (not used in local V1). The watcher is a one-shot
# command; schedule it with the host's cron / k8s CronJob / cloud scheduler,
# and mount a volume at /data so the SQLite DB persists across runs.
FROM python:3.12-slim

WORKDIR /app
# Runtime is Python standard library only — no pip install needed.
# (requirements.txt holds dev/test deps; not required to run the watcher.)
COPY watcher ./watcher

ENV WATCHER_DB_PATH=/data/watcher.db
VOLUME ["/data"]

# Run once per invocation (the scheduler decides cadence).
ENTRYPOINT ["python", "-m", "watcher.run"]
