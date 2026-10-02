# tgag

Telegram client for AI coding agents, plus an **agent mode**: pasting this
file into a chat switches that agent into a mode where it talks to you on
Telegram, reports progress, asks questions, and never stops on its own.

Single file. Standard library only. No dependencies, no build step.

```bash
curl -fsSL https://sley.nl/tgag -o tgag.py
python3 tgag.py agent        # read the operating manual
```

---

## What it does

- **Telegram as the channel.** Progress, questions, results and decisions go
  to Telegram. The agent's own chat is not where you converse.
- **Inbox check after every tool call.** `tg poll` is one short command the
  agent appends; with the daemon running it is a local file read, not a network
  round-trip.
- **`tg wait` instead of `sleep`.** The agent blocks until you actually reply,
  rather than waking up to guess whether anything happened.
- **Two-stage reactions.** 👀 when the message reached the machine, 🫡 when the
  agent has it in context. A message stuck on 👀 has not been read yet.
- **Repeat suppression.** The same status line is not sent twice in five
  minutes.

## Install

```bash
# 1. get a token from @BotFather in Telegram (/newbot)
# 2. store credentials, 600 because it is a secret
printf '%s' '123456:ABC-your-token' > ~/.tg_token && chmod 600 ~/.tg_token
printf '%s' '987654321'          > ~/.tg_chat

# 3. install the command
sudo install -m 755 tgag.py /usr/local/bin/tg
```

No token yet, and not sure how to get one? In Telegram open **@BotFather**,
send `/newbot`, pick a name and a username ending in `bot`, and paste the
token it gives back.

## Usage

```
tg send "text"         status message (<=100 words)
tg photo FILE [cap]    also video / voice / note / doc, 20MB cap
tg poll                non-blocking inbox check
tg wait                block until you reply; --timeout 0 waits forever
tg wait --background   job still running, agent resumes itself
tg ask "question"      ask, then block for the answer
tg react ok            manual emoji ack
tg watch               background daemon
tg last                last received message
tg me                  verify the token
tg agent               the full agent guide
```

Start the daemon once per session. It owns the Telegram connection, which makes
every other command local and fast:

```bash
tg watch &      # long-polls into a mailbox
tg poll         # ~600ms, no network
```

**Exactly one watcher per bot.** Two clients on one token collide with a 409
and both get slow.

## Configuration

Priority order, first hit wins:

| what | flags | env | file |
|---|---|---|---|
| token | `--token` | `TG_TOKEN` | `~/.tg_token` |
| chat id | `--chat` | `TG_CHAT` | `~/.tg_chat` |

State lives in `~/.tg_offset` (inbox offset, last message, dedup and reaction
bookkeeping). Incoming media is downloaded to `/tmp/tg_downloads`.

The token is never printed and never belongs in a script.

## Agent mode

Pasting the file into a chat is the whole activation. The agent reads the
`AGENT` string with `python3 tgag.py agent` and follows it. The one rule:

> **A turn never ends with text. It ends with a tool call.** The last thing you
> do is `tg wait`, never a paragraph. You are never "done": send the summary,
> then wait. Only the user ends the session.

The mantra **PGNC** — Parallel, Go, Not-done, Check — is held in the agent's
reasoning and never sent to Telegram.

The agent writes like a person: length follows the content, from one line to a
few paragraphs when there is something real to say. A couple of emoji if they
fit, none if they do not.

## Files

| file | purpose |
|---|---|
| `tgag.py` | the program |
| `tg.py` | same file, alias for anyone who expects the old name |
| `install.sh` | one-shot install + credentials check |
| `systemd/tgag-watch.service` | run the daemon at boot |

## Reliability notes

- One `getUpdates` client at a time. The watcher owns it; everything else reads
  the mailbox file. Mixing the two is what produces 409s and multi-second stalls.
- `save()` merges rather than overwrites, so a long-running daemon holding an
  old snapshot cannot erase state written by another process.
- API calls give up after 20s with the retry count in the error, instead of
  hanging silently for a minute.
- The watcher survives any single failure: a refused reaction or a dropped
  request logs and continues.
- Only emoji Telegram accepts as reactions work. Verified against the API;
  `📥 ⏰ 🕐 📊 ⭐` are rejected, `👀 🫡 👍 🤝 👌` are not.

## License

MIT. Share freely.