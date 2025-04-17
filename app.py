import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic
from twilio.rest import Client

app = Flask(__name__)

# --------------------- TWILIO CONFIG -----------------------
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# --------------------- GOOGLE MAPS -----------------------
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")

# --------------------- STATE TRACKER -----------------------
user_states = {}

# --------------------- BRANCH LOCATIONS -----------------------
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    resp = MessagingResponse()
    msg = resp.message()

    state = user_states.get(from_number, {"step": "start"})

    # STEP 1: Greet
    if state["step"] == "start" or incoming_msg in ["hi", "hello"]:
        user_states[from_number] = {"step": "awaiting_choice"}
        return str(resp)  # Template message will handle greeting

    # STEP 2: Handle Button Choices
    if incoming_msg == "1":  # Order Food
        msg.body("📍 Please share your live location or area name to check delivery availability.")
        user_states[from_number] = {"step": "awaiting_location"}
        return str(resp)
    elif incoming_msg == "2":  # Bulk Order
        msg.body("📦 For bulk orders, please contact us directly at: https://wa.me/918688641919")
        return str(resp)
    elif incoming_msg == "3":  # Other Query
        msg.body("❓ For queries, reach out at: https://wa.me/918688641919")
        return str(resp)

    # STEP 3: Location Check
    if state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                geocode_result = gmaps.geocode(incoming_msg)
                if not geocode_result:
                    msg.body("❌ Could not detect your location. Please try again.")
                    return str(resp)
                loc = geocode_result[0]["geometry"]["location"]
                user_coords = (loc["lat"], loc["lng"])

            found = False
            for branch_name, branch_coords in BRANCHES.items():
                distance = geodesic(user_coords, branch_coords).km
                if distance <= 2:
                    msg.body(f"🎉 Hurray! We can deliver to your location from our *{branch_name}* branch.\n\n🧾 Tap below to view our full catalog.")

                    # Send Catalog Template
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=from_number,
                        content_sid="HX79124164c9b84e23a12f0765425f7e86"  # fruitcustard_cat_menu
                    )
                    found = True
                    break

            if not found:
                msg.body("🚫 Sorry! We're currently not delivering to your location. We'll notify you when we expand to your area.")
                with open("non_serviceable.csv", "a") as f:
                    f.write(from_number + "\n")

            return str(resp)

        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Error processing your location. Please try again.")
            return str(resp)

    # Default fallback
    msg.body("🤖 Type 'hi' to start again.")
    user_states[from_number] = {"step": "start"}
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
