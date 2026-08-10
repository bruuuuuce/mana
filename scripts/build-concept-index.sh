#!/usr/bin/env bash
# Build the compact, deterministic classifier index from canonical concept files.
set -eu
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
concepts="$root/learning-kb/concepts"
[ -d "$concepts" ] || { echo "ERROR: missing concept storage: $concepts" >&2; exit 2; }
printf 'id\tkey\tcategory\taliases\thint\tlanguages\tframeworks\n'
find "$concepts" -type f -name 'cpt_*.yaml' | LC_ALL=C sort | while IFS= read -r file; do
  jq -er 'select(.schema == "mana.learning.concept/v1") | select(.id|test("^cpt_[0-9]{3}$")) | select(.key|type == "string" and length > 0) | select(.category|type == "string" and length > 0) | select(.aliases|type == "array") | select(.hint|type == "string") | select(.languages|type == "array") | select(.frameworks|type == "array") | [.id,.key,.category,(.aliases|join("|")),.hint,(.languages|join("|")),(.frameworks|join("|"))] | @tsv' "$file"
done
