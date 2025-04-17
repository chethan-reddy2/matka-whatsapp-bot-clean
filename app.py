import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps
from geopy.distance import geodesic

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

# --------------------- STATE -----------------------
user_states = {}

# --------------------- HELPERS -----------------------
def get_servicable_branch(coords):
    for branch, location in BRANCHES.items():
        if geodesic(coords, location).km <= 2:
            return branch
    return None

# --------------------- ROUTE -----------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")
    postback = request.values.get("ButtonPayload")

    resp = MessagingResponse()
    msg = resp.message()
    state = user_states.get(from_number, {"step": "start"})

    # Start with template reply
    if state["step"] == "start" or incoming_msg in ["hi", "hello"]:
        try:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                content_sid="HXb044cc05b74e2472d4c5838d94c8c6c4"  # fruitcustard_greeting
            )
        except Exception as e:
            print("Template error:", e)
        user_states[from_number] = {"step": "awaiting_main_selection"}
        return str(resp)

    # Main selection postback
    if state["step"] == "awaiting_main_selection":
        if postback == "order_food":
            msg.body("\ud83d\udccd Please share your live location or type your area name to check delivery availability.")
            user_states[from_number] = {"step": "awaiting_location"}
            return str(resp)
        elif postback in ["bulk_order", "other_query"]:
            msg.body("\ud83d\udccd Please connect with us on WhatsApp: https://wa.me/918688641919")
            user_states[from_number] = {"step": "start"}
            return str(resp)

    # Location received
    if state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                loc_data = gmaps.geocode(incoming_msg)[0]["geometry"]["location"]
                user_coords = (loc_data["lat"], loc_data["lng"])

            branch = get_servicable_branch(user_coords)
            if branch:
                msg.body(f"\u2705 You're within delivery range of our {branch} branch! \nTap below to view our catalog.")
                try:
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=from_number,
                        content_sid="HX79124164c9b84e23a12f0765425f7e86"  # fruitcustard_cat_menu
                    )
                except Exception as e:
                    print("Catalog send error:", e)
            else:
                msg.body("\u274c Sorry! You're currently outside our delivery area. We'll notify you once we reach your location. \nThanks for your interest! \ud83d\ude4f")
            user_states[from_number] = {"step": "start"}
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("\u26a0\ufe0f Couldn't detect your location. Please try again with a known area name or pin code.")
            return str(resp)

    msg.body("\ud83e\udd16 Type 'hi' to restart your order.")
    return str(resp)

# --------------------- RUN -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
