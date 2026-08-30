#!/bin/sh
# Recon fetch helper. Usage: fetch.sh URL [OUTNAME]
# Downloads via curl into raw/, appends URL/bytes/SHA-256/type to fetchlog.tsv.
# NOTE: geodesy.noaa.gov/pub soft-404s (HTTP 200 + a "404 Error" HTML body) any
# request carrying a non-default User-Agent.  Send no UA override.  The helper
# helper warns when an HTML body arrives under a non-HTML name.
set -e
HERE="C:/claude-projects/coord-convert/review/nsrs-map-assets"
url="$1"
name="${2:-$(basename "$url")}"
dest="$HERE/raw/$name"
meta=$(curl -sSL -o "$dest" -w "%{http_code}\t%{content_type}\t%{url_effective}" "$url")
code=$(printf '%s' "$meta" | cut -f1)
ctype=$(printf '%s' "$meta" | cut -f2)
eff=$(printf '%s' "$meta" | cut -f3)
bytes=$(wc -c < "$dest" | tr -d ' ')
sha=$(sha256sum "$dest" | cut -d' ' -f1)
if head -c 200 "$dest" | grep -qi "404 Error\|Page Not Found"; then
  echo "WARN  soft-404 body: $url"
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$eff" "$bytes" "$sha" "$code" "$ctype" >> "$HERE/fetchlog.tsv"
printf 'OK  %s  %10s bytes  %s  %s\n' "$code" "$bytes" "$(printf '%s' "$sha" | cut -c1-16)" "$name"
