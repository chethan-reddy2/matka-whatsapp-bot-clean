import os
from flask import Flask, request
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

    if incoming_msg in ["hi", "hello", "hey"] or user_states.get(from_number, {}).get("step") == "start":
        # Send interactive greeting using approved template
        try:
            twilio_client.messages.create(
                from_=WHATSAPP_FROM,
                to=from_number,
                content_sid="HXb044cc05b74e2472d4c5838d94c8c6c4"  # Replace with actual template content SID
            )
            user_states[from_number] = {"step": "awaiting_intent"}
            return "Greeting template sent."
        except Exception as e:
            print("❌ Failed to send template:", e)
            return "Error sending template.", 500

    return "Awaiting user message..."

# --------------------- RUN APP -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
