#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

xgettext -o po/imageflow.pot --files-from=po/POTFILES.in

while IFS= read -r lang; do
    [ -z "$lang" ] && continue
    msgmerge --update --backup='off' "po/${lang}.po" po/imageflow.pot
done < po/LINGUAS
