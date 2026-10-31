#!/bin/bash
set -eu
systemctl stop apt-daily.timer apt-daily-upgrade.timer fwupd-refresh.timer update-notifier-download.timer || true
systemctl mask --runtime apt-daily.service apt-daily-upgrade.service fwupd-refresh.service update-notifier-download.service
systemd-run --unit=ac-nine-auto-stop --on-active=6h /usr/sbin/shutdown -h now
