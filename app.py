import os
import csv
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic
import datetime
from twilio.rest import Client

app = Flask(__name__)

# Twilio Configuration
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
KITCHEN_WHATSAPP = 'whatsapp:+917671011599'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# Google Maps Configuration
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

# Save CSV
def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# Save location info for navigation
def save_location_info(phone, lat, lon, branch):
    with open("user_locations.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([phone, lat, lon, branch, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

user_states = {}

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    resp = MessagingResponse()
    msg = resp.message()

    state = user_states.get(from_number, {"step": "start"})

    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        msg.body("👋 Welcome to Fruit Custard!\n\nWe offer:\n🍧 Fruit Custards\n🥣 Oatmeals\n🍹 Juices\n🍓 Fruit Bowls\n🍮 Delights & more!\n\nWhy are you here today?\n1️⃣ Order Food\n2️⃣ Bulk Order\n3️⃣ Other Query")
        state = {"step": "greeting"}

    elif state["step"] == "greeting":
        if "1" in incoming_msg:
            msg.body("📍 Please share your live location or area name to check delivery availability.")
            state["step"] = "awaiting_location"
        elif "2" in incoming_msg or "3" in incoming_msg:
            msg.body("📲 For bulk orders or queries, message us on WhatsApp: https://wa.me/918688641919")
            state = {"step": "start"}
        else:
            msg.body("❓ Please select a valid option: 1️⃣ Order Food, 2️⃣ Bulk Order, 3️⃣ Other Query")

    elif state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                loc_data = gmaps.geocode(incoming_msg)
                loc = loc_data[0]["geometry"]["location"]
                user_coords = (loc["lat"], loc["lng"])

            for branch, coords in BRANCHES.items():
                if geodesic(user_coords, coords).km <= 2:
                    save_location_info(from_number, user_coords[0], user_coords[1], branch)
                    msg.body(f"✅ You're within delivery range of our *{branch}* branch!\n\nTap below to view our menu and order.")
                    msg.media("https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages/Media/HX79124164c9b84e23a12f0765425f7e86")  # Catalog template placeholder
                    state = {"step": "menu_displayed"}
                    break
            else:
                save_unserviceable_user(from_number)
                msg.body("❌ Sorry, we don't deliver to your area yet. We'll notify you when we do!")
                state = {"step": "start"}
        except:
            msg.body("⚠️ Couldn't detect your location. Please try again with area name or share live location.")

    user_states[from_number] = state
    return str(resp)

@app.route("/download-orders", methods=["GET"])
def download_orders():
    try:
        return send_file("user_locations.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
