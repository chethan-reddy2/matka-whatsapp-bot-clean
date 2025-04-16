import os
import csv
import datetime
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps
from geopy.distance import geodesic

app = Flask(__name__)

# -------------------- TWILIO CONFIG --------------------
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
KITCHEN_WHATSAPP = 'whatsapp:+917671011599'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# -------------------- GOOGLE MAPS --------------------
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}
BRANCH_LINKS = {
    "Kondapur": "https://maps.app.goo.gl/Wq5HzkrkKkcU32a76",
    "Madhapur": "https://maps.app.goo.gl/UNwQXhSamJLEmbNu5",
    "Manikonda": "https://maps.app.goo.gl/t1axqwpx2WxRDmFK6"
}

# -------------------- CSV LOGGING --------------------
def save_order_to_csv(phone, items, address, timestamp):
    with open("orders.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([phone, "; ".join(items), address, timestamp])

def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# -------------------- MENU ITEMS --------------------
menu_items = {
    "1": ("Fruit Custard (220g)", 120),
    "2": ("Nutty Custard Ice Cream (220g)", 100),
    "3": ("Apricot Delight (220g)", 170),
    "4": ("Fruit Pop Mini Oatmeal (220g)", 140),
    "5": ("Choco Banana Oatmeal (320g)", 180),
    "6": ("Classic Custard Bowl (250ml)", 90),
    "7": ("Watermelon Juice (300ml)", 129)
}

# -------------------- USER STATE --------------------
user_states = {}

# -------------------- ROUTES --------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    resp = MessagingResponse()
    msg = resp.message()
    state = user_states.get(from_number, {"step": "start", "cart": []})

    # Greeting template
    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        try:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                content_sid="HXb044cc05b74e2472d4c5838d94c8c6c4"  # fruitcustard_greeting
            )
        except:
            msg.body("👋 Welcome to *Fruit Custard*! Please share your location to begin.")
        state["step"] = "awaiting_location"
        user_states[from_number] = state
        return str(resp)

    # Location
    if state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                geo = gmaps.geocode(incoming_msg)
                loc = geo[0]['geometry']['location']
                user_coords = (loc['lat'], loc['lng'])

            for branch, coords in BRANCHES.items():
                distance = geodesic(coords, user_coords).km
                if distance <= 2:
                    state["branch"] = branch
                    state["step"] = "awaiting_menu_selection"
                    user_states[from_number] = state

                    try:
                        twilio_client.messages.create(
                            from_=WHATSAPP_FROM,
                            to=from_number,
                            content_sid="HXe5ce9a647ed912eb5c398e2ccd15fac3"  # fruitcustard_ordering
                        )
                    except:
                        msg.body(
                            f"✅ You're within our delivery zone from *{branch}*! Type '1' to view menu."
                        )
                    return str(resp)

            msg.body("❌ Sorry, we don't deliver to your area yet. We'll notify you once we do!")
            save_unserviceable_user(from_number)
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Please try again.")
            return str(resp)

    # Menu
    if incoming_msg == "1" and state["step"] == "awaiting_menu_selection":
        menu_text = "\n".join([f"{k}. {v[0]} – ₹{v[1]}" for k, v in menu_items.items()])
        msg.body(f"📋 *Full Menu:*\n{menu_text}\n\n👉 Reply with item numbers (e.g. 1,2) to add to cart.")
        state["step"] = "adding_items"
        user_states[from_number] = state
        return str(resp)

    # Add to cart
    if state["step"] == "adding_items":
        items = incoming_msg.replace(" ", "").split(",")
        added = []
        for i in items:
            if i in menu_items:
                item = menu_items[i]
                state["cart"].append(f"{item[0]} – ₹{item[1]}")
                added.append(item[0])
        total = sum([int(i.split("₹")[-1]) for i in state["cart"]])
        msg.body(
            f"✅ Added: {', '.join(added)}\n🛒 Your cart has {len(state['cart'])} item(s).\n\n"
            f"💰 Total: ₹{total}\n\n"
            "Reply:\n1️⃣ View Cart\n2️⃣ Menu\n3️⃣ Main Menu\n4️⃣ Checkout\n5️⃣ Clear Cart\n6️⃣ Edit Cart"
        )
        user_states[from_number] = state
        return str(resp)

    # View Cart
    if incoming_msg == "1" and state["step"] in ["awaiting_menu_selection", "adding_items"]:
        total = sum([int(i.split("₹")[-1]) for i in state["cart"]])
        items = "\n".join([f"- {item}" for item in state["cart"]])
        msg.body(
            f"📟 *Your Cart:*\n{items}\n\n💰 Total: ₹{total}\n\n"
            "Reply:\n1️⃣ View Cart\n2️⃣ Menu\n3️⃣ Main Menu\n4️⃣ Checkout\n5️⃣ Clear Cart\n6️⃣ Edit Cart"
        )
        return str(resp)

    # Clear Cart
    if incoming_msg == "5":
        user_states[from_number] = {"step": "start", "cart": []}
        msg.body("🧹 Cart cleared.\n\n👋 Welcome to *Fruit Custard*! Please share your location to begin.")
        return str(resp)

    # Edit Cart
    if incoming_msg == "6":
        cart_items = state["cart"]
        if not cart_items:
            msg.body("❌ Your cart is empty.")
            return str(resp)
        item_list = "\n".join([f"{idx+1}. {val}" for idx, val in enumerate(cart_items)])
        msg.body(f"📝 Reply with the item number you want to remove:\n{item_list}")
        state["step"] = "edit_cart"
        user_states[from_number] = state
        return str(resp)

    if state["step"] == "edit_cart":
        try:
            index = int(incoming_msg) - 1
            removed = state["cart"].pop(index)
            msg.body(f"🗑️ Removed: {removed}")
        except:
            msg.body("⚠️ Invalid input.")
        state["step"] = "awaiting_menu_selection"
        user_states[from_number] = state
        return str(resp)

    # Checkout
    if incoming_msg == "4":
        msg.body("🚀 *Checkout Options:*\n1️⃣ Pickup\n2️⃣ Delivery\n3️⃣ View Cart\n4️⃣ Menu\n5️⃣ Main Menu")
        state["step"] = "awaiting_delivery_option"
        user_states[from_number] = state
        return str(resp)

    if state["step"] == "awaiting_delivery_option":
        if incoming_msg == "1":
            branch = state["branch"]
            link = BRANCH_LINKS.get(branch, "")
            msg.body(
                f"🛍️ Please collect your order in 10–15 mins from *{branch}*.\n📍 Location: {link}\nThank you! 🙏"
            )
            try:
                twilio_client.messages.create(
                    body=f"📢 *Pickup Order Received!*\n📞 {from_number}\n🏬 {branch}\n🛒 {', '.join(state['cart'])}",
                    from_=WHATSAPP_FROM,
                    to=KITCHEN_WHATSAPP
                )
            except Exception as e:
                print("Twilio pickup alert failed:", e)
            user_states[from_number] = {"step": "start", "cart": []}
            return str(resp)

        if incoming_msg == "2":
            msg.body("📮 Please send your *delivery address*:")
            state["step"] = "awaiting_address"
            user_states[from_number] = state
            return str(resp)

    if state["step"] == "awaiting_address":
        address = incoming_msg
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            twilio_client.messages.create(
                body=f"📢 *Delivery Order Received!*\n📞 {from_number}\n📍 {address}\n🛒 {', '.join(state['cart'])}",
                from_=WHATSAPP_FROM,
                to=KITCHEN_WHATSAPP
            )
        except Exception as e:
            print("Twilio delivery alert failed:", e)

        save_order_to_csv(from_number, state["cart"], address, timestamp)
        msg.body(f"✅ Your order is confirmed!\n🚚 Will be delivered to: {address}\nThank you! 🙏")
        user_states[from_number] = {"step": "start", "cart": []}
        return str(resp)

    msg.body("🤖 Invalid option. Type 'hi' to start again.")
    return str(resp)

# -------------------- CSV DOWNLOAD --------------------
@app.route("/download-orders", methods=["GET"])
def download_orders():
    return send_file("orders.csv", as_attachment=True)

# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
