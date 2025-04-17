import os
import csv
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps
from geopy.distance import geodesic
import datetime

app = Flask(__name__)

# Twilio Configuration
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# Google Maps Configuration
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

# Save CSVs
def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def save_location_info(phone, lat, lon, branch):
    with open("user_locations.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([phone, lat, lon, branch, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# Store user state
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

    # Step 1: Greeting
    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to=from_number,
            content_sid="HXb044cc05b74e2472d4c5838d94c8c6c4"  # greeting template
        )
        user_states[from_number] = {"step": "greeted"}
        return ("", 200)

    # Step 2: Main Menu Options
    elif state["step"] == "greeted":
        if incoming_msg == "1":
            msg.body("📍 Please share your live location or type your area name to check delivery availability.")
            user_states[from_number] = {"step": "awaiting_location"}
            return str(resp)

        elif incoming_msg in ["2", "3"]:
            msg.body("📲 For bulk orders or queries, message us directly: https://wa.me/918688641919")
            user_states[from_number] = {"step": "start"}
            return str(resp)

        else:
            msg.body("❓ Please reply with:\n1️⃣ Order Food\n2️⃣ Bulk Order\n3️⃣ Other Query")
            return str(resp)

    # Step 3: Location Handling
    elif state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            elif incoming_msg:
                loc_data = gmaps.geocode(incoming_msg)
                loc = loc_data[0]['geometry']['location']
                user_coords = (loc['lat'], loc['lng'])
            else:
                msg.body("⚠️ Please share your live location or area name.")
                return str(resp)

            for branch, coords in BRANCHES.items():
                if geodesic(user_coords, coords).km <= 2:
                    save_location_info(from_number, user_coords[0], user_coords[1], branch)
                    # Confirm serviceable and send menu
                    msg.body(f"🎉 Hurray! We can deliver to you from our {branch} branch. Here's our menu 👇")
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=from_number,
                        content_sid="HX79124164c9b84e23a12f0765425f7e86"  # fruitcustard_cat_menu
                    )
                    user_states[from_number] = {"step": "catalogue_shown"}
                    return str(resp)

            save_unserviceable_user(from_number)
            msg.body("❌ Sorry, we don't deliver to your area yet. We'll notify you when we do!")
            user_states[from_number] = {"step": "start"}
            return str(resp)

        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Please try again with area name or pin code.")
            return str(resp)

    # Default fallback
    msg.body("🤖 Please type 'hi' to start your order.")
    return str(resp)

@app.route("/download-unserviceables", methods=["GET"])
def download_unserviceables():
    try:
        return send_file("unserviceable_users.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

@app.route("/download-locations", methods=["GET"])
def download_locations():
    try:
        return send_file("user_locations.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
