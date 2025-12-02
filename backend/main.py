import os
import json
import re
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session  # Add this for server-side sessions
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Enhanced session configuration for better persistence
app.config.update(
    SECRET_KEY=os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-this-123'),
    SESSION_TYPE='filesystem',  # Store sessions on filesystem for persistence
    SESSION_FILE_DIR='./flask_session',
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=1800,  # 30 minutes
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY=True,
)

# Initialize extensions
Session(app)
CORS(app, supports_credentials=True, origins=['http://localhost:3000', 'http://localhost:5000'])

# Configure Gemini API
GEMINI_API_KEY = os.getenv('AIzaSyAZsWgbaXXPmmzrvYthzl-aDwaUI4SXJ8U')
if not GEMINI_API_KEY:
    raise ValueError("❌ Please set GEMINI_API_KEY in your .env file")

# Initialize Gemini model
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# Load grocery prices
try:
    with open('grocery_prices.json', 'r') as f:
        grocery_prices = json.load(f)
    print("✅ Grocery prices loaded successfully")
except FileNotFoundError:
    print("⚠️  grocery_prices.json not found. Creating a sample file...")
    grocery_prices = {
        "fruits": {
            "apple": 80, "banana": 40, "orange": 60, "mango": 120, "grapes": 100,
            "watermelon": 50, "pineapple": 70, "strawberry": 200, "pomegranate": 150, "kiwi": 90
        },
        "vegetables": {
            "potato": 30, "tomato": 40, "onion": 25, "carrot": 35, "cabbage": 20,
            "spinach": 25, "broccoli": 80, "cauliflower": 60, "capsicum": 70, "cucumber": 20
        },
        "dairy": {
            "milk": 60, "cheese": 300, "butter": 100, "yogurt": 50, "eggs": 80
        },
        "grains": {
            "rice": 80, "wheat": 40, "oats": 120, "pasta": 60, "bread": 40
        },
        "other": {
            "sugar": 45, "salt": 20, "oil": 180, "coffee": 300, "tea": 200
        }
    }
    with open('grocery_prices.json', 'w') as f:
        json.dump(grocery_prices, f, indent=2)

# Initialize session data structure
def init_session():
    """Initialize session data if not exists"""
    session.permanent = True
    
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        session['chat_history'] = []
        session['shopping_cart'] = {
            'items': [],  # List of {item: '', quantity: 0, price: 0, total: 0}
            'subtotal': 0,
            'total_items': 0,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        session['user_context'] = {
            'name': '',
            'last_order_items': [],
            'preferences': {}
        }
        print(f"🆕 New session created: {session['session_id']}")
    else:
        print(f"📋 Existing session: {session['session_id']}")
        print(f"🛒 Cart items: {len(session.get('shopping_cart', {}).get('items', []))}")
        print(f"💬 Chat history: {len(session.get('chat_history', []))} messages")

def clean_text(text):
    """Remove unwanted characters and clean the text"""
    text = re.sub(r'\*\*|\*|__|_|#|`|~|```|```python|\n{2,}', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\S+@\S+', '', text)
    text = re.sub(r'\.{2,}', '.', text)
    return text.strip()

def get_item_price(item_name):
    """Search for item price in grocery database"""
    item_name_lower = item_name.lower().strip()
    
    # Search in all categories
    for category, items in grocery_prices.items():
        if item_name_lower in items:
            return items[item_name_lower], category
    
    # Try partial match
    for category, items in grocery_prices.items():
        for item in items:
            if item_name_lower in item or item in item_name_lower:
                return items[item], category
    
    return None, None

def update_shopping_cart(action, item_name=None, quantity=1):
    """Update shopping cart based on action"""
    init_session()  # Ensure session is initialized
    
    cart = session['shopping_cart']
    
    if action == 'add':
        price, category = get_item_price(item_name)
        if price:
            # Check if item already in cart
            item_found = False
            for i, cart_item in enumerate(cart['items']):
                if cart_item['item'].lower() == item_name.lower():
                    cart['items'][i]['quantity'] += quantity
                    cart['items'][i]['total'] = cart['items'][i]['quantity'] * cart['items'][i]['price']
                    item_found = True
                    break
            
            if not item_found:
                cart['items'].append({
                    'item': item_name,
                    'quantity': quantity,
                    'price': price,
                    'category': category,
                    'total': price * quantity
                })
            
            # Update totals
            cart['subtotal'] = sum(item['total'] for item in cart['items'])
            cart['total_items'] = sum(item['quantity'] for item in cart['items'])
            cart['last_updated'] = datetime.now().isoformat()
            
            # Force session save
            session.modified = True
            
            return True, f"Added {quantity}kg of {item_name} to cart"
        else:
            return False, f"Item '{item_name}' not found in inventory"
    
    elif action == 'clear':
        cart['items'] = []
        cart['subtotal'] = 0
        cart['total_items'] = 0
        cart['last_updated'] = datetime.now().isoformat()
        session.modified = True
        return True, "Cart cleared"
    
    elif action == 'view':
        return True, cart
    
    return False, "Invalid action"

def build_conversation_context():
    """Build context for AI including chat history and cart"""
    init_session()
    
    # Format chat history
    chat_history_text = ""
    if session['chat_history']:
        last_5_messages = session['chat_history'][-5:]
        for msg in last_5_messages:
            role = "User" if msg['role'] == 'user' else "Assistant"
            chat_history_text += f"{role}: {msg['message'][:100]}\n"
    
    # Format cart items
    cart_items_text = ""
    if session['shopping_cart']['items']:
        for item in session['shopping_cart']['items']:
            cart_items_text += f"- {item['quantity']}kg {item['item']} @ ₹{item['price']}/kg = ₹{item['total']}\n"
    else:
        cart_items_text = "Cart is empty"
    
    context = f"""=== CONVERSATION HISTORY (Last 5 messages) ===
{chat_history_text if chat_history_text else "No previous conversation"}

=== CURRENT SHOPPING CART ===
{cart_items_text}
Total Items: {session['shopping_cart']['total_items']}
Subtotal: ₹{session['shopping_cart']['subtotal']}

=== USER CONTEXT ===
Last ordered items: {[item.get('item', '') for item in session['user_context']['last_order_items'][-3:]]}
"""
    return context

def extract_cart_info_from_prompt(user_prompt):
    """Extract item and quantity from user prompt"""
    user_lower = user_prompt.lower()
    
    # Try to extract quantity and item
    quantity = 1
    item_name = None
    
    # Pattern: "1kg of banana", "2 kg apples", "500g mango"
    patterns = [
        r'(\d+)\s*(?:kg|kilos?|kilograms?|g|grams?)?\s+(?:of\s+)?(\w+)',
        r'(\d+)\s*(\w+)(?:\s+please)?',
        r'i want\s+(\d+)?\s*(\w+)',
        r'add\s+(\d+)?\s*(\w+)\s+to',
        r'order\s+(\d+)?\s*(\w+)'
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
    
    # If no quantity found, check for common items
    if not item_name:
        for item in grocery_prices['fruits']:
            if item in user_lower:
                item_name = item
                break
        if not item_name:
            for item in grocery_prices['vegetables']:
                if item in user_lower:
                    item_name = item
                    break
    
    return item_name, quantity

@app.route('/ai', methods=['POST'])
def ai_response():
    """Handle AI requests with chat history and shopping cart"""
    try:
        # Initialize session
        init_session()
        
        # Get user prompt
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        user_prompt = data.get('user_prompt', '').strip()
        if not user_prompt:
            return jsonify({'success': False, 'error': 'user_prompt is required'}), 400
        
        print(f"\n{'='*60}")
        print(f"📥 NEW REQUEST - Session: {session['session_id'][:8]}")
        print(f"📝 User prompt: {user_prompt}")
        print(f"🛒 Current cart before: {len(session['shopping_cart']['items'])} items")
        
        # Add user message to chat history
        session['chat_history'].append({
            'role': 'user',
            'message': user_prompt,
            'timestamp': datetime.now().isoformat()
        })
        
        # Extract item and quantity from prompt
        cart_item, cart_quantity = extract_cart_info_from_prompt(user_prompt)
        
        # Check if user wants to add item to cart
        user_lower = user_prompt.lower()
        wants_to_order = any(word in user_lower for word in [
            'yes', 'add', 'order', 'i want', 'put in cart', 'add to cart',
            'please add', 'add it', 'i need', 'give me', 'take', 'put it',
            'include', 'buy', 'purchase', 'get me'
        ]) or 'i want' in user_lower
        
        is_price_query = any(word in user_lower for word in [
            'price', 'cost', 'how much', 'what is the price', 'rate'
        ])
        
        is_cart_query = any(word in user_lower for word in [
            'cart', 'what is in', 'what do i have', 'my order', 'my items',
            'total', 'how much do i owe', 'what is my total'
        ])
        
        # Handle cart operations BEFORE AI response
        cart_update_msg = ""
        if wants_to_order and cart_item:
            success, message = update_shopping_cart('add', cart_item, cart_quantity)
            if success:
                cart_update_msg = f"\n✅ Added {cart_quantity}kg of {cart_item} to your shopping cart."
                
                # Update user context with last ordered item
                session['user_context']['last_order_items'].append({
                    'item': cart_item,
                    'quantity': cart_quantity,
                    'timestamp': datetime.now().isoformat()
                })
                # Keep only last 10 items
                if len(session['user_context']['last_order_items']) > 10:
                    session['user_context']['last_order_items'] = session['user_context']['last_order_items'][-10:]
        
        # Build complete context for AI
        grocery_context = json.dumps(grocery_prices, indent=2)
        conversation_context = build_conversation_context()
        
        # Prepare the prompt for Gemini with updated cart info
        prompt = f"""You are GroceryBot, a helpful grocery store assistant and shopping cart manager.

=== IMPORTANT: YOU MANAGE A SHOPPING CART ===
- When user asks about prices: Provide price and ask if they want to add to cart
- When user confirms ordering (says yes, add, want, etc.): Add item to cart
- When user asks about cart: Show ALL items with quantities and totals
- When user asks about total: Calculate and show subtotal

=== GROCERY PRICES (INR per kg/unit) ===
{grocery_context}

=== CURRENT CONTEXT ===
{conversation_context}

=== USER'S CURRENT MESSAGE ===
"{user_prompt}"

=== YOUR RESPONSE RULES ===
1. ALWAYS check the conversation history above
2. If user asks about an item price:
   - Give exact price from list
   - Ask: "Would you like to add this to your cart?"
3. If user confirms (says yes, add, want, etc.):
   - Acknowledge item added to cart (even if already added by system)
   - Mention cart status
4. If user asks "what's in my cart?" or "total price":
   - List ALL items with quantity and price
   - Show subtotal: ₹{session['shopping_cart']['subtotal']}
   - Ask if they want to checkout or add more
5. Keep responses friendly and conversational
6. NEVER say cart is empty if it has items

=== CURRENT CART STATUS ===
Items in cart: {[f"{item['item']} ({item['quantity']}kg)" for item in session['shopping_cart']['items']]}
Subtotal: ₹{session['shopping_cart']['subtotal']}

Now respond to the user's message appropriately:"""
        
        print("🤖 Generating AI response...")
        
        # Get response from Gemini
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                max_output_tokens=350,
            )
        )
        
        ai_text = response.text
        cleaned_text = clean_text(ai_text)
        
        # If we had a cart update, prepend it to AI response
        if cart_update_msg:
            cleaned_text = cart_update_msg + "\n\n" + cleaned_text
        
        print(f"📤 AI Response: {cleaned_text[:200]}...")
        print(f"🛒 Current cart after: {len(session['shopping_cart']['items'])} items")
        print(f"{'='*60}")
        
        # Add AI response to chat history
        session['chat_history'].append({
            'role': 'assistant',
            'message': cleaned_text,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep chat history manageable (last 20 messages)
        if len(session['chat_history']) > 20:
            session['chat_history'] = session['chat_history'][-20:]
        
        # Force save session
        session.modified = True
        
        # Return response
        return jsonify({
            'success': True,
            'response': cleaned_text,
            'original_prompt': user_prompt,
            'session_id': session['session_id'],
            'cart_summary': {
                'total_items': session['shopping_cart']['total_items'],
                'subtotal': session['shopping_cart']['subtotal'],
                'items': session['shopping_cart']['items'],
                'item_count': len(session['shopping_cart']['items'])
            }
        })
        
    except Exception as e:
        print(f"❌ Error in /ai endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to generate AI response'
        }), 500

@app.route('/cart', methods=['GET'])
def get_cart():
    """Get current shopping cart"""
    init_session()
    return jsonify({
        'success': True,
        'session_id': session['session_id'],
        'cart': session['shopping_cart'],
        'currency': 'INR'
    })

@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    """Manually add item to cart"""
    try:
        init_session()
        data = request.get_json()
        item_name = data.get('item_name')
        quantity = data.get('quantity', 1)
        
        if not item_name:
            return jsonify({'success': False, 'error': 'item_name is required'}), 400
        
        success, message = update_shopping_cart('add', item_name, quantity)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'cart': session['shopping_cart']
            })
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cart/clear', methods=['POST'])
def clear_cart():
    """Clear shopping cart"""
    init_session()
    success, message = update_shopping_cart('clear')
    return jsonify({'success': success, 'message': message})

@app.route('/cart/checkout', methods=['POST'])
def checkout():
    """Checkout and generate order summary"""
    init_session()
    
    if not session['shopping_cart']['items']:
        return jsonify({'success': False, 'error': 'Cart is empty'}), 400
    
    # Create order summary
    order_id = str(uuid.uuid4())[:8].upper()
    order_summary = {
        'order_id': order_id,
        'items': session['shopping_cart']['items'].copy(),
        'subtotal': session['shopping_cart']['subtotal'],
        'tax': round(session['shopping_cart']['subtotal'] * 0.18, 2),  # 18% GST
        'total': round(session['shopping_cart']['subtotal'] * 1.18, 2),
        'timestamp': datetime.now().isoformat(),
        'status': 'completed'
    }
    
    # Calculate total
    order_summary['total'] = order_summary['subtotal'] + order_summary['tax']
    
    # Store order in user context
    if 'orders' not in session['user_context']:
        session['user_context']['orders'] = []
    session['user_context']['orders'].append(order_summary)
    
    # Clear cart after checkout
    update_shopping_cart('clear')
    
    # Force save session
    session.modified = True
    
    return jsonify({
        'success': True,
        'message': f'Order #{order_id} completed successfully',
        'order': order_summary
    })

@app.route('/history', methods=['GET'])
def get_chat_history():
    """Get chat history"""
    init_session()
    return jsonify({
        'success': True,
        'session_id': session['session_id'],
        'history': session['chat_history'],
        'total_messages': len(session['chat_history'])
    })

@app.route('/session/reset', methods=['POST'])
def reset_session():
    """Reset user session"""
    session.clear()
    init_session()
    return jsonify({
        'success': True,
        'message': 'Session reset successfully',
        'new_session_id': session['session_id']
    })

@app.route('/session/info', methods=['GET'])
def session_info():
    """Get session information"""
    init_session()
    return jsonify({
        'success': True,
        'session_id': session['session_id'],
        'cart_items': len(session['shopping_cart']['items']),
        'chat_messages': len(session['chat_history']),
        'session_age': 'Active'
    })

@app.route('/prices', methods=['GET'])
def get_prices():
    """Return the grocery prices"""
    return jsonify({
        'success': True,
        'data': grocery_prices,
        'currency': 'INR',
        'last_updated': 'current'
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Grocery AI Assistant with Cart',
        'model': 'gemini-2.0-flash',
        'session_type': 'persistent',
        'items_in_inventory': sum(len(items) for items in grocery_prices.values())
    })

@app.route('/test/cart', methods=['GET'])
def test_cart_flow():
    """Test the cart persistence"""
    init_session()
    
    # Add some test items
    test_items = [
        ('banana', 1),
        ('apple', 2),
        ('milk', 1)
    ]
    
    results = []
    for item, qty in test_items:
        success, msg = update_shopping_cart('add', item, qty)
        results.append({
            'item': item,
            'quantity': qty,
            'success': success,
            'message': msg
        })
    
    return jsonify({
        'success': True,
        'test': 'Cart persistence test',
        'results': results,
        'final_cart': session['shopping_cart']
    })

@app.route('/', methods=['GET'])
def home():
    """Home page with API documentation"""
    return jsonify({
        'message': 'Grocery AI Shopping Assistant API',
        'version': '2.1',
        'features': [
            'AI-powered grocery assistant with memory',
            'Persistent shopping cart across requests',
            'Chat history maintained in session',
            'Automatic cart updates based on conversation',
            'Order checkout system'
        ],
        'endpoints': {
            'POST /ai': 'Chat with AI assistant (main endpoint) - maintains cart',
            'GET /cart': 'View current shopping cart',
            'POST /cart/add': 'Manually add item to cart',
            'GET /history': 'View chat history',
            'GET /session/info': 'Check session status'
        },
        'how_to_use': [
            '1. Ask about prices: "What is the price of banana?"',
            '2. Order items: "I want 1kg of banana" or "Yes, add it to cart"',
            '3. Check cart: "What is in my cart?" or "What is my total?"',
            '4. Cart persists across all your requests'
        ],
        'model': 'gemini-2.0-flash',
        'currency': 'INR'
    })

if __name__ == '__main__':
    # Create session directory
    os.makedirs('./flask_session', exist_ok=True)
    
    print("=" * 70)
    print("🛒 SMART GROCERY SHOPPING ASSISTANT (PERSISTENT CART)")
    print("=" * 70)
    print(f"🔑 API Key: {'✅ Configured' if GEMINI_API_KEY else '❌ NOT SET'}")
    print(f"🤖 Model: gemini-2.0-flash")
    print(f"📊 Inventory: {sum(len(items) for items in grocery_prices.values())} items")
    print(f"💾 Session storage: Filesystem (./flask_session/)")
    print(f"🌐 Server: http://localhost:5000")
    print("=" * 70)
    print("🎯 KEY FEATURES:")
    print("  • Cart persists across all requests")
    print("  • AI remembers previous conversations")
    print("  • Automatic cart updates when user says 'I want X'")
    print("  • Real-time cart tracking")
    print("=" * 70)
    print("📚 SAMPLE CONVERSATION FLOW:")
    print("  1. User: 'What is the price of banana?'")
    print("  2. AI: 'Banana is ₹40/kg. Add to cart?'")
    print("  3. User: 'Yes, add 1kg'")
    print("  4. AI: '✅ Added 1kg banana to cart'")
    print("  5. User: 'What is in my cart?'")
    print("  6. AI: 'You have: 1kg banana (₹40). Total: ₹40'")
    print("=" * 70)
    
    app.run(debug=True, host='0.0.0.0', port=5000)