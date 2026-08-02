#!/usr/bin/bash
for file in ./*; do
    if [ -d $file ]; then
        NCHARS=$(find $file -name '*.xml.gz' -exec bash -c 'gzip -d -c {} | wc -c' \; | awk 'BEGIN { a = 0 }; { a+=$1}; END { print a }')
        printf '%-20s %s\n' $file $NCHARS | numfmt --to=iec --field=2
    fi
done
