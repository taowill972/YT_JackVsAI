#!/bin/bash
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
export PYTHONUNBUFFERED=1
cd /root/YT_JackVsAI || exit 1

echo "==========================================================" >> /var/log/yt_jackvsai_batch.log
echo "? [Cron 6h] D?clenchement de la routine ? $(date -u)" >> /var/log/yt_jackvsai_batch.log
echo "==========================================================" >> /var/log/yt_jackvsai_batch.log

python3 batch_runner.py >> /var/log/yt_jackvsai_batch.log 2>&1

