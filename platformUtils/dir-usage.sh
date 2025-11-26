#!/usr/bin/env bash
clear
find . -type d -print0 |
while IFS= read -r -d '' d; do
  size=$(du -sh "$d" 2>/dev/null | cut -f1)
  files=$(find "$d" -type f 2>/dev/null | wc -l)
  printf '%s\t%s\t%s\n' "$size" "$files" "$d"
done | sort -h -r -k1,1 | awk -F '\t' '
BEGIN {
  printf "%-8s  %-8s  %s\n", "SIZE", "FILES", "DIRECTORY";
  printf "%-8s  %-8s  %s\n", "--------", "--------", "------------------------------";
}
{
  printf "%-8s  %-8s  %s\n", $1, $2, $3;
}
'
