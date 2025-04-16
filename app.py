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
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
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
        try:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                content_sid="HXb044cc05b74e2472d4c5838d94c8c6c4"  # greeting template
            )
        except Exception as e:
            print("Template send error:", e)
            msg.body("👋 Welcome to Fruit Custard! Please share your live location or area name so we can check if we deliver to you.")
        user_states[from_number] = {"step": "awaiting_post_greeting"}
        return str(resp)

    elif state["step"] == "awaiting_post_greeting":
        if "order food" in incoming_msg:
            msg.body("📍 Please share your live location or type your area name.")
            user_states[from_number] = {"step": "awaiting_location"}
            return str(resp)
        elif "bulk order" in incoming_msg or "other query" in incoming_msg:
            msg.body("📲 For bulk orders or other queries, please contact us directly at https://wa.me/+918688641919")
            user_states[from_number] = {"step": "start"}
            return str(resp)
        else:
            msg.body("🤖 Please choose one of the options from the menu or type 'hi' to restart.")
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
                        "step": "awaiting_menu_selection",
                        "branch": branch_name,
                        "location": user_coords
                    }
                    msg.body(f"✅ You're within delivery range of our *{branch_name}* branch!\n🍴 What would you like to explore?\n\n1. Best Sellers\n2. Full Menu\n3. Return to Main Menu\n\nReply with the number (1/2/3).")
                    return str(resp)

            save_unserviceable_user(from_number)
            user_states[from_number] = {"step": "start"}
            msg.body("❌ Sorry, we don’t currently deliver to your area. We'll notify you once we expand! 🗺️")
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Try again with area name, pin or share your live location.")
        return str(resp)

    elif state["step"] == "awaiting_menu_selection":
        if incoming_msg == "1":
            msg.body("🔥 *Best Sellers* 🔥\n\n• Fruit Custard (220g) – ₹120\n• Nutty Custard Ice Cream (220g) – ₹100\n• Apricot Delight (220g) – ₹170\n\nReply with item number to add to cart or type 'menu' to view full options.")
        elif incoming_msg == "2":
            menu_text = (
                "🍧 *Fruit Custard Menu* 🍧\n\n"
                "🥣 *Oatmeals*:\n"
                "1. Fruit Pop Mini (220g) - ₹140\n"
                "2. Choco Banana Oatmeal (320g) - ₹180\n\n"
                "🍨 *Custard Delicacies*:\n"
                "3. Classic Custard Bowl (250ml) - ₹90\n"
                "4. Nutty Custard Ice Cream (220g) - ₹100\n"
                "5. Apricot Delight (220g) - ₹170\n\n"
                "🧃 *Juices*:\n"
                "6. Watermelon Juice (300ml) - ₹129\n\n"
                "👉 Reply with item numbers separated by commas to add to cart."
            )
            msg.body(menu_text)
        elif incoming_msg == "3":
            msg.body("🔁 Back to main menu. Type 'hi' to restart.")
            user_states[from_number] = {"step": "start"}
        else:
            msg.body("🤖 Invalid selection. Reply with 1, 2, or 3.")
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
