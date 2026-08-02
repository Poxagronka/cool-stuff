"""The pages you see before you are let in, and the profile page after.

Same visual language as the search page, kept apart because none of it needs
the search javascript.
"""

import html

from . import brand

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>%(title)s</title>
{icon}
<style>
  :root {
    --bg: #0b0b0c; --raise: #121214; --line: #1f1f22; --line-hi: #34343a;
    --text: #ededf0; --dim: #77777f; --dimmer: #4a4a52;
    --ease: cubic-bezier(.2,.7,.3,1);
  }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important;
    transition: none !important; } }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; background: var(--bg); color: var(--text);
    font: 15px/1.55 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI",
          Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
    display: grid; place-items: center; padding: 40px 24px;
  }
  ::selection { background: var(--text); color: var(--bg); }
  .sheet {
    width: 100%%; max-width: %(width)s; animation: rise .4s var(--ease) both;
  }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; } }
  .mark {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: 12px; letter-spacing: .16em; text-transform: uppercase;
    color: var(--dim); margin-bottom: 26px;
  }
  h1 { font-size: 22px; font-weight: 600; letter-spacing: -.01em; margin: 0 0 10px; }
  p { color: var(--dim); margin: 0 0 22px; font-size: 14px; }
  p a { color: var(--text); }
  label { display: block; font-size: 12px; color: var(--dim); margin-bottom: 7px; }
  input[type=text], input[type=password] {
    width: 100%%; padding: 13px 15px; font: inherit; color: var(--text);
    background: var(--raise); border: 1px solid var(--line); border-radius: 10px;
    outline: none; transition: border-color .2s var(--ease);
  }
  input:hover { border-color: var(--line-hi); }
  input:focus { border-color: var(--dim); }
  label + input { margin-bottom: 14px; }
  button {
    margin-top: 16px; padding: 12px 22px; font: inherit; font-size: 14px;
    color: var(--bg); background: var(--text); border: 1px solid var(--text);
    border-radius: 10px; cursor: pointer;
    transition: opacity .18s var(--ease), transform .18s var(--ease);
  }
  button:hover { opacity: .88; }
  button:active { transform: scale(.985); }
  button.ghost {
    color: var(--text); background: transparent; border-color: var(--line);
  }
  button.ghost:hover { border-color: var(--line-hi); background: var(--raise); }
  .bad { color: #d98b8b; font-size: 13px; margin-top: 14px; }
  .row {
    display: flex; align-items: center; gap: 12px; padding: 13px 0;
    border-top: 1px solid var(--line); font-size: 13.5px;
  }
  .row:last-child { border-bottom: 1px solid var(--line); }
  .row code {
    flex: 1; font: 12.5px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .row .who { color: var(--dim); font-size: 12.5px; }
  .tag {
    font-size: 11px; letter-spacing: .04em; text-transform: uppercase;
    color: var(--dimmer);
  }
  .copy {
    padding: 5px 11px; font-size: 12px; color: var(--dim); cursor: pointer;
    background: transparent; border: 1px solid var(--line); border-radius: 7px;
    margin: 0; transition: color .16s var(--ease), border-color .16s var(--ease);
  }
  .copy:hover { color: var(--text); border-color: var(--line-hi); }
  .head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 24px; }
  .head h1 { margin: 0; }
  .head a { margin-left: auto; color: var(--dim); font-size: 13px; text-decoration: none; }
  .head a:hover { color: var(--text); }
  .sub { font-size: 12px; letter-spacing: .1em; text-transform: uppercase;
         color: var(--dimmer); margin: 30px 0 6px; }
</style>
</head>
<body>
<div class="sheet">
  <div class="mark">{glyph}cool stuff</div>
  %(body)s
</div>
%(script)s
</body>
</html>
"""

SHELL = SHELL.replace("{icon}", brand.ICON_LINK).replace("{glyph}", brand.GLYPH)

COPY_JS = """
<script>
document.addEventListener("click", e => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  navigator.clipboard.writeText(b.dataset.copy).then(() => {
    const was = b.textContent;
    b.textContent = "copied";
    setTimeout(() => { b.textContent = was; }, 1400);
  });
});
</script>
"""


def page(title: str, body: str, width: str = "380px", script: str = "") -> str:
    return SHELL % {"title": title, "body": body, "width": width, "script": script}


def locked(error: str = "") -> str:
    """The whole door: sign in here, or go find someone with an invite.

    This is what every page turns into when nobody is signed in, so the sign-in
    form itself has to be on it — sending people back to their invite link
    every time was the whole complaint.
    """
    bad = f'<div class="bad">{html.escape(error)}</div>' if error else ""
    return page(
        "cool stuff — sign in",
        "<h1>Sign in</h1>"
        "<p>A private collection of links from one group chat. No account yet? "
        "You need an invite link from someone already inside.</p>"
        '<form method="post" action="/signin">'
        '<label for="name">Name</label>'
        '<input id="name" name="name" type="text" maxlength="40" autofocus '
        'autocomplete="username" placeholder="Sasha">'
        '<label for="password">Password</label>'
        '<input id="password" name="password" type="password" maxlength="200" '
        'autocomplete="current-password">'
        "<button>Sign in</button></form>" + bad,
    )


def join_form(code: str, error: str = "", name: str = "") -> str:
    bad = f'<div class="bad">{html.escape(error)}</div>' if error else ""
    return page(
        "cool stuff — join",
        "<h1>You are invited</h1>"
        "<p>Pick a name and a password. That is what you come back with — this "
        "link only works once.</p>"
        f'<form method="post" action="/join/{html.escape(code)}">'
        '<label for="name">Your name</label>'
        f'<input id="name" name="name" type="text" maxlength="40" autofocus '
        f'autocomplete="username" placeholder="Sasha" value="{html.escape(name)}">'
        '<label for="password">Password</label>'
        '<input id="password" name="password" type="password" maxlength="200" '
        'autocomplete="new-password">'
        "<button>Join</button></form>" + bad,
    )


def dead_invite() -> str:
    return page(
        "cool stuff — invite used",
        "<h1>This invite is spent</h1>"
        "<p>Every link works once. Ask whoever sent it for a fresh one.</p>",
    )


def profile(account, invites, base: str, error: str = "", said: str = "") -> str:
    """Who you are, the invites you handed out, and the password you come back with."""
    rows = []
    for inv in invites:
        link = f"{base}/join/{inv['code']}"
        if inv["used_by"]:
            rows.append(
                f'<div class="row"><span class="tag">taken</span>'
                f'<code>{html.escape(link)}</code>'
                f'<span class="who">{html.escape(inv["taken_by"] or "someone")}</span></div>'
            )
        else:
            rows.append(
                f'<div class="row"><span class="tag">open</span>'
                f'<code>{html.escape(link)}</code>'
                f'<button class="copy" data-copy="{html.escape(link)}">copy</button></div>'
            )
    listing = "".join(rows) or '<p style="margin-top:14px">No invites yet.</p>'
    bad = f'<div class="bad">{html.escape(error)}</div>' if error else ""
    note = f'<p style="margin-top:14px">{html.escape(said)}</p>' if said else ""

    body = (
        '<div class="head">'
        f"<h1>{html.escape(account['name'])}</h1>"
        '<a href="/">back to search</a></div>'
        '<form method="post" action="/me/invite"><button>Create an invite link</button></form>'
        f"{bad}"
        '<div class="sub">invites you sent</div>'
        f"{listing}"
        '<div class="sub">password</div>'
        '<p style="margin-top:8px">Changing it signs out every other device.</p>'
        '<form method="post" action="/me/password">'
        '<label for="password">New password</label>'
        '<input id="password" name="password" type="password" maxlength="200" '
        'autocomplete="new-password">'
        "<button class=\"ghost\">Change password</button></form>"
        f"{note}"
        '<form method="post" action="/logout" style="margin-top:26px">'
        '<button class="ghost">Sign out of this device</button></form>'
    )
    return page("cool stuff — profile", body, width="560px", script=COPY_JS)
