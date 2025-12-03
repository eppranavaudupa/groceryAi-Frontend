# app.py (updated)
import os
import json
import re
import uuid
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, session, send_file
from flask_session import Session
from flask_cors import CORS
from dotenv import load_dotenv
from fpdf import FPDF

# Optional Gemini imports (guarded)
try:
    import google.generativeai as genai
except Exception:
    genai = None

load_dotenv()

app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "change-this-secret"),
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR="./flask_session",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=1800,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
)

# ensure dirs exist
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
os.makedirs("./saved_sessions", exist_ok=True)
os.makedirs("./tmp_pdfs", exist_ok=True)

Session(app)

# NOTE: add your frontend origin or your phone's origin here for mobile testing
CORS(app, supports_credentials=True, origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5000",
    # "http://192.168.x.x:3000"   <-- add this if you access frontend from phone
])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY and genai:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")
else:
    model = None
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY not set — model responses will be stubbed.")

# load grocery prices or create fallback
try:
    with open("grocery_prices.json", "r") as f:
        grocery_prices = json.load(f)
    print("✅ Grocery prices loaded")
except FileNotFoundError:
    print("⚠️ grocery_prices.json not found — creating sample prices")
    grocery_prices = {
        "fruits": {"apple": 80, "banana": 40, "orange": 60},
        "vegetables": {"potato": 30, "tomato": 40, "onion": 25},
        "dairy": {"milk": 60, "eggs": 80},
        "grains": {"rice": 80, "wheat": 40},
        "other": {"sugar": 45, "salt": 20},
    }
    with open("grocery_prices.json", "w") as f:
        json.dump(grocery_prices, f, indent=2)


# ----------------- helpers -----------------
def init_session():
    """Ensure session structure exists"""
    session.permanent = True
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
        session["chat_history"] = []
        session["shopping_cart"] = {
            "items": [],
            "subtotal": 0,
            "total_items": 0,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
        }
        session["user_context"] = {"name": "", "last_order_items": [], "preferences": {}}
        session.modified = True
        print(f"🆕 New session created: {session['session_id']}")
    else:
        print(f"📋 Existing session: {session['session_id']}")


def clean_text(text: str) -> str:
    text = re.sub(r'\*\*|\*|__|_|#|`|~|```|```python|\n{2,}', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\S+@\S+', '', text)
    text = re.sub(r'\.{2,}', '.', text)
    return text.strip()


def safe_text(s: str) -> str:
    """
    Convert text to ASCII-friendly string for FPDF (Latin-1). Replace non-ASCII chars with '?'.
    This prevents 'latin-1' codec can't encode character errors.
    """
    if s is None:
        return ""
    out = []
    for ch in str(s):
        # keep sensible ASCII range 32..126 and newline/tab
        if ord(ch) < 128:
            out.append(ch)
        else:
            # replace non-ascii with '?'
            out.append('?')
    return "".join(out)


def get_item_price(item_name: str):
    item_name_lower = (item_name or "").lower().strip()
    for category, items in grocery_prices.items():
        if item_name_lower in items:
            return items[item_name_lower], category
    # partial match
    for category, items in grocery_prices.items():
        for item in items:
            if item_name_lower in item or item in item_name_lower:
                return items[item], category
    return None, None


def update_shopping_cart(action, item_name=None, quantity=1):
    init_session()
    cart = session["shopping_cart"]
    if action == "add":
        price, category = get_item_price(item_name)
        if price is None:
            return False, f"Item '{item_name}' not found"
        # find existing
        item_found = False
        for i, it in enumerate(cart["items"]):
            if it["item"].lower() == item_name.lower():
                cart["items"][i]["quantity"] += quantity
                cart["items"][i]["total"] = cart["items"][i]["quantity"] * cart["items"][i]["price"]
                item_found = True
                break
        if not item_found:
            cart["items"].append({
                "item": item_name,
                "quantity": quantity,
                "price": price,
                "category": category,
                "total": price * quantity
            })
        cart["subtotal"] = sum(it["total"] for it in cart["items"])
        cart["total_items"] = sum(it["quantity"] for it in cart["items"])
        cart["last_updated"] = datetime.now().isoformat()
        session.modified = True
        return True, f"Added {quantity}kg of {item_name} to cart"
    elif action == "clear":
        cart["items"] = []
        cart["subtotal"] = 0
        cart["total_items"] = 0
        cart["last_updated"] = datetime.now().isoformat()
        session.modified = True
        return True, "Cart cleared"
    elif action == "view":
        return True, cart
    return False, "Invalid action"


def build_conversation_context():
    init_session()
    chat_history_text = ""
    if session.get("chat_history"):
        for msg in session["chat_history"][-5:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            chat_history_text += f"{role}: {msg.get('message','')[:100]}\n"
    cart_items_text = ""
    if session["shopping_cart"]["items"]:
        for it in session["shopping_cart"]["items"]:
            # use ASCII 'Rs' to avoid rupee symbol
            cart_items_text += f"- {it['quantity']}kg {it['item']} @ Rs{it['price']}/kg = Rs{it['total']}\n"
    else:
        cart_items_text = "Cart is empty"
    context = f"""=== CONVERSATION HISTORY (Last 5 messages) ===
{chat_history_text if chat_history_text else 'No previous conversation'}


=== CURRENT SHOPPING CART ===
{cart_items_text}
Total Items: {session['shopping_cart']['total_items']}
Subtotal: Rs{session['shopping_cart']['subtotal']}


=== USER CONTEXT ===
Last ordered items: {[x.get('item','') for x in session['user_context']['last_order_items'][-3:]]}
"""
    return context


def extract_cart_info_from_prompt(user_prompt: str):
    user_lower = (user_prompt or "").lower()
    quantity = 1
    item_name = None
    patterns = [
        r'(\d+)\s*(?:kg|kilos?|kilograms?|g|grams?)?\s+(?:of\s+)?([a-zA-Z]+)',
        r'add\s+(\d+)?\s*([a-zA-Z]+)\s+to',
        r'order\s+(\d+)?\s*([a-zA-Z]+)',
        r'i want\s+(\d+)?\s*([a-zA-Z]+)',
        r'(\d+)\s*([a-zA-Z]+)(?:\s+please)?'
    ]
    for pattern in patterns:
        match = re.search(pattern, user_lower)
        if match:
            if match.group(1) and match.group(1).isdigit():
                quantity = int(match.group(1))
                item_name = match.group(2)
            else:
                item_name = match.group(2) if match.group(2) else match.group(1)
            break
    if not item_name:
        for item in grocery_prices.get("fruits", {}):
            if item in user_lower:
                item_name = item
                break
    if not item_name:
        for item in grocery_prices.get("vegetables", {}):
            if item in user_lower:
                item_name = item
                break
    return item_name, quantity


def save_session_to_file():
    """Write session snapshot to ./saved_sessions/{session_id}.json"""
    try:
        init_session()
        filename = os.path.join("saved_sessions", f"{session['session_id']}.json")
        payload = {
            "session_id": session["session_id"],
            "shopping_cart": session.get("shopping_cart", {}),
            "chat_history": session.get("chat_history", []),
            "user_context": session.get("user_context", {}),
            "saved_at": datetime.now().isoformat()
        }
        with open(filename, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
        print(f"💾 Session saved to {filename}")
        return filename
    except Exception as e:
        print(f"Error saving session: {e}")
        return None


# ----------------- routes -----------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Grocery AI Assistant", "status": "ok"})


@app.route("/ai", methods=["POST"])
def ai_endpoint():
    try:
        init_session()
        data = request.get_json(silent=True) or {}
        user_prompt = (data.get("user_prompt", "") or "").strip()
        if not user_prompt:
            return jsonify({"success": False, "error": "user_prompt required"}), 400

        print("\n" + "=" * 60)
        print(f"📥 NEW REQUEST - Session: {session['session_id'][:8]}")
        print(f"📝 User prompt: {user_prompt}")
        print(f"🛒 Current cart before: {len(session['shopping_cart']['items'])} items")

        # store user message in history
        session["chat_history"].append({
            "role": "user",
            "message": user_prompt,
            "timestamp": datetime.now().isoformat()
        })

        user_lower = user_prompt.lower()

        # detect cart inquiry intent
        cart_query_patterns = [
            r'what.*in.*my.*cart',
            r'what.*in.*the.*cart',
            r'what.*are.*in.*my.*cart',
            r'what.*items.*in.*my.*cart',
            r'list.*cart',
            r'show.*cart'
        ]
        is_cart_query = any(re.search(pat, user_lower) for pat in cart_query_patterns)

        cart_update_msg = ""
        cart_item, cart_quantity = extract_cart_info_from_prompt(user_prompt)
        wants_to_order = any(k in user_lower for k in [
            "yes", "add", "order", "i want", "put in cart", "add to cart",
            "please add", "add it", "i need", "give me", "put it", "include", "buy", "purchase", "get me"
        ])

        if is_cart_query:
            cart = session.get("shopping_cart", {})
            items = cart.get("items", [])
            if not items:
                ai_text = "Your cart is empty."
            else:
                lines = []
                for it in items:
                    qty = int(it.get("quantity", 1))
                    price = float(it.get("price", 0))
                    total = float(it.get("total", price * qty))
                    lines.append(f"- {qty}kg {it.get('item', 'Unknown')} - Rs{price} x {qty} = Rs{total}")
                lines_text = "\n".join(lines)
                ai_text = f"Here are the items in your cart:\n{lines_text}\nSubtotal: Rs{cart.get('subtotal', 0)}"
        else:
            if wants_to_order and cart_item:
                success, msg = update_shopping_cart("add", cart_item, cart_quantity)
                if success:
                    cart_update_msg = f"Added {cart_quantity}kg of {cart_item} to your shopping cart."
                    session["user_context"]["last_order_items"].append({
                        "item": cart_item,
                        "quantity": cart_quantity,
                        "timestamp": datetime.now().isoformat()
                    })
                    if len(session["user_context"]["last_order_items"]) > 10:
                        session["user_context"]["last_order_items"] = session["user_context"]["last_order_items"][-10:]

            grocery_context = json.dumps(grocery_prices, indent=2)
            conversation_context = build_conversation_context()
            prompt_for_model = f"""You are GroceryBot.
Grocery prices: {grocery_context}
Context: {conversation_context}
User: "{user_prompt}"
Respond concisely.
"""

            ai_text = "(no model configured)"
            if model:
                try:
                    response = model.generate_content(
                        prompt_for_model,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.6,
                            top_p=0.9,
                            top_k=40,
                            max_output_tokens=300,
                        )
                    )
                    ai_text = response.text
                except Exception as e:
                    print("Model generation error:", e)
                    ai_text = "Sorry, I couldn't generate a response right now."
            else:
                if any(w in user_lower for w in ["price", "cost", "how much", "rate"]):
                    item_candidate, _ = extract_cart_info_from_prompt(user_prompt)
                    if item_candidate:
                        price, _ = get_item_price(item_candidate)
                        if price:
                            ai_text = f"{item_candidate.capitalize()} costs Rs{price} per kg. Would you like to add it to the cart?"
                        else:
                            ai_text = f"Sorry, I don't have a price for {item_candidate}."
                    else:
                        ai_text = "Which item would you like the price for?"
                else:
                    if cart_update_msg:
                        ai_text = f"{cart_update_msg} I've updated your cart."
                    else:
                        ai_text = f"I heard: {user_prompt}"

        cleaned = clean_text(ai_text)
        if cart_update_msg:
            cleaned = cart_update_msg + "\n\n" + cleaned

        # log assistant message
        session["chat_history"].append({
            "role": "assistant",
            "message": cleaned,
            "timestamp": datetime.now().isoformat()
        })

        session.modified = True
        save_session_to_file()

        print(f"📤 AI Response: {cleaned[:200]}...")
        print(f"🛒 Current cart after: {len(session['shopping_cart']['items'])} items")
        print("=" * 60)

        return jsonify({
            "success": True,
            "response": cleaned,
            "session_id": session["session_id"],
            "cart_summary": {
                "total_items": session["shopping_cart"]["total_items"],
                "subtotal": session["shopping_cart"]["subtotal"],
                "items": session["shopping_cart"]["items"],
                "item_count": len(session["shopping_cart"]["items"])
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/cart", methods=["GET"])
def get_cart():
    init_session()
    session.modified = True
    return jsonify({
        "success": True,
        "session_id": session["session_id"],
        "cart": session["shopping_cart"],
        "currency": "INR"
    })


@app.route("/cart/add", methods=["POST"])
def add_to_cart_route():
    try:
        init_session()
        data = request.get_json(silent=True) or {}
        item_name = data.get("item_name")
        quantity = int(data.get("quantity", 1))
        if not item_name:
            return jsonify({"success": False, "error": "item_name required"}), 400
        success, msg = update_shopping_cart("add", item_name, quantity)
        session.modified = True
        save_session_to_file()
        if success:
            return jsonify({"success": True, "message": msg, "cart": session["shopping_cart"]})
        else:
            return jsonify({"success": False, "error": msg}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/cart/clear", methods=["POST"])
def clear_cart_route():
    init_session()
    success, msg = update_shopping_cart("clear")
    session.modified = True
    save_session_to_file()
    return jsonify({"success": success, "message": msg})


@app.route("/download-pdf", methods=["GET"])
def download_pdf():
    try:
        init_session()
        cart = session.get("shopping_cart", {})
        chat_history = session.get("chat_history", [])

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, safe_text("Grocery Assistant Summary"), ln=True, align="C")
        pdf.ln(6)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, safe_text(f"Session: {session['session_id']}"), ln=True)
        pdf.ln(4)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, safe_text(f"Cart Items ({len(cart.get('items', []))}):"), ln=True)
        pdf.set_font("Arial", "", 11)
        total = 0.0
        for it in cart.get("items", []):
            item_total = float(it.get("total", it.get("price", 0) * it.get("quantity", 1)))
            total += item_total
            # ASCII-friendly line: '-' instead of bullet, 'Rs' instead of rupee symbol
            item_name = safe_text(it.get('item', 'Unknown'))
            price = it.get('price', 0)
            qty = it.get('quantity', 1)
            line = f"- {item_name} - Rs{price} x {qty} = Rs{item_total}"
            pdf.multi_cell(0, 7, safe_text(line))
        pdf.ln(4)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, safe_text(f"Subtotal: Rs{cart.get('subtotal',0)}"), ln=True)
        pdf.ln(8)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, safe_text("Recent Chat History:"), ln=True)
        pdf.ln(4)
        pdf.set_font("Arial", "", 11)
        for msg in chat_history[-20:]:
            role = safe_text(msg.get("role", "").capitalize())
            text = safe_text(msg.get("message", ""))
            pdf.multi_cell(0, 7, safe_text(f"{role}: {text}"))

        tmp = tempfile.NamedTemporaryFile(delete=False, dir="./tmp_pdfs", suffix=".pdf")
        tmp.close()
        pdf.output(tmp.name)
        filename = tmp.name

        try:
            meta = {"generated_pdf": os.path.basename(filename), "generated_at": datetime.now().isoformat()}
            ss = os.path.join("saved_sessions", f"{session['session_id']}.json")
            if os.path.exists(ss):
                with open(ss, "r+") as fh:
                    data = json.load(fh)
                    data.setdefault("generated_files", []).append(meta)
                    fh.seek(0)
                    json.dump(data, fh, indent=2, default=str)
                    fh.truncate()
        except Exception as e:
            print("Could not append PDF metadata to session file:", e)

        return send_file(filename, as_attachment=True, download_name=f"grocery-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf", mimetype="application/pdf")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/history", methods=["GET"])
def get_history():
    init_session()
    return jsonify({"success": True, "session_id": session["session_id"], "history": session.get("chat_history", [])})


@app.route("/session/reset", methods=["POST"])
def reset_session():
    session.clear()
    init_session()
    return jsonify({"success": True, "message": "Session reset", "session_id": session["session_id"]})


if __name__ == "__main__":
    print("=" * 70)
    print("Grocery Assistant API starting")
    print(f"Session dir: {app.config['SESSION_FILE_DIR']}")
    print("Saved sessions dir: ./saved_sessions")
    print("PDFs dir: ./tmp_pdfs")
    print("=" * 70)
    app.run(debug=True, host="0.0.0.0", port=5000)
