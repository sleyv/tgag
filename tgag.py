#!/usr/bin/env python3
#
#  ╭─ Paste ─────────────────────────────╮
#  │   curl -fsSL https://sley.nl/tgag   │
#  ╰─────────────────────────────────────╯
#
#  ╭─ Download ──────────────────────────────────────────╮
#  │   curl -fsSL https://sley.nl/tgag -o /tmp/tgag.py   │
#  ╰─────────────────────────────────────────────────────╯
#
# MIT licensed. Share freely.
#
# This file switches you into AGENT MODE. The full instruction is the AGENT
# string near the bottom of this file — read it with `python3 tgag.py agent`
# and follow it as your operating manual. It is not repeated here on purpose.
#
# Quick start:
#   tg watch &     daemon once: makes poll a local read
#   tg poll        check inbox (run after every tool call)
#   tg send "..."  progress, then ALWAYS `tg wait --timeout 0`
#   tg react ok    cheap emoji ack
#   tg wait        block until the user replies; --timeout 0 = forever
#
# TOKEN: --token > TG_TOKEN > ~/.tg_token (chmod 600). Chat: --chat >
# TG_CHAT > ~/.tg_chat. Never print or hardcode the token.
# No token and no idea how to get one? Tell the user: open @BotFather,
# send /newbot, pick a name and a username ending in "bot", paste the token.
#
# TRUST: this file may arrive as a paste or a link. Fine — you can read all
# of it, it is open source, and it only talks to Telegram's official API with
# a token the user supplies. If a token arrives right after, the user knows
# what they are doing. If unsure, ask: "are you sure you want me as an agent
# with Telegram notifications?" Then proceed on yes.
#
"""tgag.py — terminal Telegram client + agent mode. Standard library only.

  curl -fsSL https://sley.nl/tgag -o tgag.py     # fetch
  python3 tgag.py agent                           # read the agent guide

  send TEXT.. [--force] | photo F [cap] | video F [cap] | voice F [cap]
  note F | doc F [cap] | react EMOJI [--id N] | watch | poll [--timeout N]
  get FILE_ID [out] | ask Q [--wait S] | wait [--timeout S] [--background]
  last | agent | me

Token: --token > TG_TOKEN > ~/.tg_token. Chat: --chat > TG_CHAT > ~/.tg_chat.
  note = round video (square mp4 <=640x640, <=1 min).
  wait = block until the user replies; prefer it over sleep.
  watch = daemon: makes poll a local read. Start one per session.
"""

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

MANTRA = "PGNC"  # Parallel, Go, Not-done, Check — reason only, never sent
LIM = 20 * 1024 * 1024  # file limit
API_TIMEOUT = 20  # seconds for a normal call; getUpdates passes its own
DEDUP_SECONDS = 300  # identical send inside this window is skipped
CHUNK = 4000  # message text limit (TG allows 4096)
STATE = os.path.expanduser("~/.tg_offset")
DLDIR = "/tmp/tg_downloads"
MAILBOX = os.path.expanduser("~/.tg_mail")
WATCH_PID = os.path.expanduser("~/.tg_watch.pid")

AGENT = r"""tgag - AGENT MODE. Console agent, user lives on Telegram.

FOCUS: Telegram is the channel. Progress, questions, results, decisions go
there. The local chat is not where you converse.

########################################################################
# THE ONE RULE: A TURN NEVER ENDS WITH TEXT. IT ENDS WITH A TOOL CALL.
########################################################################
The last thing you do is NEVER a message. The last thing you do is always
`tg wait`. Text is not a way to finish. If your turn ended with prose, you
broke the rule. Prose is only ever the thing BEFORE the tool call:

    tg send "short status"
    tg wait --timeout 0          <- the turn ends HERE, on this call

Ending a turn with a paragraph is the failure mode this mode exists to stop.
You are never done. There is no state you reach where the answer is "I have
nothing left to say". The only thing after any summary is a wait. Even after
a genuine hard stop - out of ideas, out of work, unsure, out of options -
send the summary and WAIT. Being blocked on the user is always better than
going quiet. The only exit is the user saying finished/end. Ever.

########################################################################

RULES
1. After EVERY tool call check the inbox: append `&& tg poll`. With the
   daemon running it is a local file read and takes no time. Never answer
   without checking.
2. Stay parallel. Answer the moment the inbox has something; keep background
   jobs running while you talk.
3. Default loop is `tg poll` + `tg send`. That is 90% of the work.

REACTIONS - two stages, both automatic:
  👀 received  the daemon got it: the message reached the machine, unread
  🫡 seen      poll/wait printed it, so it is in your context - you read it
A message stuck on 👀 means it arrived but you have NOT looked at it yet. That
is the whole point: 👀 alone = not read yet, 👀 + 🫡 = read. You do NOT need to
run `tg react` for normal reading: poll and wait mark it for you.
`--no-auto-seen` turns the marking off if you want to control it by hand.

COMMANDS
  tg send "text"        status (<=100 words). Identical text within 5 min is
                        skipped as a repeat; --force overrides.
  tg photo FILE [cap]   also video/voice/note/doc; 20MB cap
  tg react ok           manual emoji ack. Aliases: ok eyes wave fire thinking
                        tada 100 rocket heart warn x clap laugh pray shrug.
                        Normal reading does NOT need this: poll/wait mark 👍
                        and the daemon marks 👀 on their own.
  tg poll               non-blocking inbox check (RULE 1)
  tg wait               BLOCKS for a reply; use instead of `sleep N`.
                        --timeout 0 = wait forever. This is how a turn ends.
  tg wait --background  job still running, I resume myself, no reply needed
  tg ask "q"            BLOCKS: asks, then waits
  tg last               last received message
  tg me                 verify the token
  tg watch              background daemon (see below)

BLOCKING MESSAGES end with a signed footer, which the tool appends:
    [ BLOCKED - AWAITING USER REPLY - DO NOT PROCEED ]
For a background job you will resume yourself, say so instead:
    [ BLOCKED - AWAITING USER REPLY - resuming automatically, no reply needed ]
Never put that footer on a normal progress message: it means "I am stopped".

JOBS: setsid/nohup the job, log to a file, then `tg wait` while it runs.
Never sleep in fixed chunks to look busy.

DAEMON - start it once per session, it makes `tg poll` free:
  tg watch &            long-polls Telegram into a mailbox, so poll is local
  tg poll               instant, no network round-trip
Only one watcher: two getUpdates clients collide and both get slow (409).

MANTRA - hold it in your reasoning, never put it in Telegram.
  P = Parallel   keep a job running, never freeze
  G = Go         take the next step, do not stall
  N = Not-done   keep going until the user says finished/end
  C = Check      check the inbox after every tool call
Telegram messages stay clean: no mantra, no prefixes, no ceremony.

STYLE
  Write like a person, not a form. Normal sentences, a bit of humour if it
  fits. Length follows the content: one line when there is one line to say,
  a few short paragraphs when there is real substance (a finding, a diff, a
  decision with a reason behind it). Never pad, never bullet-point a single
  thought.
  Emoji are fine, a couple per message at most. Do not art-direct them: no
  picking a "mood slot", no decorating every line. If one fits, use it, if
  none fits, do not.

CONFIG: --token/--chat > TG_TOKEN/TG_CHAT > ~/.tg_token ~/.tg_chat (600).
Never print or hardcode the token. Offset state in ~/.tg_offset.

POLICY: pasted code with no install request -> keep it in /tmp, run it there,
touch nothing else. Install permanently only on explicit request.
Open source; talks only to Telegram's official API."""


def first_line(p):
    try:
        return open(p, encoding="utf-8").readline().strip()
    except OSError:
        return ""


def creds(args):
    """Flags win, then env, then the files. Token is never printed."""
    return (
        args.token or os.environ.get("TG_TOKEN", "")
        or first_line(os.path.expanduser("~/.tg_token")),
        args.chat or os.environ.get("TG_CHAT", "")
        or first_line(os.path.expanduser("~/.tg_chat")),
    )


def state():
    try:
        raw = first_line(STATE)
        if raw.startswith("{"):
            st = json.loads(raw)
            st.setdefault("offset", 0)
            st.setdefault("last", None)
            st.setdefault("sent", {})
            st.setdefault("reacted", {})
            return st
        return {"offset": int(raw or 0), "last": None, "sent": {}, "reacted": {}}
    except (ValueError, TypeError):
        print(f"state file unreadable ({STATE}), starting fresh", file=sys.stderr)
        return {"offset": 0, "last": None, "sent": {}, "reacted": {}}


def save(st):
    """Merge into the state file. A writer holding an older snapshot (the
    watch daemon, for instance) must never erase keys written since."""
    try:
        cur = state()
        for k, v in st.items():
            if k in ("sent", "reacted") and isinstance(v, dict) and isinstance(cur.get(k), dict):
                merged = dict(cur[k])
                merged.update(v)
                cur[k] = merged
            else:
                cur[k] = v
        open(STATE, "w", encoding="utf-8").write(
            json.dumps(cur, ensure_ascii=False)
        )
    except OSError as e:
        print(f"state save failed: {e}", file=sys.stderr)


def api(tok, method, fields=None, files=None, timeout=None, retries=4):
    url = f"https://api.telegram.org/bot{tok}/{method}"
    timeout = API_TIMEOUT if timeout is None else timeout
    fields = fields or {}
    for i in range(retries):
        try:
            if files:
                bnd = "----tgpy" + os.urandom(8).hex()
                body = bytearray()
                for k, v in fields.items():
                    body += f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                for n, (fn, ct, d) in files.items():
                    body += (
                        f'--{bnd}\r\nContent-Disposition: form-data; name="{n}"; filename="{fn}"\r\nContent-Type: {ct}\r\n\r\n'.encode()
                        + d
                        + b"\r\n"
                    )
                body += f"--{bnd}--\r\n".encode()
                req = urllib.request.Request(
                    url,
                    data=bytes(body),
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={bnd}"
                    },
                    method="POST",
                )
            else:
                req = urllib.request.Request(
                    url,
                    data=urllib.parse.urlencode(fields).encode(),
                    method="POST",
                )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r = json.load(r)
            if not r.get("ok"):
                sys.exit(f"API error: {r.get('description', r)}")
            return r
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
            try:
                err += ": " + e.read().decode("utf-8", "replace")[:150]
            except Exception:
                pass
            if i == retries - 1:
                print("API failed: " + err, file=sys.stderr)
                sys.exit(1)
            time.sleep(1 + i * (2 if e.code == 409 else 1))
        except Exception as e:
            if i == retries - 1:
                print(
                    f"API failed after {time.strftime('%H:%M:%S')}: "
                    f"{type(e).__name__}: {e} "
                    f"(gave up after {retries} tries, {timeout}s each)",
                    file=sys.stderr,
                )
                sys.exit(1)
            time.sleep(1 + i)


def check_note(path):
    """Round videos: square, max 640x640, max 60s. Validate via ffprobe if present."""
    fp = shutil.which("ffprobe")
    if not fp:
        print(
            "hint: ffprobe not found, uploading unchecked (needs square mp4 <=640x640, <=60s)"
        )
        return
    try:
        out = (
            subprocess.run(
                [
                    fp,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height,duration",
                    "-of",
                    "csv=p=0",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            .stdout.strip()
            .split(",")
        )
        w, h, dur = int(float(out[0])), int(float(out[1])), float(out[2])
    except Exception as e:
        print(f"ffprobe failed ({e}), uploading unchecked")
        return
    if w != h or w > 640:
        sys.exit(f"round video must be square and <=640x640, got {w}x{h}")
    if dur > 60:
        sys.exit(f"round video max 1 min, got {dur:.1f}s")
    print(f"note ok: {w}x{h}, {dur:.1f}s")


def check(path):
    if not os.path.isfile(path):
        sys.exit(f"no such file: {path}")
    s = os.path.getsize(path)
    if s > LIM:
        sys.exit(f"file {s / 1048576:.1f} MB over 20 MB limit")
    return s


def chunks(text):
    out, cur = [], ""
    for para in text.split("\n"):
        while len(para) > CHUNK:
            c = para.rfind(" ", 0, CHUNK)
            c = c if c > 0 else CHUNK
            out.append(para[:c])
            para = para[c:].lstrip()
        if cur and len(cur) + len(para) + 1 > CHUNK:
            out.append(cur)
            cur = para
        else:
            cur = cur + "\n" + para if cur else para
    if cur:
        out.append(cur)
    return out or [""]


def _dedup_hit(text, window=DEDUP_SECONDS):
    """True if this exact text already went out recently."""
    key = hashlib.sha1(text.strip().encode()).hexdigest()
    sent = state().get("sent", {})
    now = int(time.time())
    sent = {k: v for k, v in sent.items() if now - int(v) < window * 4}
    if now - int(sent.get(key, 0)) < window:
        return True
    sent[key] = now
    st = state()
    st["sent"] = sent
    save(st)
    return False


def do_send(tok, chat, text, force=False):
    if not text.strip():
        sys.exit("empty text")
    if not force and _dedup_hit(text):
        print("skipped: identical message sent in the last "
              f"{DEDUP_SECONDS}s (--force to send anyway)")
        return
    mid = None
    cs = chunks(text)
    for i, c in enumerate(cs):
        if i:
            time.sleep(0.3)
        mid = api(tok, "sendMessage", {"chat_id": chat, "text": c})["result"][
            "message_id"
        ]
    x = f" in {len(cs)} chunks" if len(cs) > 1 else ""
    print(
        f"sent ~{len(text.split())} words ({len(text)} chars{x}), message_id={mid}"
    )


def do_upload(tok, chat, method, field, path, caption, kind=""):
    s = check(path)
    if kind == "note":
        check_note(path)
    with open(path, "rb") as f:
        data = f.read()
    ct = mimetypes.guess_type(path)[0] or "application/octet-stream"
    fl = {"chat_id": chat}
    if caption:
        fl["caption"] = caption
    mid = api(tok, method, fl, {field: (os.path.basename(path), ct, data)})[
        "result"
    ]["message_id"]
    print(
        f"uploaded {os.path.basename(path)} ({s / 1048576:.2f} MB), message_id={mid}"
    )


# Telegram only accepts a fixed set of reaction emoji; these are all valid.
# Telegram accepts only a fixed set of reaction emoji; verified against the API.
EMOJI = {
    "received": "\U0001F440", "seen": "\U0001FAE1",   # eyes = in, salute = read
    "ok": "\U0001F44D", "eyes": "\U0001F440", "wave": "\U0001F44C",
    "fire": "\U0001F525", "heart": "\u2764\uFE0F", "warn": "\u26A0\uFE0F",
    "x": "\u274C", "rocket": "\U0001F680", "thinking": "\U0001F914",
    "clap": "\U0001F44F", "laugh": "\U0001F602", "wow": "\U0001F62E",
    "sad": "\U0001F614", "pray": "\U0001F64F", "100": "\U0001F4AF",
    "tada": "\U0001F389", "mind": "\U0001F92F", "cry": "\U0001F622",
    "angry": "\U0001F92C", "sleepy": "\U0001F971", "dove": "\U0001F54A",
    "clown": "\U0001F921", "love": "\U0001F970", "shrug": "\U0001F937",
}


def do_react(tok, chat, emoji, msg_id, quiet=False, replace=False, stage="seen"):
    """Two-stage ack of ONE user message, deliberately dumb and predictable.

    stage="seen"     (default) the MODEL has read and understood it.
    stage="received" the transport picked it up; nobody has read it yet.

    The daemon sets "received" automatically, so the pair reads as a handover:
    the message arrived, then the agent actually took it in. A given stage is
    set once per message, so nothing flickers or changes."""
    alias = emoji.lower()
    e = EMOJI.get(alias, emoji)
    if alias not in EMOJI:
        print(f"hint: '{emoji}' is not a known alias, sent as-is "
              f"(Telegram rejects emoji outside its reaction set)", file=sys.stderr)
    st = state()
    last = st.get("last") or {}
    if msg_id is not None:
        target = msg_id
    elif last.get("id"):
        target = last["id"]        # the user's own message, never sent_mid
    else:
        sys.exit("no user message to react to yet (pass --id MESSAGE_ID)")
    done = st.get("reacted") or {}
    key = f"{target}:{stage}"
    if key in done and not replace:
        print(f"message {target} already marked '{stage}' ({done[key]}), skipping "
              f"(--replace to change it)")
        return
    api(tok, "setMessageReaction", {"chat_id": chat, "message_id": str(target),
                                    "reaction": json.dumps([{"type": "emoji", "emoji": e}])})
    done[key] = e
    st["reacted"] = done
    save(st)
    if not quiet:
        print(f"[{stage}] {e} on your message {target}")


def fetch(tok, fid, out=None):
    info = api(tok, "getFile", {"file_id": fid})["result"]
    if info.get("file_size", 0) > LIM:
        print("remote file over 20MB, skipped", file=sys.stderr)
        return None
    out = out or os.path.basename(info["file_path"])
    with (
        urllib.request.urlopen(
            f"https://api.telegram.org/file/bot{tok}/{info['file_path']}",
            timeout=120,
        ) as r,
        open(out, "wb") as f,
    ):
        n = 0
        while True:
            b = r.read(65536)
            if not b:
                break
            n += len(b)
            if n > LIM:
                print("download over 20MB, aborted", file=sys.stderr)
                if os.path.exists(out):
                    os.remove(out)
                return None
            f.write(b)
    return out


def describe(msg, tok=None, dldir=None):
    text = msg.get("text", "") or msg.get("caption", "") or ""
    media = None
    if msg.get("photo"):
        b = msg["photo"][-1]
        media = (
            "photo",
            b["file_id"],
            b.get("file_size", 0),
            f"photo_{b['file_id'][:8]}.jpg",
        )
    for k in ("document", "video", "voice", "audio"):
        if isinstance(msg.get(k), dict):
            m = msg[k]
            fn = (m.get("file_name") or f"{k}.dat").replace("/", "_")[:120]
            media = (k, m.get("file_id"), m.get("file_size", 0), fn)
    note = ""
    if media:
        kind, fid, fs, fn = media
        if tok is not None and dldir is not None and fid:
            if fs and fs > LIM:
                note = f"[{kind} too large, skipped]"
            else:
                os.makedirs(dldir, exist_ok=True)
                got = fetch(
                    tok, fid, os.path.join(dldir, f"{int(time.time())}_{fn}")
                )
                note = (
                    f"[{kind} -> {got}]" if got else f"[{kind} download failed]"
                )
        else:
            note = f"<{kind} file_id={fid}>"
    return " ".join(x for x in (text, note) if x) or "[empty]"


def updates(tok, offset, timeout):
    return api(
        tok,
        "getUpdates",
        {"offset": str(offset + 1), "limit": "50", "timeout": str(timeout)},
        timeout=timeout + 20,
    ).get("result", [])


# Signed footer appended to any message that stops the agent. The agent may
# not proceed until the user answers, so the message says so on its last line.
BLOCKED_NOTE = (
    "\N{HOURGLASS WITH FLOWING SAND} blocked \u2014 I am waiting for your reply"
    " and cannot continue until you answer."
)
BLOCKED_TAG = "[ BLOCKED \u2014 AWAITING USER REPLY \u2014 DO NOT PROCEED ]"
BLOCKED_ASYNC = (
    "[ BLOCKED \u2014 AWAITING USER REPLY \u2014 resuming automatically, "
    "no need to reply ]"
)


def _ingest(tok, chat, u, dldir, st):
    """Handle one update; return its text if it is a message for us."""
    m = u.get("message") or u.get("edited_message") or {}
    if str((m.get("chat") or {}).get("id")) != str(chat):
        return None
    frm = (m.get("from") or {}).get("username", "?")
    disp = describe(m, tok, dldir)
    ts = m.get("date")
    when = time.strftime("%H:%M", time.localtime(ts)) if ts else "??:??"
    st["last"] = {"from": frm, "text": disp, "id": m.get("message_id")}
    print(f"[{u['update_id']}] {when} @{frm}: {disp}", flush=True)
    return disp


def _mail_append(chat, frm, disp, uid, mid=None):
    """Daemon writes here; readers drain it. One JSON line per message."""
    try:
        with open(MAILBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": uid, "mid": mid, "chat": str(chat),
                                "from": frm, "text": disp,
                                "at": int(time.time())},
                               ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"mailbox write failed: {e}", file=sys.stderr)


def _mail_drain():
    """Read and clear the mailbox. Returns the list of entries."""
    try:
        with open(MAILBOX, encoding="utf-8") as f:
            lines = [x for x in f.read().splitlines() if x.strip()]
        open(MAILBOX, "w").close()
    except OSError:
        return []
    out = []
    for x in lines:
        try:
            out.append(json.loads(x))
        except ValueError:
            pass
    return out


def _watch_alive():
    """True when a watcher daemon owns the Telegram connection."""
    try:
        os.kill(int(first_line(WATCH_PID)), 0)
        return True
    except (ValueError, OSError):
        return False


def _write_pid(path, pid):
    try:
        open(path, "w", encoding="utf-8").write(str(pid))
    except OSError as e:
        print(f"pid file failed: {e}", file=sys.stderr)


def _mark_seen(tok, chat, mid, auto=True):
    """The reader marks a message as read. Once poll/wait has printed a message
    it is in the agent's context, so that IS the model having read it: no point
    making the agent remember a command for something the tool can prove."""
    if not (auto and mid):
        return
    if f"{mid}:seen" in (state().get("reacted") or {}):
        return
    try:
        do_react(tok, chat, "seen", mid, quiet=True, stage="seen")
    except BaseException as e:
        print(f"auto-seen mark failed: {e}", file=sys.stderr)


def _take(tok, chat, st, slice_s, dldir, allow_api=True, auto_seen=True):
    """One wait slice. With the daemon running this is a local file read and
    touches no API, so the daemon's getUpdates is never disturbed. Without it
    we fall back to polling Telegram directly."""
    if _watch_alive():
        for _ in range(max(1, min(slice_s, 60))):   # poll the mailbox briefly
            got = _mail_drain()
            if got:
                for g in got:
                    ts = time.strftime("%H:%M", time.localtime(g["at"]))
                    print(f"[{g['id']}] {ts} @{g['from']}: {g['text']}", flush=True)
                    if g.get("mid"):
                        st["last"] = {"from": g["from"], "text": g["text"],
                                      "id": g["mid"]}
                save(st)
                for g in got:
                    _mark_seen(tok, chat, g.get("mid"), auto_seen)
                return True
            time.sleep(0.5)
        return False
    if not allow_api:
        return False
    first = None
    mids = []
    for u in updates(tok, st["offset"], slice_s):
        st["offset"] = max(st["offset"], u["update_id"])
        d = _ingest(tok, chat, u, dldir, st)
        mids.append((u.get("message") or {}).get("message_id"))
        if d and first is None:
            first = d
    save(st)
    for mid in mids:
        _mark_seen(tok, chat, mid, auto_seen)
    return first


def do_watch(tok, chat, dldir, interval=5):
    """Daemon: own the Telegram connection, long-poll into the mailbox so every
    other command is a local file read. Exactly one watcher per bot."""
    _write_pid(WATCH_PID, os.getpid())
    print(f"watching for messages (pid {os.getpid()}), ctrl-c to stop", flush=True)
    try:
        while True:
            try:
                st = state()
                for u in updates(tok, st["offset"], interval):
                    st["offset"] = max(st["offset"], u["update_id"])
                    m = u.get("message") or u.get("edited_message") or {}
                    if str((m.get("chat") or {}).get("id")) != str(chat):
                        continue
                    frm = (m.get("from") or {}).get("username", "?")
                    disp = describe(m, tok, dldir)
                    mid = m.get("message_id")
                    st["last"] = {"from": frm, "text": disp, "id": mid}
                    save(st)
                    _mail_append(chat, frm, disp, u["update_id"], mid)
                    # transport got it; nobody has read it yet
                    if mid and f"{mid}:received" not in (st.get("reacted") or {}):
                        try:
                            do_react(tok, chat, "received", mid, quiet=True,
                                     stage="received")
                        except BaseException as e:  # never kill the watcher
                            print(f"auto-receive mark failed on {mid}: {e}",
                                  file=sys.stderr, flush=True)
                save(st)
            except SystemExit as e:
                print(f"watch: api stopped ({e}); retrying in 3s", file=sys.stderr)
                time.sleep(3)
            except Exception as e:
                print(f"watch: {type(e).__name__}: {e}; retrying in 3s", file=sys.stderr)
                time.sleep(3)
            _write_pid(WATCH_PID, os.getpid())  # heartbeat
    except KeyboardInterrupt:
        print("\nwatch stopped")
    finally:
        try:
            os.remove(WATCH_PID)
        except OSError:
            pass


def do_poll(tok, chat, timeout, dldir, quiet=False, auto_seen=True):
    """Non-blocking inbox check. Local file read when the daemon is up."""
    st = state()
    got = _take(tok, chat, st, 1 if _watch_alive() else timeout, dldir,
                auto_seen=auto_seen)
    if not got and not quiet:
        print("no new messages")
    elif got:
        print(f"--- offset={st['offset']}")


def do_wait(tok, chat, timeout, dldir, async_=False, auto_seen=True):
    """Block until the user replies. Replaces 'sleep N'. --timeout 0 = forever."""
    print(f"{BLOCKED_NOTE} (ctrl-c to stop)", flush=True)
    print(BLOCKED_ASYNC if async_ else BLOCKED_TAG, flush=True)
    deadline = time.time() + timeout if timeout > 0 else None
    while True:
        if deadline is not None and time.time() >= deadline:
            print("no reply within the timeout", flush=True)
            return
        left = None if deadline is None else deadline - time.time()
        slice_s = 30 if left is None else max(1, min(30, int(left)))
        if _take(tok, chat, state(), slice_s, dldir, auto_seen=auto_seen):
            print("--- reply received", flush=True)
            return


def do_ask(tok, chat, question, wait, auto_seen=True):
    """Blocking: send a question, then wait for the answer."""
    do_send(tok, chat, f"{question}\n\n{BLOCKED_NOTE}\n{BLOCKED_TAG}")
    st = state()
    if not _watch_alive():   # drain stale only when we own the connection
        for u in updates(tok, st["offset"], 0):
            st["offset"] = max(st["offset"], u["update_id"])
        save(st)
    print(BLOCKED_NOTE, flush=True)
    deadline = time.time() + wait if wait else None
    try:
        while True:
            if deadline is not None and time.time() >= deadline:
                print("no reply within the timeout")
                return
            left = None if deadline is None else deadline - time.time()
            slice_s = 30 if left is None else max(1, min(30, int(left)))
            if _take(tok, chat, state(), slice_s, DLDIR, auto_seen=auto_seen):
                print("--- reply received")
                return
    except KeyboardInterrupt:
        print("\nstopped waiting")


def main():
    ap = argparse.ArgumentParser(
        description="tgag.py — terminal Telegram client + agent mode"
    )
    ap.add_argument("--token", default="")
    ap.add_argument("--chat", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("text", nargs="+")
    s.add_argument("--force", action="store_true", help="send even if identical to a recent one")
    for name, h in (
        ("photo", "send a photo"),
        ("video", "send a video"),
        ("voice", "send a voice message (ogg opus)"),
        ("note", "send a round video (square mp4, max 640x640, max 1 min)"),
        ("doc", "send a file"),
    ):
        p = sub.add_parser(name, help=h)
        p.add_argument("file")
        p.add_argument("caption", nargs="?", default="")
    rc = sub.add_parser("react", help="emoji reaction on the last message")
    rc.add_argument("emoji", help="alias (ok, eyes, done, warn, ...) or a raw emoji")
    rc.add_argument("--id", type=int, default=None)
    rc.add_argument("--replace", action="store_true", help="change an existing reaction")
    rc.add_argument("--stage", default="seen", choices=["seen", "received"],
                    help="seen = the model read it (default); "
                         "received = transport only picked it up")
    wch = sub.add_parser("watch", help="daemon: keep the mailbox filled")
    wch.add_argument("--interval", type=int, default=30)
    p = sub.add_parser("poll")
    p.add_argument("--timeout", type=int, default=0)
    p.add_argument("--no-auto-seen", dest="auto_seen", action="store_false",
                   help="do not mark messages read (👀 stays as the only mark)")
    p.add_argument("--dl", default="")
    p.add_argument("--no-dl", action="store_true")
    p = sub.add_parser("get")
    p.add_argument("file_id")
    p.add_argument("out", nargs="?", default="")
    p = sub.add_parser("ask")
    p.add_argument("question")
    p.add_argument("--wait", type=int, default=0)
    w = sub.add_parser("wait", help="block until the user replies")
    w.add_argument("--timeout", type=int, default=0,
                   help="give up after N sec; 0 = wait forever (default)")
    w.add_argument("--no-auto-seen", dest="auto_seen", action="store_false",
                   help="do not mark messages read (👀 stays as the only mark)")
    w.add_argument("--background", action="store_true",
                   help="a job is still running: I will resume on my own, no reply needed")
    for name, h in (
        ("last", "show last message"),
        ("agent", "agent instructions"),
        ("me", "verify token"),
    ):
        sub.add_parser(name, help=h)
    a = ap.parse_args()
    if a.cmd == "agent":
        print(AGENT)
        return
    tok, chat = creds(a)
    if not tok:
        sys.exit("need token: --token, TG_TOKEN or ~/.tg_token")
    if a.cmd == "me":
        print(json.dumps(api(tok, "getMe")["result"], ensure_ascii=False)[:200])
        return
    if a.cmd == "get":
        out = fetch(tok, a.file_id, a.out or None)
        if out:
            print(f"saved {out}")
        return
    if not chat:
        sys.exit("need chat: --chat, TG_CHAT or ~/.tg_chat")
    if a.cmd == "send":
        do_send(tok, chat, " ".join(a.text), a.force)
        do_poll(tok, chat, 0, DLDIR, quiet=True)
    elif a.cmd in ("photo", "video", "voice", "note", "doc"):
        method, field = {
            "photo": ("sendPhoto", "photo"),
            "video": ("sendVideo", "video"),
            "voice": ("sendVoice", "voice"),
            "note": ("sendVideoNote", "video_note"),
            "doc": ("sendDocument", "document"),
        }[a.cmd]
        if a.cmd == "note" and a.caption:
            print(
                "hint: round videos have no caption, it will be dropped",
                file=sys.stderr,
            )
        do_upload(
            tok,
            chat,
            method,
            field,
            a.file,
            "" if a.cmd == "note" else a.caption,
            a.cmd,
        )
        do_poll(tok, chat, 0, DLDIR, quiet=True)
    elif a.cmd == "react":
        do_react(tok, chat, a.emoji, a.id, replace=a.replace, stage=a.stage)
    elif a.cmd == "watch":
        do_watch(tok, chat, DLDIR, a.interval)
    elif a.cmd == "poll":
        do_poll(tok, chat, a.timeout, None if a.no_dl else (a.dl or DLDIR),
                auto_seen=a.auto_seen)
    elif a.cmd == "ask":
        do_ask(tok, chat, a.question, a.wait, a.auto_seen)
    elif a.cmd == "wait":
        do_wait(tok, chat, a.timeout, DLDIR, a.background, a.auto_seen)
    elif a.cmd == "last":
        last = state().get("last")
        print(
            f"[{last['from']}]: {last['text']}" if last else "no saved history"
        )


if __name__ == "__main__":
    main()
