#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-m08-benchmark.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
"$root/scripts/generate-m08-fixture.py" --output "$tmp/small" --class small --seed 7 > "$tmp/generator.json"
jq -e '.schema=="mana.m08.fixture/v1" and .logical_counts=={artifacts:100,work_items:10,runtime_events:100,knowledge_documents:20} and .generated.regular_files==100 and .contains_customer_data==false and .network_calls==0 and .model_calls==0' "$tmp/generator.json" >/dev/null
"$root/scripts/benchmark-m08-inspect.py" --project-root "$tmp/small" --runs 1 --output "$tmp/report.json" > "$tmp/stdout.json"
cmp -s "$tmp/report.json" <(jq -S . "$tmp/stdout.json") || { jq -S . "$tmp/report.json" > "$tmp/sorted-report.json"; cmp -s "$tmp/sorted-report.json" <(jq -S . "$tmp/stdout.json"); }
jq -e '.schema=="mana.m08.inspect-benchmark/v1" and .cold.legacy_full_read.catalog_build_count==4 and .cold.snapshot_supporting.catalog_build_count==1 and .cold.snapshot_route_minimal.catalog_build_count==1 and .cold.legacy_full_read.process_count==5 and .cold.snapshot_supporting.process_count==2 and .privacy=={source_content:false,absolute_paths:false,credentials:false}' "$tmp/report.json" >/dev/null
! grep -Fq "$tmp" "$tmp/report.json" || { echo 'FAIL: benchmark leaked an absolute fixture path' >&2; exit 1; }
echo 'M08 deterministic fixture and benchmark tests passed'
