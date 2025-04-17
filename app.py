import os
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic

app = Flask(__name__)

# Twilio config
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# Google Maps
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
branches = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

# State tracking
user_states = {}

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")
    from_number = request.values.get("From")

    resp = MessagingResponse()
    msg = resp.message()
    state = user_states.get(from_number, {"step": "start"})

    # 🟢 Phase 1: Greeting
    if incoming_msg in ["hi", "hello", "hey"] or state["step"] == "start":
        user_states[from_number] = {"step": "main_menu"}
        try:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                content_sid="HXb044cc05b74e2472d4c5838d94c8c6c4"  # greeting template
            )
        except Exception as e:
            print("Greeting template failed:", e)
            msg.body("👋 Welcome to Fruit Custard! Please choose: 1. Order Food, 2. Bulk Order, 3. Other Query")
        return str(resp)

    # 🟡 Step 2: After choosing Order Food
    elif incoming_msg == "1" and state["step"] == "main_menu":
        msg.body("📍 Please share your live location or area name to check delivery availability.")
        user_states[from_number] = {"step": "awaiting_location"}
        return str(resp)

    # 🔴 Step 2b: Bulk or Other Query
    elif incoming_msg in ["2", "3"] and state["step"] == "main_menu":
        msg.body("📲 Please reach us on WhatsApp at +918688641919 for bulk orders or other queries.")
        user_states[from_number] = {"step": "start"}
        return str(resp)

    # 📍 Step 3: Location detection
    elif state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                location_data = gmaps.geocode(incoming_msg)
                if not location_data:
                    msg.body("❌ Couldn't detect location. Try again.")
                    return str(resp)
                loc = location_data[0]['geometry']['location']
                user_coords = (loc['lat'], loc['lng'])

            for branch, coords in branches.items():
                if geodesic(user_coords, coords).km <= 2:
                    user_states[from_number] = {"step": "catalog_shown"}
                    msg.body(f"🎉 Hurray! You're within delivery range of our {branch} branch!")
                    try:
                        twilio_client.messages.create(
                            from_=WHATSAPP_FROM,
                            to=from_number,
                            content_sid="HX79124164c9b84e23a12f0765425f7e86"  # catalog template
                        )
                    except Exception as e:
                        print("Catalog template failed:", e)
                        msg.body("🛍️ Here's our catalog. (But we couldn't show template, try manually.)")
                    return str(resp)

            # If not in range
            msg.body("🚫 Sorry, you're currently outside our 2 km delivery range. We'll notify you when we expand!")
            # Optional: Save number for future marketing
            with open("out_of_range.csv", "a") as f:
                f.write(f"{from_number},{incoming_msg}\n")
            user_states[from_number] = {"step": "start"}
        except Exception as e:
            print("❌ Location error:", e)
            msg.body("⚠️ Error checking your location. Try again.")
        return str(resp)

    # 🌀 Default fallback
    msg.body("🤖 Type 'hi' to start.")
    user_states[from_number] = {"step": "start"}
    return str(resp)

# Run
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
