import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic
import datetime
from twilio.rest import Client
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

app = Flask(__name__)

# --------------------- CONFIG -----------------------
# Twilio & WhatsApp
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = 'ef5c7e7ddd59267420b9860539b12227'
WHATSAPP_FROM = 'whatsapp:+14155238886'
KITCHEN_WHATSAPP = 'whatsapp:+917671011599'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# Google Maps API
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
KITCHEN_LOCATION = (17.453049, 78.395519)

# Google Sheets Setup (Inline JSON Credentials)
def connect_to_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    service_account_info = {
      "type": "service_account",
      "project_id": "bubbly-subject-438713-a8",
      "private_key_id": "e2dc343b2514515f567677e204ec6e0a7e8d1730",
      "private_key": """-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDhfLi7jVhcskqH\njsRc88Iy70k+EJ8gyEsBaJTq9PX81hZNwNRkLBeVVKbnXidGgErOgecTBqNiN81e\n... (truncated for brevity) ...\n-----END PRIVATE KEY-----""",
      "client_email": "matka-foods-orders@bubbly-subject-438713-a8.iam.gserviceaccount.com",
      "client_id": "102405415436373978451",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/matka-foods-orders@bubbly-subject-438713-a8.iam.gserviceaccount.com",
      "universe_domain": "googleapis.com"
    }
    creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
    client = gspread.authorize(creds)
    return client.open("Matka Orders").worksheet("Matka Orders")

# Menu Items
menu_items = {
    "1": "Ma Brownie (1 piece) - ₹150",
    "2": "Itlu Bobbatlu (2 pieces) - ₹120",
    "3": "Gulab Jamun Cheesecake (Slice) - ₹180",
    "4": "Classic Custard (250ml Bowl) - ₹90"
}

# Track user steps
user_states = {}

# ---------------------- ROUTE -----------------------
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

        try:
            sheet = connect_to_sheet()
            sheet.append_row([from_number, item, address, timestamp])
        except Exception as e:
            print("❌ Sheet logging failed:", e)
            msg.body("⚠️ Could not log your order to Google Sheets. Please try again.")
            return str(resp)

        try:
            order_msg = (
                f"📢 *New Order Received!*\n"
                f"🍽️ Item: {item}\n"
                f"📾 Customer: {from_number}\n"
                f"📍 Address: {address}\n"
                f"🕒 Time: {timestamp}"
            )
            twilio_client.messages.create(
                body=order_msg,
                from_=WHATSAPP_FROM,
                to=KITCHEN_WHATSAPP
            )
        except Exception as e:
            print("❌ Kitchen alert failed:", e)

        msg.body(f"✅ Order confirmed for *{item}*.\n📍 Delivery to: {address}\nThank you for ordering with Matka Foods! 🙏")
        user_states[from_number] = {"step": "start"}
        return str(resp)

    else:
        msg.body("🤖 Type 'hi' to start your order.")
        return str(resp)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 10000))
