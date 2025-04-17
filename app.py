import os
import csv
import uuid
import re
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps
from geopy.distance import geodesic
import datetime

app = Flask(__name__)

# Twilio Config
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = 'eb7baed508c4da7fac7c5a5d537e5621'
WHATSAPP_FROM = 'whatsapp:+14134145410'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# Google Maps Config
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")

# Branch Info
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}
BRANCH_LINKS = {
    "Kondapur": "https://maps.app.goo.gl/E26sm634cKJmxktH6",
    "Madhapur": "https://maps.app.goo.gl/x5AHBgoh3gMbhUobA",
    "Manikonda": "https://maps.app.goo.gl/FkCU71kfvKY2vrgw9"
}
KITCHEN_NUMBERS = ["+918885112242", "+917671011599"]
SUPPORT_NUMBER = "+91 9640112005"

user_states = {}

# Ensure orders.csv has headers if empty
def ensure_order_csv():
    file_exists = os.path.exists("orders.csv")
    if not file_exists or os.stat("orders.csv").st_size == 0:
        with open("orders.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "Order ID", "Phone", "Name", "Branch", "Order Type", "Address or Pickup", "Latitude", "Longitude", "Timestamp"
            ])

# CSV Utils
def save_order(phone, name, branch, order_type, address, lat, lon):
    ensure_order_csv()
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    with open("orders.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            order_id, phone, name, branch, order_type, address or "Takeaway", lat, lon, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
    return order_id

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip()
    button_text = request.values.get("ButtonText", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    resp = MessagingResponse()
    msg = resp.message()
    state = user_states.get(from_number, {"step": "start"})

    # Track name if user already shared it
    if state.get("step") == "get_name":
        user_states[from_number]["name"] = incoming_msg
        msg.body("✅ Got it! Now please enter your full delivery address:")
        user_states[from_number]["step"] = "awaiting_address"
        return str(resp)

    if incoming_msg.lower() in ["hi", "hello"]:
        user_states[from_number] = {"step": "get_name"}
        msg.body("👋 Hi! Welcome to Fruit Custard. What's your name?")
        return str(resp)

    if state.get("step") == "awaiting_address":
        branch = state.get("branch", "Kondapur")
        name = state.get("name", "Guest")
        lat = state.get("lat", "")
        lon = state.get("lon", "")
        order_id = save_order(from_number, name, branch, "Delivery", incoming_msg, lat, lon)
        msg.body(
            f"✅ Order placed!
📍 Delivery to: {incoming_msg}
🧾 Order ID: {order_id}\n\n📞 For changes, call us at {SUPPORT_NUMBER}"
        )
        for kitchen in KITCHEN_NUMBERS:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=f"whatsapp:{kitchen}",
                body=f"🧾 Delivery Order\nBranch: {branch}\nOrder ID: {order_id}\nAddress: {incoming_msg}\nCustomer: {name}\nPhone: {from_number}"
            )
        user_states[from_number] = {"step": "start"}
        return str(resp)

    if state.get("step") == "awaiting_takeaway_confirm":
        branch = state.get("branch", "Kondapur")
        name = state.get("name", "Guest")
        lat = state.get("lat", "")
        lon = state.get("lon", "")
        order_id = save_order(from_number, name, branch, "Takeaway", "Takeaway", lat, lon)
        msg.body(
            f"🕒 Please pick up in 15 mins from {branch} branch.\n📍 {BRANCH_LINKS[branch]}\n🧾 Order ID: {order_id}\n\n📞 For queries, call us at {SUPPORT_NUMBER}"
        )
        for kitchen in KITCHEN_NUMBERS:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=f"whatsapp:{kitchen}",
                body=f"🧾 Takeaway Order\nBranch: {branch}\nOrder ID: {order_id}\nCustomer: {name}\nPhone: {from_number}"
            )
        user_states[from_number] = {"step": "start"}
        return str(resp)

    # Catch catalog access (for logging)
    if "fruit custard" in incoming_msg.lower() or "menu" in incoming_msg.lower():
        lat = latitude or ""
        lon = longitude or ""
        name = state.get("name", "Guest")
        save_order(from_number, name, "", "Viewed Catalog", "N/A", lat, lon)
        msg.body("🛍️ Enjoy browsing our catalog! Type 'order' when you're ready to place an order.")
        return str(resp)

    # Generic fallback
    msg.body("🤖 Please type 'hi' to start your order.")
    return str(resp)

@app.route("/download-orders")
def download_orders():
    return send_file("orders.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
