#!/usr/bin/env bash
# Deterministic lexical evaluation of compact index representations. Token cost
# is an explicit approximation (UTF-8 bytes / 4), not a model token count.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
fixtures="$root/tests/fixtures/concept-recognition/cases.tsv"
index="$root/learning-kb/concept-index.tsv"
[ -f "$fixtures" ] && [ -f "$index" ] || { echo 'ERROR: missing concept evaluation inputs' >&2; exit 2; }
printf 'variant\tprecision\trecall\tambiguous_rate\ttest_cases\testimated_tokens\n'
for variant in keyword keyword-category keyword-category-aliases keyword-category-aliases-hint; do
  awk -F '\t' -v variant="$variant" '
    NR==FNR { if (NR > 1) { id[NR]=$1; key[NR]=$2; cat[NR]=$3; aliases[NR]=$4; hint[NR]=$5; n=NR } next }
    FNR == 1 { next }
    { text=tolower($2); expected=$3; expected_category=$4; matches=0; hit=""; for (i=2;i<=n;i++) { found=(index(text,tolower(key[i]))>0); if (variant != "keyword") found=found || (index(text,tolower(cat[i]))>0 && index(text,tolower(key[i]))>0); if (variant ~ /aliases/) { split(tolower(aliases[i]), a, "\\|"); for (j in a) if (a[j] != "" && index(text,a[j])>0) found=1 } if (found) { matches++; hit=id[i] } } total++; if (matches > 1) ambiguous++; if (matches == 1) { predicted++; if (hit == expected) correct++ } }
    END { precision=(predicted ? correct/predicted : 0); recall=(total ? correct/total : 0); ambiguity=(total ? ambiguous/total : 0); bytes=0; for(i=2;i<=n;i++) { bytes+=length(id[i])+length(key[i]); if(variant!="keyword") bytes+=length(cat[i]); if(variant~/aliases/) bytes+=length(aliases[i]); if(variant~/hint/) bytes+=length(hint[i]) } printf "%s\t%.2f\t%.2f\t%.2f\t%d\t%d\n",variant,precision,recall,ambiguity,total,int((bytes+3)/4) }
  ' "$index" "$fixtures"
done
