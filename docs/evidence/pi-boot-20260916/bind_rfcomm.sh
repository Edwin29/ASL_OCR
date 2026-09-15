#!/bin/bash
set -euo pipefail
if test -e /dev/rfcomm0; then
    /usr/bin/rfcomm show 0 | /usr/bin/grep -F '98:D3:02:96:9C:8C'
else
    /usr/bin/rfcomm bind 0 98:D3:02:96:9C:8C 1
fi
