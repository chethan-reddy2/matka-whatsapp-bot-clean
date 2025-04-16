import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

app = Flask(__name__)

# --------------------- TWILIO CONFIG -----------------------
TWILIO_SID = 'AC96d4eedb5a670c040181473cc2710d52'
TWILIO_AUTH = '7b4b18aab19134c83f1db7f22b43a39e'
WHATSAPP_FROM = 'whatsapp:+14134145410'
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# --------------------- USER STATE TRACKER -----------------------
user_states = {}

# --------------------- WHATSAPP ENDPOINT -----------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From")

    resp = MessagingResponse()
    msg = resp.message()

    state = user_states.get(from_number, {"step": "start"})

    # STEP 1: Greeting & Introduction
    if incoming_msg in ["hi", "hello", "hey"] or state["step"] == "start":
        greeting = (
            "👋 Welcome to *Fruit Custard*! 🍓\n\n"
            "We are your one-stop destination for delicious *Fruit Custard*, *Juices*, *Oatmeals*, *Fruit Bowls*, *Delights* & more!\n\n"
            "Please choose why you're here today:"
        )
        msg.body(greeting)
        msg.media("https://i.imgur.com/FruitCustardSample.jpg")

        msg.message().interactive(
            type="button",
            body={"text": "Choose an option:"},
            action={
                "buttons": [
                    {"type": "reply", "reply": {"id": "order_food", "title": "🛵 Order Food"}},
                    {"type": "reply", "reply": {"id": "bulk_order", "title": "📦 Bulk Order"}},
                    {"type": "reply", "reply": {"id": "other_query", "title": "❓ Other Query"}}
                ]
            }
        )
        user_states[from_number] = {"step": "awaiting_intent"}
        return str(resp)

    # STEP 2: Handle button reply for intent
    elif state["step"] == "awaiting_intent":
        if incoming_msg in ["1", "order_food"]:
            msg.body("📍 Please share your location or area name. We deliver only within a 2 km radius from our nearest branch.")
            user_states[from_number] = {"step": "awaiting_location"}
        elif incoming_msg in ["2", "bulk_order"]:
            msg.body("📦 Please tell us more about your bulk order – quantity, occasion, and delivery date. Our team will get in touch soon!")
            user_states[from_number] = {"step": "bulk_query"}
        elif incoming_msg in ["3", "other_query"]:
            msg.body("🤔 Please type your question and we’ll respond as soon as possible!")
            user_states[from_number] = {"step": "other_query"}
        else:
            msg.body("❌ Please choose a valid option from the buttons above.")
        return str(resp)

    # Fallback
    else:
        msg.body("🤖 Type 'hi' to begin your order journey with Fruit Custard!")
        return str(resp)

# --------------------- RUN APP -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
