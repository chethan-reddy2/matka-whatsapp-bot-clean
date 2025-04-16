import os
from flask import Flask, request
from twilio.rest import Client
import googlemaps
from geopy.distance import geodesic
import csv
import datetime

app = Flask(__name__)

# --------------------- TWILIO CONFIG -----------------------
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# --------------------- GOOGLE MAPS -----------------------
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
BRANCHES = {
    "Kondapur": (17.453049, 78.395519),
    "Madhapur": (17.451883, 78.394328),
    "Manikonda": (17.403894, 78.390795)
}

# --------------------- STATE -----------------------
user_states = {}

# --------------------- UTILITY -----------------------
def log_unserviceable_user(number):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("unserviceable_users.csv", "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([number, timestamp])

# --------------------- ROUTE -----------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")

    state = user_states.get(from_number, {"step": "start"})

    if incoming_msg in ["hi", "hello", "hey"] or state["step"] == "start":
        try:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                content_sid="HXb044cc05b74e2472d4c5838d94c8c6c4"
            )
            user_states[from_number] = {"step": "awaiting_intent"}
            return "Greeting template sent."
        except Exception as e:
            print("❌ Failed to send template:", e)
            return "Error sending template.", 500

    elif state["step"] == "awaiting_intent":
        if incoming_msg in ["1", "order_food"]:
            user_states[from_number] = {"step": "awaiting_location"}
            return "📍 Please send your location or area name."
        elif incoming_msg in ["2", "bulk_order"]:
            user_states[from_number] = {"step": "done"}
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                body="📦 For bulk order queries, please contact us at https://wa.me/918688641919"
            )
            return "Redirected to bulk order contact."
        elif incoming_msg in ["3", "other_query"]:
            user_states[from_number] = {"step": "done"}
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                body="💬 For other queries, please contact us at https://wa.me/918688641919"
            )
            return "Redirected to support contact."

    elif state["step"] == "awaiting_location":
        try:
            geo = gmaps.geocode(incoming_msg)
            if not geo:
                raise Exception("Invalid location")
            user_latlng = geo[0]['geometry']['location']
            user_coords = (user_latlng['lat'], user_latlng['lng'])

            for branch, coords in BRANCHES.items():
                if geodesic(user_coords, coords).km <= 2:
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=from_number,
                        body=f"✅ You're eligible for delivery from our *{branch}* branch! 🍧 Let's continue your order."
                    )
                    user_states[from_number] = {"step": "menu", "branch": branch}
                    return "Branch found and message sent."

            # No branch found within 2 km
            log_unserviceable_user(from_number)
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                body="❌ Sorry, we currently don't deliver to your area. We'll notify you when we expand!"
            )
            user_states[from_number] = {"step": "done"}
            return "Location out of range."

        except Exception as e:
            print("❌ Location error:", e)
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                body="⚠️ Couldn't detect your location. Please try again with a different area name or pin."
            )
            return "Location handling failed."

    return "Unhandled state."

# --------------------- RUN -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
