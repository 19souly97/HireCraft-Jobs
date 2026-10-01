import os, json, re, hmac, hashlib, sqlite3, threading, html
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, abort, send_from_directory
import telebot
from telebot import types

TOKEN = os.environ["BOT_TOKEN"]        # from @BotFather
WEBAPP_URL = os.environ["WEBAPP_URL"]  # public HTTPS address of this server

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024


def db():
    c = sqlite3.connect("hirecraft.db")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS profiles(
        id INTEGER PRIMARY KEY, name, skill, years, location, rate, bio, photos,
        updated DEFAULT CURRENT_TIMESTAMP)""")
    return c


def user():
    """Verify Telegram's signed initData and return the Telegram user."""
    data = dict(parse_qsl(request.headers.get("X-Init-Data", "")))
    given = data.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    good = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not given or not hmac.compare_digest(good, given):
        abort(401)
    return json.loads(data["user"])


def out(r):
    d = dict(r)
    d["photos"] = json.loads(d["photos"] or "[]")
    return d


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/me")
def me():
    u = user()
    r = db().execute("SELECT * FROM profiles WHERE id=?", (u["id"],)).fetchone()
    return jsonify(out(r) if r else {})


@app.post("/api/profile")
def save():
    u = user()
    b = request.get_json(force=True)
    photos = [p for p in b.get("photos", [])[:4]
              if re.fullmatch(r"data:image/jpeg;base64,[A-Za-z0-9+/=]+", p)]
    f = {k: str(b.get(k, ""))[:1000] for k in ("name", "skill", "years", "location", "rate", "bio")}
    if not f["name"] or not f["skill"]:
        return jsonify(error="Name and skill are required"), 400
    c = db()
    c.execute("REPLACE INTO profiles(id,name,skill,years,location,rate,bio,photos) VALUES(?,?,?,?,?,?,?,?)",
              (u["id"], f["name"], f["skill"], f["years"], f["location"], f["rate"], f["bio"], json.dumps(photos)))
    c.commit()
    return jsonify(ok=True)


@app.get("/api/profiles")
def profiles():
    user()
    q = f"%{request.args.get('q', '')}%"
    rows = db().execute(
        "SELECT * FROM profiles WHERE skill LIKE ? OR bio LIKE ? OR name LIKE ? "
        "ORDER BY updated DESC LIMIT 50", (q, q, q)).fetchall()
    return jsonify([out(r) for r in rows])


@app.post("/api/hire")
def hire():
    u = user()
    worker_id = int(request.get_json(force=True)["id"])
    if u.get("username"):
        who = "@" + html.escape(u["username"])
    else:
        who = f'<a href="tg://user?id={u["id"]}">{html.escape(u.get("first_name", "A recruiter"))}</a>'
    try:
        bot.send_message(worker_id,
            f"<b>New hire request</b>\n{who} wants to hire you through Hirecraft Jobs. "
            "Message them directly to agree on the job details.", parse_mode="HTML")
    except Exception:
        return jsonify(error="Couldn't reach this person. They need to open the bot first."), 502
    return jsonify(ok=True)


@bot.message_handler(commands=["start"])
def start(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Open Hirecraft Jobs", web_app=types.WebAppInfo(WEBAPP_URL)))
    with open("static/logo.png", "rb") as f:
        bot.send_photo(m.chat.id, f, reply_markup=kb,
                       caption="Welcome to Hirecraft Jobs.\nShow your skills and past work, or find and hire talent.")


if __name__ == "__main__":
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
