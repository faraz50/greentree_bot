from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type", "API-SECRET"], methods=["GET", "POST", "OPTIONS"])
@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,API-SECRET"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

DB_FILE = "airdrop_bot.db"
API_SECRET = "452428fb1c3e4f0a61a53ea2c74a941094325afdf3ed67bb1d807abeacbc1de7"

@app.route("/tonconnect-manifest.json")
def tonconnect_manifest():
    return send_from_directory("static", "tonconnect-manifest.json", mimetype="application/json")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.before_request
def verify_api_secret():
    allowed_routes = ["register_user", "get_user_info", "tonconnect_manifest", "favicon", "save_wallet_address", "log_social_action", "purchase_tokens", "log_token_purchase", "get_global_stats", "get_invite_count"]
    if request.endpoint not in allowed_routes:
        secret = request.headers.get("API-SECRET")
        print(f"🔍 Received API_SECRET: {secret}")
        if not secret or secret != API_SECRET:
            return jsonify({"error": "Invalid API-SECRET"}), 403

@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.get_json()
    user_id = data.get("user_id")
    first_name = data.get("first_name")
    birth_year = data.get("birth_year")
    referrer_id = data.get("referrer_id")  # ✅ اضافه شد

    if not user_id or not first_name or not birth_year:
        return jsonify({"error": "User ID, first name, and birth year are required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # بررسی وجود کاربر در دیتابیس
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user_exists = cursor.fetchone()

    if user_exists:
        conn.close()
        return jsonify({"message": "User already registered", "user_id": user_id}), 200

    # مقداردهی مقدار اولیه توکن‌ها بر اساس سال تولد
    tokens = (datetime.now().year - birth_year) * 100

    # ایجاد کاربر جدید در دیتابیس
    cursor.execute("INSERT INTO users (user_id, first_name, birth_year, total_tokens, wallet_address) VALUES (?, ?, ?, ?, ?)", 
                   (user_id, first_name, birth_year, tokens, None))
        # ✅ اگر referrer وجود داشته باشد و کاربر جدید است، به معرف ۲۵۰ توکن بده
    if referrer_id:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
        ref_exists = cursor.fetchone()

        if ref_exists:
            # افزودن لاگ به token_logs
            cursor.execute("""
                INSERT INTO token_logs (user_id, tokens, category)
                VALUES (?, ?, 'invite')
            """, (referrer_id, 250))

            # افزایش total_tokens
            cursor.execute("""
                UPDATE users SET total_tokens = total_tokens + 250 WHERE user_id = ?
            """, (referrer_id,))
            print(f"🎉 250 tokens added to referrer {referrer_id}!")

    conn.commit()
    conn.close()

    print(f"✅ New user registered: {user_id} with {tokens} tokens")
    return jsonify({"success": True, "user_id": user_id, "total_tokens": tokens}), 201

@app.route("/get_user_info", methods=["GET"])
def get_user_info():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    # 👇 wallet_address رو به SELECT اضافه کن
    cursor.execute("SELECT user_id, total_tokens, wallet_address FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    total_tokens = user["total_tokens"] if user["total_tokens"] is not None else 0
    wallet_address = user["wallet_address"] if user["wallet_address"] is not None else ""

    print(f"✅ User {user_id} has {total_tokens} tokens and wallet address: {wallet_address}")

    # 👇 wallet_address رو به پاسخ اضافه کن
    return jsonify({
        "user_id": user["user_id"],
        "total_tokens": total_tokens,
        "wallet_address": wallet_address
    }), 200

@app.route("/update_tokens", methods=["POST"])
def update_tokens():
    data = request.get_json()
    user_id = data.get("user_id")
    tokens_to_add = data.get("tokens")

    if not user_id or tokens_to_add is None or tokens_to_add <= 0:
        print(f"⚠️ Invalid tokens_to_add value ({tokens_to_add}) for user {user_id}")
        return jsonify({"error": "Invalid token update request"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT total_tokens FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    new_total_tokens = result["total_tokens"] + tokens_to_add
    cursor.execute("UPDATE users SET total_tokens = ? WHERE user_id = ?", (new_total_tokens, user_id))
    conn.commit()
    conn.close()

    print(f"✅ Updated tokens for user {user_id}: {new_total_tokens}")  # لاگ مقدار جدید توکن‌ها

    return jsonify({"success": True, "total_tokens": new_total_tokens}), 200

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal Server Error", "message": str(error)}), 500

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route("/save_wallet_address", methods=["POST"])
def save_wallet_address():
    data = request.get_json()
    user_id = data.get("user_id")
    wallet_address = data.get("wallet_address")

    if not user_id or not wallet_address:
        print("❌ Missing user_id or wallet_address")
        return jsonify({"error": "Missing user_id or wallet_address"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user_exists = cursor.fetchone()

    if not user_exists:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    cursor.execute("UPDATE users SET wallet_address = ? WHERE user_id = ?", (wallet_address, user_id))
    conn.commit()
    conn.close()

    print(f"✅ Wallet address {wallet_address} saved for user {user_id}")
    return jsonify({"success": True, "wallet_address": wallet_address}), 200

@app.route("/log_social_action", methods=["POST"])
def log_social_action():
    data = request.get_json()
    user_id = data.get("user_id")
    platform = data.get("platform")

    if not user_id or not platform:
        return jsonify({"error": "Missing user_id or platform"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # جلوگیری از ثبت امتیاز تکراری
    cursor.execute("""
        SELECT * FROM token_logs
        WHERE user_id = ? AND category = 'social' AND platform = ?
    """, (user_id, platform))
    exists = cursor.fetchone()

    if exists:
        conn.close()
        return jsonify({"message": "Already rewarded for this platform"}), 200

    # ثبت پاداش جدید
    cursor.execute("""
        INSERT INTO token_logs (user_id, tokens, category, platform)
        VALUES (?, ?, 'social', ?)
    """, (user_id, 500, platform))

    cursor.execute("UPDATE users SET total_tokens = total_tokens + 500 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    print(f"🎉 500 tokens added to user {user_id} for platform {platform}")
    return jsonify({"success": True}), 200

@app.route("/log_invite", methods=["POST"])
def log_invite():
    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # بررسی اینکه فقط یک بار جایزه بدهیم
    cursor.execute("""
        SELECT * FROM token_logs
        WHERE user_id = ? AND category = 'invite_self'
    """, (user_id,))
    already_logged = cursor.fetchone()
    if already_logged:
        conn.close()
        return jsonify({"message": "Already rewarded for invite_self"}), 200

    # افزودن 250 توکن برای خودش (مثلاً برای اشتراک‌گذاری موفق)
    cursor.execute("""
        INSERT INTO token_logs (user_id, tokens, category)
        VALUES (?, ?, 'invite_self')
    """, (user_id, 250))
    cursor.execute("UPDATE users SET total_tokens = total_tokens + 250 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    print(f"🎁 250 tokens added to user {user_id} for sharing invite link")
    return jsonify({"success": True, "user_id": user_id}), 200

@app.route("/purchase_tokens", methods=["POST"])
def purchase_tokens():
    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # بررسی وجود کاربر
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    try:
        # افزودن توکن به کاربر
        cursor.execute("UPDATE users SET total_tokens = total_tokens + 10000 WHERE user_id = ?", (user_id,))
        
        # ثبت در token_logs
        cursor.execute("""
            INSERT INTO token_logs (user_id, tokens, category)
            VALUES (?, ?, 'purchase')
        """, (user_id, 10000))

        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "✅ Purchase completed successfully. 10,000 tokens added!"}), 200

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": "Server error: " + str(e)}), 500

@app.route("/log_token_purchase", methods=["POST"])
def log_token_purchase():
    data = request.get_json()
    user_id = data.get("user_id")
    transaction_boc = data.get("transaction_boc")
    amount = data.get("amount", 10000)

    if not user_id or not transaction_boc:
        return jsonify({"error": "Missing user_id or transaction data"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # بررسی وجود خرید قبلی
        cursor.execute("""
            SELECT 1 FROM token_logs WHERE user_id = ? AND category = 'purchase'
        """, (user_id,))
        already_purchased = cursor.fetchone()

        if already_purchased:
            conn.close()
            return jsonify({"error": "You have already purchased tokens!"}), 403

        # ثبت لاگ خرید
        cursor.execute("""
            INSERT INTO token_logs (user_id, tokens, category)
            VALUES (?, ?, 'purchase')
        """, (user_id, amount))

        # افزایش توکن کاربر
        cursor.execute("""
            UPDATE users SET total_tokens = total_tokens + ? WHERE user_id = ?
        """, (amount, user_id))

        conn.commit()
        conn.close()

        print(f"✅ Purchase recorded: {user_id} received {amount} tokens.")
        return jsonify({"success": True}), 200

    except Exception as e:
        conn.rollback()
        conn.close()
        print("❌ Database error during token purchase:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/check_purchase_status", methods=["GET"])
def check_purchase_status():
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 1 FROM token_logs WHERE user_id = ? AND category = 'purchase'
    """, (user_id,))
    already_purchased = cursor.fetchone()

    conn.close()

    return jsonify({"hasPurchased": bool(already_purchased)})

@app.route("/get_invite_count", methods=["GET"])
def get_invite_count():
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS invite_count
        FROM token_logs
        WHERE category = 'invite' AND user_id = ?
    """, (user_id,))

    invite_count = cursor.fetchone()["invite_count"]
    conn.close()

    return jsonify({"invite_count": invite_count}), 200

@app.route("/get_global_stats", methods=["GET", "OPTIONS"])
def get_global_stats():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()["total_users"]

    cursor.execute("SELECT SUM(tokens) AS total_tokens_distributed FROM token_logs")
    total_tokens_distributed = cursor.fetchone()["total_tokens_distributed"] or 0

    # چون فعلاً جدول transactions نداری
    total_transactions = 0

    conn.close()

    return jsonify({
        "total_users": total_users,
        "total_tokens_distributed": total_tokens_distributed,
        "total_transactions": total_transactions
    }), 200

# اجرای خودکار create_db.py فقط اگر دیتابیس وجود نداشت
if not os.path.exists("airdrop_bot.db"):
    try:
        import create_db
        print("✅ Database created automatically on startup.")
    except Exception as e:
        print(f"❌ Error creating database on startup: {e}")
import telebot
from bot import bot  # استفاده از همون bot.py که ساختی

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        print("📩 Webhook received data:", update)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"error": "Invalid content type"}), 403

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
