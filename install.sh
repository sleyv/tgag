#!/bin/bash
# tgag installer: drops the single file in place and checks credentials.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
dest="/usr/local/bin/tg"

if [ "$(id -u)" -ne 0 ]; then
    echo "need root for $dest, re-run with sudo"
    exit 1
fi

install -m 755 "$here/tgag.py" "$dest"
echo "installed $dest"

if [ ! -s "$HOME/.tg_token" ] && [ -z "$TG_TOKEN" ]; then
    cat <<'EOF'

no token yet.
  1. in Telegram open @BotFather, send /newbot
  2. pick a name and a username ending in "bot"
  3. store it:
       printf '%s' 'YOUR_TOKEN' > ~/.tg_token && chmod 600 ~/.tg_token
       printf '%s' 'YOUR_CHAT_ID' > ~/.tg_chat

chat id: message @userinfobot, or run `tg send hi` and read the log.
EOF
    exit 0
fi

echo
"$dest" me
echo
echo "next:  tg watch &      start the daemon"
echo "       tg poll         check the inbox"
echo "       python3 tgag.py agent   the agent guide"