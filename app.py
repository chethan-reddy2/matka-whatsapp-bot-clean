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
BRANCH_CONTACTS = {
    "Kondapur": "+91 8885112242",
    "Madhapur": "+91 9640112005",
    "Manikonda": "+91 9182149094"
}
KITCHEN_NUMBERS = ["+918885112242", "+917671011599"]

user_states = {}

# CSV Utils
def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def save_location_info(phone, lat, lon, branch):
    with open("user_locations.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([phone, lat, lon, branch, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def save_order(phone, name, branch, order_type, address=None):
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    with open("orders.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([order_id, phone, name, branch, order_type, address or "Takeaway", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
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

    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to=from_number,
            content_sid="HXe1b289e2a199611ad5b7c864f97a024c"
        )
        user_states[from_number] = {"step": "greeted"}
        return ("", 200)

    if state["step"] == "greeted":
        if incoming_msg in ["1", "order food"]:
            msg.body("📍 Please share your live location or type your area name to check delivery availability.")
            user_states[from_number] = {"step": "awaiting_location"}
            return str(resp)
        elif incoming_msg in ["2", "bulk order", "3", "other query"]:
            msg.body("📲 For bulk orders or queries, message us: https://wa.me/918688641919")
            user_states[from_number] = {"step": "start"}
            return str(resp)
        else:
            msg.body("❓ Reply with:\n1️⃣ Order Food\n2️⃣ Bulk Order\n3️⃣ Other Query")
            return str(resp)

    if state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                loc = gmaps.geocode(incoming_msg)[0]['geometry']['location']
                user_coords = (loc['lat'], loc['lng'])

            for branch, coords in BRANCHES.items():
                if geodesic(user_coords, coords).km <= 2:
                    save_location_info(from_number, user_coords[0], user_coords[1], branch)
                    msg.body(f"🎉 We can deliver to you from {branch} branch. Here's our menu 👇")
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=from_number,
                        content_sid="HX79124164c9b84e23a12f0765425f7e86"
                    )
                    user_states[from_number] = {"step": "catalogue_shown", "branch": branch, "lat": user_coords[0], "lon": user_coords[1]}
                    return str(resp)

            save_unserviceable_user(from_number)
            msg.body("❌ Sorry, we don't deliver to your area yet.")
            user_states[from_number] = {"step": "start"}
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Try typing your area name.")
            return str(resp)

    if state["step"] == "catalogue_shown" and (
        "estimated total" in incoming_msg or
        "view sent cart" in incoming_msg or
        ("₹" in incoming_msg and "item" in incoming_msg) or
        incoming_msg.startswith("1 item")
    ):
        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to=from_number,
            content_sid="HX6a4548eddff22056b5f4727db8ce5dcd"
        )
        user_states[from_number]["step"] = "order_type_selection"
        return ("", 200)

    if state["step"] == "order_type_selection" and button_text in ["delivery", "takeaway"]:
        user_states[from_number]["order_type"] = button_text
        msg.body("🧑 Please enter your name for the order:")
        user_states[from_number]["step"] = "get_name"
        return str(resp)

    if state["step"] == "get_name":
        name = incoming_msg
        branch = user_states[from_number].get("branch", "Kondapur")
        lat = user_states[from_number].get("lat", "")
        lon = user_states[from_number].get("lon", "")
        user_states[from_number]["name"] = name

        if user_states[from_number].get("order_type") == "delivery":
            msg.body("🏠 Please enter your full delivery address:")
            user_states[from_number]["step"] = "awaiting_address"
        else:
            order_id = save_order(from_number, name, branch, "Takeaway", "Takeaway")
            msg.body(
                f"🕒 Please pick up in 15 mins from {branch} branch.\n"
                f"📍 {BRANCH_LINKS[branch]}\n"
                f"🧾 Order ID: {order_id}\n"
                f"📞 For any changes, call: {BRANCH_CONTACTS[branch]}"
            )
            for kitchen in KITCHEN_NUMBERS:
                twilio_client.messages.create(
                    from_=WHATSAPP_FROM,
                    to=f"whatsapp:{kitchen}",
                    body=f"🧾 Takeaway Order\nBranch: {branch}\nOrder ID: {order_id}\nCustomer: {name}\nPhone: {from_number}"
                )
            user_states[from_number] = {"step": "start"}
        return str(resp)

    if state.get("step") == "awaiting_address":
        name = user_states[from_number].get("name", "Guest")
        branch = user_states[from_number].get("branch", "Kondapur")
        lat = user_states[from_number].get("lat", "")
        lon = user_states[from_number].get("lon", "")
        address = incoming_msg
        order_id = save_order(from_number, name, branch, "Delivery", address)
        msg.body(
            f"✅ Order placed!\n"
            f"📍 Delivery to: {address}\n"
            f"🧾 Order ID: {order_id}\n"
            f"📞 For any changes, call: {BRANCH_CONTACTS[branch]}"
        )
        for kitchen in KITCHEN_NUMBERS:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=f"whatsapp:{kitchen}",
                body=f"🧾 Delivery Order\nBranch: {branch}\nOrder ID: {order_id}\nAddress: {address}\nCustomer: {name}\nPhone: {from_number}"
            )
        user_states[from_number] = {"step": "start"}
        return str(resp)

    msg.body("🤖 Please type 'hi' to start your order.")
    return str(resp)

@app.route("/download-unserviceables")
def download_unserviceables():
    return send_file("unserviceable_users.csv", as_attachment=True)

@app.route("/download-locations")
def download_locations():
    return send_file("user_locations.csv", as_attachment=True)

@app.route("/download-orders")
def download_orders():
    return send_file("orders.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
