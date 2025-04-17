import os
import csv
import uuid
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

# Branch Coordinates
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

# Google Maps Links
BRANCH_LINKS = {
    "Kondapur": "https://maps.app.goo.gl/rSxvENYt2usTsgkM9",
    "Madhapur": "https://maps.app.goo.gl/NiqeMPuLk8SHTxv48",
    "Manikonda": "https://maps.app.goo.gl/fhn1JfopRp27JxFv6"
}

user_states = {}
orders = {}

# Save unserviceable user
def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# Save location
def save_location_info(phone, lat, lon, branch):
    with open("user_locations.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([phone, lat, lon, branch, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# Save order
def save_order(phone, branch, order_type, address=None):
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("orders.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([order_id, phone, branch, order_type, address or "Takeaway", timestamp])
    return order_id

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
            content_sid="HXe1b289e2a199611ad5b7c864f97a024c"  # greeting template with buttons
        )
        user_states[from_number] = {"step": "greeted"}
        return ("", 200)

    # Step 2: Menu Options
    elif state["step"] == "greeted":
        if incoming_msg in ["1", "order food"]:
            msg.body("📍 Please share your live location or type your area name to check delivery availability.")
            user_states[from_number] = {"step": "awaiting_location"}
            return str(resp)
        elif incoming_msg in ["2", "bulk order", "3", "other query"]:
            msg.body("📲 For bulk orders or queries, message us directly: https://wa.me/918688641919")
            user_states[from_number] = {"step": "start"}
            return str(resp)
        else:
            msg.body("❓ Please reply with:\n🟢 Order Food\n📦 Bulk Order\n❓ Other Query")
            return str(resp)

    # Step 3: Handle location input
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
                    msg.body(f"🎉 Hurray! We can deliver to you from our {branch} branch. Here's our menu 👇")
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=from_number,
                        content_sid="HX79124164c9b84e23a12f0765425f7e86"  # fruitcustard_cat_menu
                    )
                    msg.body("🛍️ After selecting items from the catalog, type *order* to proceed.")
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

    # Step 4: Detect "order" typed manually after using catalog
    elif state["step"] == "catalogue_shown" and incoming_msg in ["order", "place order"]:
        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to=from_number,
            content_sid="HX6a4548eddff22056b5f4727db8ce5dcd"  # delivery or takeaway buttons
        )
        user_states[from_number] = {"step": "order_type_selection"}
        return ("", 200)

    # Step 5: Delivery or Takeaway
    elif state["step"] == "order_type_selection":
        if incoming_msg == "delivery":
            msg.body("🏠 Please enter your full delivery address including area, street, and any landmark:")
            user_states[from_number] = {"step": "awaiting_address", "type": "Delivery"}
            return str(resp)

        elif incoming_msg == "takeaway":
            try:
                with open("user_locations.csv", encoding="utf-8") as f:
                    rows = list(csv.reader(f))
                    branch = next((row[3] for row in reversed(rows) if row[0] == from_number), "Kondapur")
            except:
                branch = "Kondapur"

            order_id = save_order(from_number, branch, "Takeaway")
            msg.body(f"🕒 Please pick up your order in 15 minutes from our {branch} branch.\n📍 Location: {BRANCH_LINKS[branch]}\n\n🧾 Your Order ID: {order_id}")

            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to="whatsapp:+918885112242",
                body=f"🧾 New Takeaway Order\nBranch: {branch}\nOrder ID: {order_id}\nCustomer: {from_number}"
            )
            user_states[from_number] = {"step": "start"}
            return str(resp)

    # Step 6: Get Delivery Address
    elif state["step"] == "awaiting_address":
        try:
            with open("user_locations.csv", encoding="utf-8") as f:
                rows = list(csv.reader(f))
                branch = next((row[3] for row in reversed(rows) if row[0] == from_number), "Kondapur")
        except:
            branch = "Kondapur"

        address = incoming_msg.strip()
        order_id = save_order(from_number, branch, "Delivery", address)

        msg.body(f"✅ Your order has been placed for delivery.\n📦 It will be delivered soon to:\n{address}\n\n🧾 Order ID: {order_id}")

        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to="whatsapp:+918885112242",
            body=f"🧾 New Delivery Order\nBranch: {branch}\nOrder ID: {order_id}\nAddress: {address}\nCustomer: {from_number}"
        )

        user_states[from_number] = {"step": "start"}
        return str(resp)

    # Default fallback
    msg.body("🤖 Please type 'hi' to start your order.")
    return str(resp)

# CSV Download Endpoints
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

@app.route("/download-orders", methods=["GET"])
def download_orders():
    try:
        return send_file("orders.csv", as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
