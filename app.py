from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os
from dotenv import load_dotenv
from database import init_db, save_chat

# Load env
load_dotenv()

# Flask
app = Flask(__name__)

# Init DB
init_db()

# Memory
chat_history = []
MAX_HISTORY = 10

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# System prompt
SYSTEM_PROMPT = """
You are a professional medical health assistant.

Rules:
- Provide general health guidance only
- Suggest only OTC medicines
- Provide home remedies
- Provide diet advice
- Provide precautions
- Explain severity level (Mild / Moderate / Serious)
- Clearly tell when to see a doctor
- Detect emergency symptoms
- Never provide prescription medicines
- Never provide dosage for strong drugs
- If unsure → say consult doctor
- Always include disclaimer
- Avoid diagnosis certainty

Respond STRICTLY in this structured format:

Condition:
Severity:
OTC Medicines:
Home Remedies:
Diet:
Precautions:
When to See Doctor:
Disclaimer:
"""

# Home route
@app.route("/")
def home():
    return render_template("index.html")


# Chat route
@app.route("/chat", methods=["POST"])
def chat():

    data = request.json
    user_message = data.get("message", "")
    msg = user_message.lower()

    # 🚨 Emergency detection
    EMERGENCY_KEYWORDS = [
        "chest pain","difficulty breathing","unconscious",
        "severe bleeding","heart attack","stroke",
        "fainting","seizure"
    ]

    if any(word in msg for word in EMERGENCY_KEYWORDS):
        return jsonify({
            "reply": """⚠ POSSIBLE MEDICAL EMERGENCY

Please seek immediate medical attention.

This chatbot cannot handle emergencies."""
        })

    # 🛡 Abuse protection
    BLOCKED = ["kill myself","suicide guide","drug overdose guide","self harm guide"]
    if any(b in msg for b in BLOCKED):
        return jsonify({"reply": "I cannot help with that request."})

    # 🧠 Severity logic
    severity_hint = "unknown"
    if any(w in msg for w in ["severe","worst","intense","unbearable"]):
        severity_hint = "serious"
    elif any(w in msg for w in ["pain","fever","vomiting"]):
        severity_hint = "moderate"
    elif any(w in msg for w in ["slight","mild","little"]):
        severity_hint = "mild"

    # 🌍 Language detection
    lang_hint = "english"
    if any(w in msg for w in ["bukhar","dard","sir","pet","khansi"]):
        lang_hint = "hindi"

    # 👨‍⚕️ Doctor suggestion
    DOCTOR_MAP = {
        "skin": "Dermatologist",
        "stomach": "Gastroenterologist",
        "heart": "Cardiologist",
        "mental": "Psychiatrist",
        "eye": "Ophthalmologist"
    }

    doctor_hint = ""
    for k,v in DOCTOR_MAP.items():
        if k in msg:
            doctor_hint = v

    # 💰 Cost control
    chat_history.append({"role": "user", "content": user_message})
    chat_history[:] = chat_history[-MAX_HISTORY:]

    # 🤖 GPT call (SAFE)
    try:
        print("Calling OpenAI...")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": f"User severity hint: {severity_hint}"},
                {"role": "system", "content": f"Respond language: {lang_hint}"}
            ] + chat_history,
            temperature=0.3
        )

        reply = response.choices[0].message.content
        print("GPT success")

    except Exception as e:
        print("OPENAI ERROR:", e)
        reply = "AI service temporarily unavailable"

    # Add doctor suggestion
    if doctor_hint:
        reply += f"\n\nSuggested Specialist: {doctor_hint}"

    # Save memory + DB
    chat_history.append({"role": "assistant", "content": reply})
    save_chat(user_message, reply)

    return jsonify({"reply": reply})


# Run server
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
