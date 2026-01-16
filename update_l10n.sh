#!/bin/bash

xgettext -o po/imageflow.pot --files-from=po/POTFILES.in

# msgmerge --update --backup='off' po/it.po po/imageflow.pot
msgmerge --update --backup='off' po/ru.po po/imageflow.pot

exit 0
