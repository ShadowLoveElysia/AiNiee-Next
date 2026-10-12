#!/bin/bash
task_root="$(cd "$(dirname "$0")" && pwd)"
bash "$task_root/prepare_media.sh" "$@"
task_status=$?
if [ -t 0 ]; then
    read -r -p "Press Enter to close..." _
fi
exit "$task_status"
