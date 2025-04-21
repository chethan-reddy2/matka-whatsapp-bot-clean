import os
import csv
import uuid
import re
from flask import Flask, request, send_file, render_template_string, redirect, url_for
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps
from geopy.distance import geodesic
import datetime

app = Flask(__name__)

# Twilio Config
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = 'b60f99f091d59e8a1f47b8be20c25a98'
WHATSAPP_FROM = 'whatsapp:+14134145410'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# Google Maps Config
gmaps = googlemaps.Client(key="AIzaSyCuUz9N78WZAT1N38ffIDkbySI3_0zkZgE")

# Branch Info
BRANCHES = {
    "Kondapur": (17.47019976442252, 78.35272372527311),
    "Madhapur": (17.452121157758043, 78.39433952527278),
    "Manikonda": (17.403904212354316, 78.39079508109451)
}
BRANCH_LINKS = {
    "Kondapur": "https://maps.app.goo.gl/E26sm634cKJmxktH6",
    "Madhapur": "https://maps.app.goo.gl/x5AHBgoh3gMbhUobA",
    "Manikonda": "https://maps.app.goo.gl/FkCU71kfvKY2vrgw9"
}
BRANCH_CONTACTS = {
    "Kondapur": "+91 8885112242",
    "Madhapur": "+91 9640112005",
    "Manikonda": "+91 9182149094"
}
KITCHEN_NUMBERS = ["+918885112242", "+917671011599"]

user_states = {}

# CSV Utils
def save_unserviceable_user(phone):
    with open("unserviceable_users.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([phone, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def save_location_info(phone, lat, lon, branch):
    with open("user_locations.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([phone, lat, lon, branch, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])


def save_order(phone, branch, order_type, address=None):
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    with open("orders.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            order_id,
            phone,
            branch,
            order_type,
            address or "Takeaway",
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Pending"  # <- ADD THIS STATUS COLUMN
        ])
    return order_id

# WhatsApp Main Flow
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    button_text = request.values.get("ButtonText", "").strip().lower()
    from_number = request.values.get("From")
    latitude = request.values.get("Latitude")
    longitude = request.values.get("Longitude")

    resp = MessagingResponse()
    msg = resp.message()
    state = user_states.get(from_number, {"step": "start"})

    if incoming_msg in ["hi", "hello"] or state["step"] == "start":
        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to=from_number,
            content_sid="HXe1b289e2a199611ad5b7c864f97a024c"
        )
        user_states[from_number] = {"step": "greeted"}
        return ("", 200)

    if state["step"] == "greeted":
        if incoming_msg in ["1", "order food"]:
            msg.body("📍 Please share your live location or type your area name to check delivery availability.")
            user_states[from_number] = {"step": "awaiting_location"}
            return str(resp)
        elif incoming_msg in ["2", "bulk order", "3", "other query"]:
            msg.body("📲 For bulk orders or queries, message us: https://wa.me/918688641919")
            user_states[from_number] = {"step": "start"}
            return str(resp)
        else:
            msg.body("❓ Reply with:\n1️⃣ Order Food\n2️⃣ Bulk Order\n3️⃣ Other Query")
            return str(resp)

    if state["step"] == "awaiting_location":
        try:
            # If no input is received, just ask again
            if not incoming_msg and not (latitude and longitude):
                msg.body("📍 Please share your live location or type your area name to check delivery availability.")
                return str(resp)

            if latitude and longitude:
                user_coords = (float(latitude), float(longitude))
            else:
                loc = gmaps.geocode(incoming_msg)[0]['geometry']['location']
                user_coords = (loc['lat'], loc['lng'])

            for branch, coords in BRANCHES.items():
                if geodesic(user_coords, coords).km <= 2:
                    save_location_info(from_number, user_coords[0], user_coords[1], branch)
                    msg.body(f"🎉 We can deliver to you from {branch} branch. Here's our menu 👇")
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=from_number,
                        content_sid="HX79124164c9b84e23a12f0765425f7e86"
                    )
                    user_states[from_number] = {"step": "catalogue_shown"}
                    return str(resp)

            save_unserviceable_user(from_number)
            msg.body("❌ Sorry, we don't deliver to your area yet.")
            user_states[from_number] = {"step": "start"}
            return str(resp)
        except Exception as e:
            print("Location error:", e)
            msg.body("⚠️ Couldn't detect your location. Try typing your area name.")
            return str(resp)

    if state["step"] == "catalogue_shown" and (
        "estimated total" in incoming_msg or
        "view sent cart" in incoming_msg or
        "₹" in incoming_msg and "item" in incoming_msg or
        incoming_msg.startswith("1 item")
    ):
        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to=from_number,
            content_sid="HX6a4548eddff22056b5f4727db8ce5dcd"
        )
        user_states[from_number] = {"step": "order_type_selection"}
        for kitchen in KITCHEN_NUMBERS:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=f"whatsapp:{kitchen}",
                body=f"🛎️ Customer {from_number} submitted cart. Awaiting delivery/takeaway choice."
            )
        return ("", 200)

    msg.body("🤖 Please type 'hi' to start your order.")
    return str(resp)

    if state["step"] == "order_type_selection" and button_text in ["delivery", "takeaway"]:
        branch = "Kondapur"
        try:
            with open("user_locations.csv", encoding="utf-8") as f:
                branch = next((row[3] for row in reversed(list(csv.reader(f))) if row[0] == from_number), "Kondapur")
        except:
            pass

        if button_text == "delivery":
            msg.body("🏠 Please enter your full delivery address:")
            user_states[from_number] = {"step": "awaiting_address", "branch": branch}
            return str(resp)
        else:
            order_id = save_order(from_number, branch, "Takeaway")
            msg.body(
                f"🕒 Please pick up in 15 mins from {branch} branch.\n"
                f"📍 {BRANCH_LINKS[branch]}\n"
                f"🧾 Order ID: {order_id}\n"
                f"📞 For any changes, call: {BRANCH_CONTACTS[branch]}"
            )
            for kitchen in KITCHEN_NUMBERS:
                twilio_client.messages.create(
                    from_=WHATSAPP_FROM,
                    to=f"whatsapp:{kitchen}",
                    body=f"🧾 Takeaway Order\nBranch: {branch}\nOrder ID: {order_id}\nCustomer: {from_number}"
                )
            user_states[from_number] = {"step": "start"}
            return str(resp)

    if state.get("step") == "awaiting_address":
        branch = state.get("branch", "Kondapur")
        address = incoming_msg
        order_id = save_order(from_number, branch, "Delivery", address)
        msg.body(
            f"✅ Order placed!\n"
            f"📍 Delivery to: {address}\n"
            f"🧾 Order ID: {order_id}\n"
            f"📞 For any changes, call: {BRANCH_CONTACTS[branch]}"
        )
        for kitchen in KITCHEN_NUMBERS:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=f"whatsapp:{kitchen}",
                body=f"🧾 Delivery Order\nBranch: {branch}\nOrder ID: {order_id}\nAddress: {address}\nCustomer: {from_number}"
            )
        user_states[from_number] = {"step": "start"}
        return str(resp)

    if state.get("step") == "catalogue_shown":
        twilio_client.messages.create(
            from_=WHATSAPP_FROM,
            to=from_number,
            content_sid="HX6a4548eddff22056b5f4727db8ce5dcd"
        )
        user_states[from_number] = {"step": "order_type_selection"}
        for kitchen in KITCHEN_NUMBERS:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=f"whatsapp:{kitchen}",
                body=f"🛎️ Fallback used to detect cart. Sent delivery/takeaway to {from_number}"
            )
        return ("", 200)

    msg.body("🤖 Please type 'hi' to start your order.")
    return str(resp)

# 📦 Update status from kitchen via WhatsApp
@app.route("/update-order-status", methods=["POST"])
def update_order_status():
    incoming_msg = request.values.get("Body", "").strip().lower()
    order_match = re.search(r"ord-[a-z0-9]+", incoming_msg)
    if not order_match:
        return ("Please include order ID (ORD-XXXX) and status (ready, preparing, delivered).", 200)

    order_id = order_match.group().upper()
    status_msg = ""
    if "ready" in incoming_msg:
        status_msg = "✅ Your order is ready!"
    elif "preparing" in incoming_msg:
        status_msg = "👨‍🍳 Your order is being prepared."
    elif "delivered" in incoming_msg:
        status_msg = "📦 Your order has been delivered."
    else:
        return ("Unknown status. Use: ready, preparing, delivered.", 200)

    try:
        with open("orders.csv", newline='', encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row[0] == order_id:
                    phone = row[1]
                    twilio_client.messages.create(
                        from_=WHATSAPP_FROM,
                        to=phone,
                        body=f"{status_msg}\n🧾 Order ID: {order_id}"
                    )
                    return ("Customer notified.", 200)
            return ("Order ID not found.", 404)
    except Exception as e:
        return (f"Error: {str(e)}", 500)

# 🖥️ Dashboard to manage status
@app.route("/dashboard")
def dashboard():
    orders = []
    with open("orders.csv", newline='', encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                orders.append(row)
    return render_template_string(DASHBOARD_TEMPLATE, orders=orders)

@app.route("/update-status", methods=["POST"])
def update_status():
    order_id = request.form.get("order_id")
    phone = request.form.get("phone")
    status = request.form.get("status")
    status_map = {
        "preparing": "👨‍🍳 Your order is being prepared.",
        "ready": "✅ Your order is ready!",
        "delivered": "📦 Your order has been delivered."
    }
    msg = f"{status_map.get(status)}\n🧾 Order ID: {order_id}"
    twilio_client.messages.create(
        from_=WHATSAPP_FROM,
        to=phone,
        body=msg
    )
    rows = []
    with open("orders.csv", newline='', encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if row[0] == order_id and len(row) >= 7:
                row[6] = status.capitalize()
            rows.append(row)
    with open("orders.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)    
    return redirect(url_for("dashboard"))

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\"><head><meta charset=\"UTF-8\">
<title>Order Dashboard</title>
<link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css\" rel=\"stylesheet\">
</head>
<body class=\"p-4\">
<h2>Order Status Dashboard</h2>
<table class=\"table table-bordered\">
<thead>
<tr><th>Order ID</th><th>Phone</th><th>Branch</th><th>Type</th><th>Address</th><th>Time</th><th>Status</th><th>Update</th></tr>
</thead>
<tbody>
{% for order in orders %}
<tr>
<td>{{ order[0] }}</td>
<td>{{ order[1] }}</td>
<td>{{ order[2] }}</td>
<td>{{ order[3] }}</td>
<td>{{ order[4] }}</td>
<td>{{ order[5] }}</td>
<td>{{ order[6] if order|length > 6 else 'Pending' }}</td>
<td>
  <form method=\"POST\" action=\"/update-status\" class=\"d-flex\">
    <input type=\"hidden\" name=\"order_id\" value=\"{{ order[0] }}\">
    <input type=\"hidden\" name=\"phone\" value=\"{{ order[1] }}\">
    <select name=\"status\" class=\"form-select me-2\">
      <option disabled selected>Status</option>
      <option value=\"preparing\">Preparing</option>
      <option value=\"ready\">Ready</option>
      <option value=\"delivered\">Delivered</option>
    </select>
    <button class=\"btn btn-primary\">Update</button>
  </form>
</td>
</tr>
{% endfor %}
</tbody>
</table>
</body>
</html>
"""

@app.route("/download-unserviceables")
def download_unserviceables():
    return send_file("unserviceable_users.csv", as_attachment=True)

@app.route("/download-locations")
def download_locations():
    return send_file("user_locations.csv", as_attachment=True)

@app.route("/download-orders")
def download_orders():
    return send_file("orders.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
