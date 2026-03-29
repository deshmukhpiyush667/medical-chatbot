from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
import requests
import json

# ===============================
# Load Environment Variables
# ===============================
# Try loading from config.env locally, fall back to system env vars on Vercel
load_dotenv("config.env")
load_dotenv()  # Also try loading from .env

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

if not OPENROUTER_API_KEY:
    print("WARNING: OPENROUTER_API_KEY not found in environment variables")

# ===============================
# Flask App
# ===============================
app = Flask(__name__)

# ===============================
# Memory
# ===============================
chat_history = []
MAX_HISTORY = 10

# ===============================
# Currently Working Free Models (March 2026)
# ===============================
FREE_MODELS = [
    "openrouter/free",                              # Auto-router — always picks an available free model
    "meta-llama/llama-3.3-70b-instruct:free",      # Best quality free model
    "mistralai/mistral-small-3.1-24b-instruct:free", # Great multilingual support
    "google/gemma-3-27b-it:free",                  # Google's best free model
    "google/gemma-3-12b-it:free",                  # Fallback
    "meta-llama/llama-3.2-3b-instruct:free",       # Fast lightweight fallback
    "google/gemma-3-4b-it:free",                   # Last resort
]

VISION_MODELS = [
    "mistralai/mistral-small-3.1-24b-instruct:free",  # Free + vision capable
    "google/gemma-3-27b-it:free",                     # Free + vision capable
    "google/gemma-3-12b-it:free",                     # Free + vision capable
    "google/gemma-3-4b-it:free",                      # Free + vision capable
    "openai/gpt-4o-mini",                             # Paid fallback
]

# ===============================
# System Prompts per Language
# ===============================
SYSTEM_PROMPTS = {
    "english": """
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
- Avoid diagnosis certainty

Respond STRICTLY in this structured format IN ENGLISH:

Condition:
Severity:
OTC Medicines:
Home Remedies:
Diet:
Precautions:
When to See Doctor:
Disclaimer:
""",
    "hindi": """
Aap ek professional medical health assistant hain.

Niyam:
- Sirf general health guidance dijiye
- Sirf OTC medicines suggest karein
- Gharelu nuskhe batayein
- Diet ki salah dijiye
- Savdhaniyaan batayein
- Gambhirta batayein (Halka / Madhyam / Gambhir)
- Doctor ke paas kab jaana chahiye clearly batayein
- Emergency symptoms detect karein
- Prescription medicines kabhi mat dijiye
- Diagnosis mein certainty se bachein

BILKUL IS FORMAT MEIN HINDI MEIN JAWAB DIJIYE:

Stithi (Condition):
Gambhirta (Severity):
OTC Dawayein (OTC Medicines):
Gharelu Nuskhe (Home Remedies):
Aahar (Diet):
Savdhaniyaan (Precautions):
Doctor Kab Milein (When to See Doctor):
Asvikaran (Disclaimer):
""",
    "marathi": """
Aap ek professional medical health assistant aahat.

Niyam:
- Fakt general health margadarshan dya
- Fakt OTC aushadhe suchva
- Gharachi upay sangya
- Aaharachi salaha dya
- Khobaryaa sangya
- Tamachya gambhirteche varnan kara (Sadharan / Madhyam / Gambhir)
- Doctor kadhi bheta hya he spashta sanga
- Emergency lakshane olvya
- Prescription aushadhe khadhi nahi dyu naka
- Nishchit nidan uggalvu naka

KHAALYAPRAMAANE FORMAT MAADHYE MARATHIT UTTAR DYA:

Sthiti (Condition):
Gambhirta (Severity):
OTC Aushadhe (OTC Medicines):
Gharguti Upay (Home Remedies):
Aahar (Diet):
Khobaryaa (Precautions):
Doctor Kadhi Bheta (When to See Doctor):
Asvikruti (Disclaimer):
"""
}

# ===============================
# Emergency Keywords
# ===============================
EMERGENCY_KEYWORDS = {
    "english": ["chest pain", "difficulty breathing", "unconscious",
                "severe bleeding", "heart attack", "stroke", "fainting", "seizure"],
    "hindi":   ["seene mein dard", "sans lene mein takleef", "behosh",
                "bahut khoon", "dil ka daura", "paralysis", "behoshi", "mirgi",
                "chest pain", "heart attack"],
    "marathi": ["chhatit dukh", "shvas ghenyat trasas", "shahaara",
                "jast rakta", "hriday vikaar", "paksha-ghaat",
                "moorcha", "aakshan", "chest pain", "heart attack"]
}

EMERGENCY_RESPONSES = {
    "english": "⚠️ POSSIBLE MEDICAL EMERGENCY\n\nPlease seek immediate medical attention or call emergency services (112).",
    "hindi":   "⚠️ SAMBHAV CHIKITSA AAPATKAL\n\nKripaya turant chikitsa sahayata lein ya 112 call karein.",
    "marathi": "⚠️ SAMBHAVIT VAIDYAKIYA AAPATKAALIN STHITI\n\nKrupaya tatkaal madad ghya kinva 112 la call kara."
}

BLOCKED = ["kill myself", "suicide guide", "drug overdose guide", "self harm guide"]

# ===============================
# Language Detection
# ===============================
HINDI_KEYWORDS = [
    "bukhar","dard","sir","pet","khansi","nabz","dawai","bimari","seene",
    "mujhe","mera","meri","kya","kaise","bahut","thoda","sar","ulti",
    "thakaan","naak","gala","aankh","haath","paer","pait"
]
MARATHI_KEYWORDS = [
    "dukh","taap","khokla","poti","dokyat","aushadh","rog","aajar",
    "mala","majha","majhi","kay","kasa","khup","nakaat",
    "ghasat","ulaati","thakawa","paay","shkam","chhatit","shwas","dokedukhi"
]

def detect_language(msg):
    msg_lower = msg.lower()
    marathi_count = sum(1 for w in MARATHI_KEYWORDS if w in msg_lower)
    hindi_count   = sum(1 for w in HINDI_KEYWORDS   if w in msg_lower)
    if marathi_count > hindi_count and marathi_count > 0:
        return "marathi"
    elif hindi_count > 0:
        return "hindi"
    return "english"

# ===============================
# Doctor Map
# ===============================
DOCTOR_MAP = {
    "skin": "Dermatologist",       "stomach": "Gastroenterologist",
    "heart": "Cardiologist",       "mental": "Psychiatrist",
    "eye": "Ophthalmologist",      "dil": "Cardiologist",
    "aankh": "Ophthalmologist",    "pet": "Gastroenterologist",
    "chamdi": "Dermatologist",     "kaadha": "Gastroenterologist",
    "dola": "Ophthalmologist"
}
DOCTOR_LABEL = {
    "english": "Suggested Specialist",
    "hindi":   "Sujhaya Gaya Visheshagy",
    "marathi": "Suchavlela Tataj"
}

# ===============================
# Core helper — call OpenRouter with fallback
# ===============================
def call_openrouter(messages_payload, models, max_tokens=1024):
    """Try each model in order. Returns (reply_text, model_used) or (None, error_str)."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost:5000",
        "X-Title":       "MediMind AI"
    }
    last_error = "No models tried"

    for model in models:
        try:
            payload = {
                "model":      model,
                "messages":   messages_payload,
                "max_tokens": max_tokens
            }
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            result = response.json()

            if "error" in result:
                last_error = result["error"].get("message", str(result["error"]))
                print(f"[{model}] API error: {last_error}")
                continue

            choices = result.get("choices") or []
            if not choices:
                last_error = f"Empty choices from {model}"
                print(f"[{model}] No choices returned")
                continue

            reply = (choices[0].get("message") or {}).get("content", "").strip()
            if not reply:
                last_error = f"Empty content from {model}"
                continue

            print(f"✅ Success with: {model}")
            return reply, model

        except requests.exceptions.Timeout:
            last_error = f"{model} timed out"
            print(f"[{model}] Timeout")
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {e}"
            print(f"[{model}] Connection error")
        except Exception as e:
            last_error = str(e)
            print(f"[{model}] Error: {e}")

    return None, last_error

# ===============================
# Home Route
# ===============================
@app.route("/")
def home():
    return render_template("index.html")

# ===============================
# Chat Route
# ===============================
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data         = request.get_json(force=True, silent=True) or {}
        user_message = str(data.get("message", "")).strip()

        if not user_message:
            return jsonify({"reply": "Please type a message.", "detected_lang": "english"})

        preferred_lang = data.get("language", "auto")
        msg = user_message.lower()

        # Language detection
        lang = preferred_lang if preferred_lang in ("hindi","marathi","english") else detect_language(msg)

        # Emergency check
        all_emergency = (EMERGENCY_KEYWORDS["english"]
                       + EMERGENCY_KEYWORDS["hindi"]
                       + EMERGENCY_KEYWORDS["marathi"])
        if any(word in msg for word in all_emergency):
            return jsonify({"reply": EMERGENCY_RESPONSES[lang], "detected_lang": lang})

        # Blocked content
        if any(b in msg for b in BLOCKED):
            return jsonify({"reply": "I cannot help with that request.", "detected_lang": lang})

        # Severity
        severity_hint = "unknown"
        if any(w in msg for w in ["severe","worst","intense","unbearable","bahut tez","khup jast","gambhir"]):
            severity_hint = "serious"
        elif any(w in msg for w in ["pain","fever","vomiting","dard","bukhar","ulti","dukh","taap"]):
            severity_hint = "moderate"
        elif any(w in msg for w in ["slight","mild","little","thoda","halka","sadharan"]):
            severity_hint = "mild"

        # Doctor suggestion
        doctor_hint = ""
        for k, v in DOCTOR_MAP.items():
            if k in msg:
                doctor_hint = v

        # Build chat history
        chat_history.append({"role": "user", "content": user_message})
        chat_history[:] = chat_history[-MAX_HISTORY:]

        messages_payload = [
            {"role": "system", "content": SYSTEM_PROMPTS[lang]},
            {"role": "system", "content": f"User severity hint: {severity_hint}"},
            {"role": "system", "content": f"Respond ONLY in language: {lang}. Do not mix languages."}
        ] + chat_history

        # Call API
        reply, model_used = call_openrouter(messages_payload, FREE_MODELS)

        if reply is None:
            error_msgs = {
                "english": f"⚠️ All AI models are currently unavailable.\n\nError: {model_used}\n\nPlease try again in a moment.",
                "hindi":   "⚠️ AI seva abhi uplabdh nahin hai. Thodi der baad dobara koshish karein.",
                "marathi": "⚠️ AI seva sadhya upalabdh nahi. Thodi vel nantar parat prayas kara."
            }
            reply = error_msgs[lang]
        else:
            chat_history.append({"role": "assistant", "content": reply})

        if doctor_hint:
            reply += f"\n\n{DOCTOR_LABEL[lang]}: {doctor_hint}"

        return jsonify({"reply": reply, "detected_lang": lang})

    except Exception as e:
        print(f"❌ CHAT CRASH: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"reply": f"⚠️ Server error: {str(e)}", "detected_lang": "english"}), 500


# ===============================
# Skin Image Analysis Route
# ===============================
SKIN_SYSTEM_PROMPTS = {
    "english": """You are a medical AI assistant specializing in skin and dermatology analysis.
Analyze the skin/rash image and respond STRICTLY in this format:

Visual Observation:
Possible Conditions:
Severity Estimate:
OTC Care:
Home Remedies:
Warning Signs to Watch:
When to See Doctor:
Disclaimer:""",

    "hindi": """Aap ek skin specialist medical AI assistant hain.
IS FORMAT MEIN JAWAB DIJIYE:
Drishtikon (Visual Observation):
Sambhav Stithi (Possible Conditions):
Gambhirta Anuman (Severity Estimate):
OTC Upchar (OTC Care):
Gharelu Nuskhe (Home Remedies):
Khatarnak Lakshan (Warning Signs):
Doctor Kab Milein (When to See Doctor):
Asvikaran (Disclaimer):""",

    "marathi": """Aap ek tvachaa specialist medical AI assistant aahat.
YA FORMAT MADHYE UTTAR DYA:
Drushya Nirikshan (Visual Observation):
Sambhavit Sthiti (Possible Conditions):
Gambhirta Anuman (Severity Estimate):
OTC Kalatji (OTC Care):
Gharguti Upay (Home Remedies):
Dhokyadayak Lakshane (Warning Signs):
Doctor Kadhi Bheta (When to See Doctor):
Asvikruti (Disclaimer):"""
}

@app.route("/analyze-image", methods=["POST"])
def analyze_image():
    try:
        data           = request.get_json(force=True, silent=True) or {}
        image_base64   = data.get("image_base64", "").strip()
        symptoms       = data.get("symptoms", "").strip()
        preferred_lang = data.get("language", "english")
        mime_type      = data.get("mime_type", "image/jpeg")

        lang = preferred_lang if preferred_lang in ("hindi","marathi","english") else "english"

        if not image_base64:
            return jsonify({"reply": "⚠️ No image received. Please upload an image first."}), 400
        if len(image_base64) > 7_000_000:
            return jsonify({"reply": "⚠️ Image too large. Please upload under 5 MB."}), 400

        allowed_mimes = {"image/jpeg","image/png","image/webp","image/gif"}
        if mime_type not in allowed_mimes:
            mime_type = "image/jpeg"

        user_text = "Carefully analyze this skin/rash image and provide a detailed medical assessment."
        if symptoms:
            user_text += f" Patient also reports: {symptoms}"

        messages_payload = [
    {"role": "system", "content": SKIN_SYSTEM_PROMPTS[lang]},
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_base64}"
                }
            },
            {
                "type": "text",
                "text": user_text
            }
        ]
    }
]

        reply, model_used = call_openrouter(messages_payload, VISION_MODELS, max_tokens=1024)

        if reply is None:
            error_msgs = {
                "english": f"⚠️ Image analysis failed: {model_used}\n\nPlease describe your symptoms in text instead.",
                "hindi":   "⚠️ Image vishleshan fail hua. Lakshan text mein type karein.",
                "marathi": "⚠️ Image vishleshan aayashasta. Lakshane text madhe type kara."
            }
            return jsonify({"reply": error_msgs[lang], "detected_lang": lang})

        return jsonify({"reply": reply, "detected_lang": lang, "model_used": model_used})

    except Exception as e:
        print(f"❌ IMAGE CRASH: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"reply": f"⚠️ Server error: {str(e)}"}), 500


# ===============================
# Run Server
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
