import os
import csv
import uuid
from flask import Flask, request, send_file, render_template_string
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps
from geopy.distance import geodesic
import datetime
import threading

app = Flask(__name__)

# --------------------- TWILIO CONFIG -----------------------
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
KITCHEN_WHATSAPP = 'whatsapp:+917671011599'
MANAGER_WHATSAPP = 'whatsapp:+918885112242'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# Templates - content_sid
TEMPLATE_GREETING = "HXb044cc05b74e2472d4c5838d94c8c6c4"
TEMPLATE_ORDERING = "HXe5ce9a647ed912eb5c398e2ccd15fac3"
TEMPLATE_CART = "HXb3ef2c569aa925b76195f95d5f06eeb8"
TEMPLATE_DELIVERY = "HX6a4548eddff22056b5f4727db8ce5dcd"

# --------------------- GOOGLE MAPS -----------------------
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}

# --------------------- CSV LOGGER -----------------------
def log_interaction(phone, message, step):
    with open("interactions.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone, message, step])

def save_order_to_csv(order_id, phone, item, address, timestamp, status):
    with open("orders.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([order_id, phone, "; ".join(item), address, timestamp, status])

def update_order_status(order_id, status):
    lines = []
    updated = False
    customer_phone = None
    with open("orders.csv", mode="r", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        for row in reader:
            if row[0] == order_id:
                row[5] = status
                customer_phone = row[1]
                updated = True
            lines.append(row)

    if updated:
        with open("orders.csv", mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerows(lines)
    return updated, customer_phone

def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

user_states = {}
order_mapping = {}

menu_items = {
    "1": ("Fruit Custard (220g)", 120),
    "2": ("Nutty Custard Ice Cream (220g)", 100),
    "3": ("Apricot Delight (220g)", 170),
    "4": ("Fruit Pop Mini Oatmeal (220g)", 140),
    "5": ("Choco Banana Oatmeal (320g)", 180),
    "6": ("Classic Custard Bowl (250ml)", 90),
    "7": ("Watermelon Juice (300ml)", 129)
}

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    state = user_states.get(from_number, {"step": "start", "cart": []})
    log_interaction(from_number, incoming_msg, state.get("step", "unknown"))

    resp = MessagingResponse()
    msg = resp.message()

    if from_number in [KITCHEN_WHATSAPP, MANAGER_WHATSAPP] and incoming_msg.startswith("update"):
        parts = incoming_msg.split()
        if len(parts) == 3:
            _, order_id, new_status = parts
            updated, customer_phone = update_order_status(order_id, new_status)
            if updated:
                msg.body(f"✅ Order {order_id} updated to {new_status}")
                if customer_phone:
                    twilio_client.messages.create(
                        body=f"🔄 Your Order {order_id} status is now: {new_status.upper()}.",
                        from_=WHATSAPP_FROM,
                        to=customer_phone
                    )
            else:
                msg.body("❌ Order ID not found.")
        else:
            msg.body("⚠️ Format: update ORDER_ID STATUS")
        return str(resp)

    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        twilio_client.messages.create(from_=WHATSAPP_FROM, to=from_number, content_sid=TEMPLATE_GREETING)
        user_states[from_number] = {"step": "awaiting_location", "cart": []}
        return ""

    elif state["step"] == "awaiting_location":
        try:
            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            elif "," in incoming_msg:
                parts = incoming_msg.split(",")
                user_coords = (float(parts[0].strip()), float(parts[1].strip()))
            else:
                loc_data = gmaps.geocode(incoming_msg)
                if not loc_data:
                    raise Exception("No location found")
                loc = loc_data[0]["geometry"]["location"]
                user_coords = (loc["lat"], loc["lng"])

            for branch_name, branch_coords in BRANCHES.items():
                distance = geodesic(user_coords, branch_coords).km
                if distance <= 2:
                    state["step"] = "awaiting_cart"
                    state["branch"] = branch_name
                    user_states[from_number] = state
                    twilio_client.messages.create(from_=WHATSAPP_FROM, to=from_number, content_sid=TEMPLATE_ORDERING)
                    return ""

            save_unserviceable_user(from_number)
            msg.body("❌ Sorry, we don’t deliver to your area yet. We'll notify you once we expand! 🗺️")
            user_states[from_number] = {"step": "start", "cart": []}
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Try again with area name, or share lat,long format like '17.45, 78.39'.")
            return str(resp)

    msg.body("🤖 Type 'hi' to start.")
    return str(resp)

@app.route("/download-orders")
def download_orders():
    return send_file("orders.csv", as_attachment=True)

@app.route("/dashboard")
def dashboard():
    try:
        with open("orders.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except:
        rows = []
    html = """
    <html><body><h2>Order Dashboard</h2>
    <table border='1'><tr><th>Order ID</th><th>Phone</th><th>Items</th><th>Address</th><th>Time</th><th>Status</th></tr>
    {% for row in rows %}<tr>{% for col in row %}<td>{{ col }}</td>{% endfor %}</tr>{% endfor %}
    </table></body></html>
    """
    return render_template_string(html, rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
