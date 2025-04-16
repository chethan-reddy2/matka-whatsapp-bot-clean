import os
import csv
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic
import datetime
from twilio.rest import Client

app = Flask(__name__)

# --------------------- TWILIO CONFIG -----------------------
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
KITCHEN_WHATSAPP = 'whatsapp:+917671011599'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# --------------------- GOOGLE MAPS -----------------------
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

# --------------------- CSV LOGGER -----------------------
def save_order_to_csv(phone, items, address, timestamp):
    try:
        with open("orders.csv", mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([phone, "; ".join(items), address, timestamp])
    except Exception as e:
        print("CSV logging error:", e)

def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

user_states = {}

# --------------------- MENU ITEMS -----------------------
menu_items = {
    "1": ("Fruit Custard (220g)", 120),
    "2": ("Nutty Custard Ice Cream (220g)", 100),
    "3": ("Apricot Delight (220g)", 170),
    "4": ("Fruit Pop Mini Oatmeal (220g)", 140),
    "5": ("Choco Banana Oatmeal (320g)", 180),
    "6": ("Classic Custard Bowl (250ml)", 90),
    "7": ("Watermelon Juice (300ml)", 129)
}

# --------------------- WHATSAPP ROUTE -----------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    resp = MessagingResponse()
    msg = resp.message()
    state = user_states.get(from_number, {"step": "start", "cart": []})

    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        msg.body("👋 Welcome to Fruit Custard! Please share your live location or area name so we can check if we deliver to you.")
        state = {"step": "awaiting_location", "cart": []}
        user_states[from_number] = state
        return str(resp)

    elif state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                loc_data = gmaps.geocode(incoming_msg)
                if not loc_data:
                    raise Exception("No location found")
                loc = loc_data[0]["geometry"]["location"]
                user_coords = (loc["lat"], loc["lng"])

            for branch_name, branch_coords in BRANCHES.items():
                distance = geodesic(user_coords, branch_coords).km
                if distance <= 2:
                    state["step"] = "awaiting_menu_selection"
                    state["branch"] = branch_name
                    msg.body(f"✅ You're within delivery range of our *{branch_name}* branch!\n\nType 'menu' to view our offerings or select item numbers directly.")
                    user_states[from_number] = state
                    return str(resp)

            save_unserviceable_user(from_number)
            msg.body("❌ Sorry, we don’t deliver to your area yet. We'll notify you once we expand! 🗺️")
            user_states[from_number] = {"step": "start", "cart": []}
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Try again or type your area name.")
        return str(resp)

    elif state["step"] == "awaiting_menu_selection":
        if incoming_msg == "menu":
            menu_text = "\n".join([f"{k}. {v[0]} – ₹{v[1]}" for k, v in menu_items.items()])
            msg.body(f"📋 *Menu:*\n{menu_text}\n\nType item numbers to add to cart (e.g. 1,2,4).")
            return str(resp)

        elif any(x.strip() in menu_items for x in incoming_msg.split(",")):
            added = []
            for item_num in incoming_msg.split(","):
                item_num = item_num.strip()
                if item_num in menu_items:
                    item_name, price = menu_items[item_num]
                    state["cart"].append(f"{item_name} – ₹{price}")
                    added.append(item_name)
            user_states[from_number] = state

            msg.body(f"✅ Added: {', '.join(added)}\n🛒 Your cart has {len(state['cart'])} item(s).\n\nReply with:\n1 - View Cart\n2 - View Menu\n3 - Main Menu\n4 - Checkout\n5 - Clear Cart")
            return str(resp)

        elif incoming_msg == "1":
            if not state["cart"]:
                msg.body("🛒 Your cart is empty. Type 'menu' to view items.")
            else:
                total = sum(int(x.split('₹')[-1]) for x in state["cart"])
                items_text = "\n".join([f"- {item}" for item in state["cart"]])
                msg.body(f"🧾 *Your Cart:*\n{items_text}\n\n💰 Total: ₹{total}\n\nReply with:\n2 - View Menu\n3 - Main Menu\n4 - Checkout\n5 - Clear Cart")
            return str(resp)

        elif incoming_msg == "2":
            menu_text = "\n".join([f"{k}. {v[0]} – ₹{v[1]}" for k, v in menu_items.items()])
            msg.body(f"📋 *Menu:*\n{menu_text}\n\nType item numbers to add to cart.")
            return str(resp)

        elif incoming_msg == "3":
            state["step"] = "start"
            user_states[from_number] = state
            return whatsapp()

        elif incoming_msg == "4":
            msg.body("🚚 Delivery or 🛍️ Pickup? Reply with 'delivery' or 'pickup'.")
            state["step"] = "awaiting_delivery_option"
            user_states[from_number] = state
            return str(resp)

        elif incoming_msg == "5":
            state["cart"] = []
            msg.body("🧹 Cart cleared. Type 'menu' to view items again.")
            user_states[from_number] = state
            return str(resp)

        else:
            msg.body("🤖 Invalid input. Please type menu, item numbers, or use options:\n1 - View Cart\n2 - View Menu\n3 - Main Menu\n4 - Checkout\n5 - Clear Cart")

        user_states[from_number] = state
        return str(resp)

    else:
        msg.body("🤖 Type 'hi' to start.")
        return str(resp)

# --------------------- CSV DOWNLOAD ROUTE -----------------------
@app.route("/download-orders", methods=["GET"])
def download_orders():
    try:
        return send_file("orders.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

# --------------------- RUN -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
