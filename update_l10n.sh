#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

POT_FILE="po/imageflow.pot"
POT_TEMP="${POT_FILE}.tmp"
trap 'rm -f "$POT_TEMP"' EXIT

# ignore POT-Creation-Date so unchanged templates aren't rewritten
xgettext -o "$POT_TEMP" --files-from=po/POTFILES.in
sed -i '/^"POT-Creation-Date:/d' "$POT_TEMP"

if ! diff -q "$POT_FILE" "$POT_TEMP" > /dev/null 2>&1; then
    mv "$POT_TEMP" "$POT_FILE"
else
    exit 0
fi

# merge only when the template has changed
while IFS= read -r lang; do
    [ -z "$lang" ] && continue
    msgmerge --update --backup='off' "po/${lang}.po" "$POT_FILE"
done < po/LINGUAS
