#!/bin/bash
set -euo pipefail

echo '[initdb 59z] apply 65 (nutrient tips and knowledge sources)'
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f '/delivery/65_冲刺收尾_营养科普与知识库.sql'
