import os
import csv
import uuid
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic
import datetime
import threading
from twilio.rest import Client

app = Flask(__name__)

# --------------------- TWILIO CONFIG -----------------------
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
KITCHEN_WHATSAPP = 'whatsapp:+917671011599'
MANAGER_WHATSAPP = 'whatsapp:+918885112242'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# --------------------- GOOGLE MAPS -----------------------
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

# --------------------- CSV LOGGER -----------------------
def log_interaction(phone, message, step):
    with open("interactions.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone, message, step])

def save_order_to_csv(order_id, phone, item, address, timestamp, status):
    try:
        with open("orders.csv", mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([order_id, phone, "; ".join(item), address, timestamp, status])
    except Exception as e:
        print("CSV logging error:", e)

def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

user_states = {}
order_mapping = {}
menu_items = {
    "1": ("Fruit Custard (220g)", 120),
    "2": ("Nutty Custard Ice Cream (220g)", 100),
    "3": ("Apricot Delight (220g)", 170),
    "4": ("Fruit Pop Mini Oatmeal (220g)", 140),
    "5": ("Choco Banana Oatmeal (320g)", 180),
    "6": ("Classic Custard Bowl (250ml)", 90),
    "7": ("Watermelon Juice (300ml)", 129)
}

def send_feedback_reminder(to):
    def delayed():
        import time
        time.sleep(3600)
        try:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=to,
                body="🙏 Hope you enjoyed your order! We'd love your feedback. Please reply with a rating (1–5) and any suggestions."
            )
        except Exception as e:
            print("Feedback message error:", e)
    threading.Thread(target=delayed).start()

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    state = user_states.get(from_number, {"step": "start", "cart": []})
    log_interaction(from_number, incoming_msg, state.get("step", "unknown"))

    resp = MessagingResponse()
    msg = resp.message()

    # Kitchen update
    if from_number == KITCHEN_WHATSAPP:
        if incoming_msg.startswith("#ord"):
            try:
                parts = incoming_msg.split()
                order_id, status_keyword = parts[0], parts[1].lower()
                status_map = {
                    "preparing": "is now being prepared",
                    "ready": "is ready for pickup",
                    "out": "is out for delivery",
                    "delivered": "has been delivered",
                    "cancel": "has been cancelled"
                }
                if status_keyword in status_map:
                    customer_number = order_mapping.get(order_id.upper())
                    if customer_number:
                        status_message = f"📦 Your order {order_id.upper()} {status_map[status_keyword]}!"
                        twilio_client.messages.create(
                            from_=WHATSAPP_FROM,
                            to=customer_number,
                            body=status_message
                        )
                        msg.body(f"✅ Order update sent to customer: {status_message}")
                        return str(resp)
                    else:
                        msg.body("❌ Order ID not found.")
                        return str(resp)
                else:
                    msg.body("❌ Unknown status keyword.")
                    return str(resp)
            except Exception as e:
                msg.body("❌ Failed to parse status update.")
                print("Kitchen update error:", e)
                return str(resp)

    # Customer flow
    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        msg.body("👋 Welcome to Fruit Custard! Please share your live location or type your area name to check if we deliver to you.")
        user_states[from_number] = {"step": "awaiting_location", "cart": []}
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
                    state["step"] = "awaiting_item"
                    state["branch"] = branch_name
                    msg.body(f"✅ You're within delivery range of our *{branch_name}* branch!\nPlease reply with item numbers to add to your cart.\nType 'menu' to see available items.")
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

    elif state["step"] == "awaiting_item":
        if incoming_msg in menu_items:
            item_name, price = menu_items[incoming_msg]
            state["cart"].append(f"{item_name} ₹{price}")
            msg.body(f"✅ Added *{item_name}* to your cart.\nType another item number or 'cart' to view your cart.")
        elif incoming_msg == "menu":
            menu_text = "\n".join([f"{k}. {v[0]} - ₹{v[1]}" for k, v in menu_items.items()])
            msg.body(f"📋 Menu:\n{menu_text}\n\nReply with item numbers to add.")
        elif incoming_msg == "cart":
            cart_items = "\n".join(state["cart"])
            msg.body(f"🛒 Your cart:\n{cart_items}\nType 'checkout' to place the order or 'menu' to continue.")
        elif incoming_msg == "checkout":
            msg.body("🚚 Delivery or 🏃 Takeaway? Type 'delivery' or 'takeaway'")
            state["step"] = "awaiting_order_type"
        user_states[from_number] = state
        return str(resp)

    elif state["step"] == "awaiting_order_type":
        if incoming_msg == "takeaway":
            order_id = f"#ORD{str(uuid.uuid4())[:6].upper()}"
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cart_total = sum([int(i.split('₹')[-1]) for i in state["cart"]])
            msg.body(f"✅ Order ID {order_id} confirmed for takeaway.\n🛍️ Pick it up in 15 mins from our {state['branch']} branch.\nTotal: ₹{cart_total}")
            try:
                for number in [KITCHEN_WHATSAPP, MANAGER_WHATSAPP]:
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=number,
                        body=f"📢 New Takeaway Order {order_id}!\nFrom: {from_number}\nItems: {', '.join(state['cart'])}"
                    )
            except Exception as e:
                print("Twilio error:", e)
            save_order_to_csv(order_id, from_number, state["cart"], f"Takeaway ({state['branch']})", timestamp, "Takeaway Confirmed")
            order_mapping[order_id] = from_number
            send_feedback_reminder(from_number)
            user_states[from_number] = {"step": "start", "cart": []}
            return str(resp)

        elif incoming_msg == "delivery":
            state["step"] = "awaiting_delivery_address"
            msg.body("📍 Please send your full delivery address.")
            user_states[from_number] = state
            return str(resp)

    elif state["step"] == "awaiting_delivery_address":
        order_id = f"#ORD{str(uuid.uuid4())[:6].upper()}"
        address = incoming_msg
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cart_total = sum([int(i.split('₹')[-1]) for i in state["cart"]]) + 20
        msg.body(f"✅ Order ID {order_id} placed.\n📦 Delivery to: {address}\nTotal incl. ₹20 delivery: ₹{cart_total}\nThank you for ordering!")
        try:
            for number in [KITCHEN_WHATSAPP, MANAGER_WHATSAPP]:
                twilio_client.messages.create(
                    from_=WHATSAPP_FROM,
                    to=number,
                    body=f"📢 New Delivery Order {order_id}!\nFrom: {from_number}\nItems: {', '.join(state['cart'])}\nAddress: {address}"
                )
        except Exception as e:
            print("Twilio error:", e)
        save_order_to_csv(order_id, from_number, state["cart"], address, timestamp, "Delivery Confirmed")
        order_mapping[order_id] = from_number
        send_feedback_reminder(from_number)
        user_states[from_number] = {"step": "start", "cart": []}
        return str(resp)

    else:
        msg.body("🤖 Type 'hi' to start.")
        return str(resp)

@app.route("/download-orders", methods=["GET"])
def download_orders():
    try:
        return send_file("orders.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

@app.route("/download-interactions", methods=["GET"])
def download_interactions():
    try:
        return send_file("interactions.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
