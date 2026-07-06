#!/usr/bin/env bash
set -euo pipefail

SECTOR_HOTSPOTS_REPORT_DIR="${SECTOR_HOTSPOTS_REPORT_DIR:-published/us-sector-hotspots}" \
SECTOR_HOTSPOTS_STATUS_DIR="${SECTOR_HOTSPOTS_STATUS_DIR:-var/us-sector-hotspots-status}" \
SECTOR_HOTSPOTS_COMMIT_LABEL="${SECTOR_HOTSPOTS_COMMIT_LABEL:-US sector hotspots}" \
SECTOR_HOTSPOTS_PUBLISH_NAME="${SECTOR_HOTSPOTS_PUBLISH_NAME:-us-sector-hotspots}" \
  "$(dirname "$0")/publish-sector-hotspots.sh"
