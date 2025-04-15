from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic
import datetime
from twilio.rest import Client
import os

app = Flask(__name__)

# Use environment variables for secrets
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
WHATSAPP_FROM = 'whatsapp:+14155238886'
KITCHEN_WHATSAPP = 'whatsapp:+917671011599'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

gmaps = googlemaps.Client(key="YOUR_GOOGLE_MAPS_API_KEY")  # Can keep here or make env
KITCHEN_LOCATION = (17.453049, 78.395519)

menu_items = {
    "1": "Matka Brownie (1 piece) - ₹150",
    "2": "Itlu Bobbatlu (2 pieces) - ₹120",
    "3": "Gulab Jamun Cheesecake (Slice) - ₹180",
    "4": "Classic Custard (250ml Bowl) - ₹90"
}

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
        menu_text = "\n".join([f"{k}. {v}" for k, v in menu_items.items()])
        msg.body(f"👋 Welcome to Matka Foods!\nHere’s our menu:\n\n{menu_text}\n\nReply with the item number to order.")
        user_states[from_number] = {"step": "awaiting_item"}
        return str(resp)

    elif state["step"] == "awaiting_item":
        if incoming_msg in menu_items:
            selected_item = menu_items[incoming_msg]
            user_states[from_number] = {
                "step": "awaiting_location",
                "item": selected_item
            }
            msg.body(f"🍽️ You selected: {selected_item}\n\n📍 Please send your location (area name or pin).")
        else:
            msg.body("❌ Invalid selection. Please choose a valid item number.")
        return str(resp)

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

            distance = geodesic(KITCHEN_LOCATION, user_coords).km
            if distance <= 3:
                user_states[from_number]["step"] = "awaiting_address"
                msg.body(f"✅ You're {round(distance, 2)} km away — within our delivery zone!\nPlease send your full delivery address.")
            else:
                msg.body(f"❌ You're {round(distance, 2)} km away — outside our 3 km delivery zone.")
                user_states[from_number] = {"step": "start"}
        except Exception as e:
            print("❌ Location error:", e)
            msg.body("⚠️ Error checking your location. Try again.")
        return str(resp)

    elif state["step"] == "awaiting_address":
        address = incoming_msg
        item = state["item"]
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Send to kitchen
        try:
            order_msg = (
                f"📢 *New Order!*\n"
                f"🍽️ Item: {item}\n"
                f"📞 Customer: {from_number}\n"
                f"📍 Address: {address}\n"
                f"🕒 Time: {timestamp}"
            )
            twilio_client.messages.create(
                body=order_msg,
                from_=WHATSAPP_FROM,
                to=KITCHEN_WHATSAPP
            )
        except Exception as e:
            print("❌ Failed to send alert:", e)

        msg.body(f"✅ Order confirmed for *{item}*.\n📍 Delivery to: {address}\nThanks for ordering! 🙏")
        user_states[from_number] = {"step": "start"}
        return str(resp)

    else:
        msg.body("🤖 Type 'hi' to start.")
        return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
