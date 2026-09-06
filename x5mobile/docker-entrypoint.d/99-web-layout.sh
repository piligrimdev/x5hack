#!/bin/sh
set -eu

raw="${MOBILE_LAYOUT:-${EXPO_PUBLIC_WEB_LAYOUT:-phone}}"
raw=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')

case "$raw" in
  fullscreen|full|1|true) layout=fullscreen ;;
  *) layout=phone ;;
esac

printf "window.__X5_WEB_LAYOUT__='%s';\n" "$layout" > /usr/share/nginx/html/layout.js
echo "x5mobile web layout: $layout"
