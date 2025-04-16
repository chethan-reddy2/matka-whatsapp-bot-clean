import os
import csv
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
import googlemaps
from geopy.distance import geodesic
import datetime
from twilio.rest import Client

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
    "Kondapur": (17.453049, 78.395519),
    "Madhapur": (17.451883, 78.394328),
    "Manikonda": (17.403894, 78.390795)
}

# --------------------- CSV LOGGER -----------------------
def save_order_to_csv(phone, item, address, timestamp):
    try:
        with open("orders.csv", mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([phone, item, address, timestamp])
    except Exception as e:
        print("CSV logging error:", e)

def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# --------------------- MENU -----------------------
menu_items = {
    "1": "Brownie (1 piece) - ₹150",
    "2": "Itlu Bobbatlu (2 pieces) - ₹120",
    "3": "Gulab Jamun Cheesecake (Slice) - ₹180",
    "4": "Classic Custard (250ml Bowl) - ₹90"
}
user_states = {}

# --------------------- WHATSAPP ROUTE -----------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    print("Incoming Payload:", dict(request.values))

    resp = MessagingResponse()
    msg = resp.message()
    state = user_states.get(from_number, {"step": "start"})

    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        msg.body("👋 Welcome to Fruit Custard! We deliver from Kondapur, Madhapur & Manikonda branches.\n\n📍 Please share your live location or area name so we can check if we deliver to you.")
        user_states[from_number] = {"step": "awaiting_location"}
        return str(resp)

    elif state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                loc_data = gmaps.geocode(incoming_msg)
                if not loc_data:
                    raise Exception("No location found")
                loc = loc_data[0]["geometry"]["location"]
                user_coords = (loc["lat"], loc["lng"])

            for branch_name, branch_coords in BRANCHES.items():
                distance = geodesic(user_coords, branch_coords).km
                if distance <= 2:
                    user_states[from_number] = {
                        "step": "awaiting_order",
                        "branch": branch_name,
                        "location": user_coords
                    }
                    msg.body(f"✅ You're within 2 km of our *{branch_name}* branch! 🎉\nWhat would you like to do today?\n\nReply with: Order / Takeaway / Bulk Order / Other Query")
                    return str(resp)

            # Out of range for all branches
            save_unserviceable_user(from_number)
            user_states[from_number] = {"step": "start"}
            msg.body("❌ Sorry, we don’t currently deliver to your area. We'll notify you once we expand! 🗺️")
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Try again with area name, pin or share your live location.")
        return str(resp)

    elif state["step"] == "awaiting_order":
        msg.body("🛍️ Ordering not implemented yet. Please reply 'hi' to restart.")
        return str(resp)

    else:
        msg.body("🤖 Type 'hi' to start.")
        return str(resp)

# --------------------- CSV DOWNLOAD ROUTE -----------------------
@app.route("/download-orders", methods=["GET"])
def download_orders():
    try:
        return send_file("orders.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

# --------------------- RUN -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
