import streamlit as st  # Streamlit for building the web UI
from openai import OpenAI  # OpenAI client to access GPT models
import datetime  # For date handling
import json  # For working with JSON data
import re  # For regular expressions (unused here but imported)
from typing import List  # For type hinting
from pdf_builder import build_pdf  # Custom function to build PDF from JSON data
from tts import text_to_speech  # Custom TTS module for speech output
from stt import speech_to_text  # Custom STT module using Whisper
from json_builder import extract_prescription_data  # Extracts data for PDF formatting
from ocr import perform_ocr  # OCR function using PaddleOCR
from mtest_data_parser import extract_text_from_json  # Extracts text from OCR output JSON
from detect_fracture import predict_fracture  # Fracture prediction function using CNN models
import whisper  # OpenAI Whisper speech-to-text model
from multiprocessing import Process  # For possible parallel tasks (unused here)
import os
from dotenv import load_dotenv

load_dotenv()

# Load configuration from .env file
API_KEY = os.getenv('LLM_API_KEY')
BASE_URL = os.getenv('LLM_BASE_URL')
MODEL = os.getenv('LLM_MODEL')
MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS', 10000))  # Default to 10000 if not set
TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', 0.3))  # Default to 0.3 if not set

# Initializing OpenAI client with OpenRouter base URL
client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

@st.cache_resource  # Cache Whisper model to avoid reloading on every run
def load_whisper_model():
    return whisper.load_model("medium")  # Load the medium version of Whisper model

# Sends a message list to the AI and returns the response text
def ask_ai(messages):
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    return response.choices[0].message.content  # Return only the content part of the response

# Main app function
def app():
    with st.spinner('Loading voice model...'):  # Show loading spinner while loading Whisper
        model = load_whisper_model()

    st.title("🩺 AI Doctor - Virtual Medical Assistant")  # App title

    # Collect basic user info
    name = st.text_input("Enter your name:")
    age = st.text_input("Enter your age:")
    gender = st.radio("What's your gender?", ["Male", "Female"])
    
    if name and age:
        st.markdown("### Upload Medical Files (optional)")
        xray_image = st.file_uploader("Upload X-ray Image (JPEG/PNG)", type=["jpg", "jpeg", "png"])  # X-ray input
        test_report = st.file_uploader("Upload Test Report (Image or JSON)", type=["jpg", "jpeg", "png", "json"])  # Test report input

        use_voice = st.radio("Do you want to use voice for communication?", ["Yes", "No"])  # Choose voice or text input

        symptom = ""
        if use_voice == "Yes":
            st.write("Please speak your symptoms when ready...")
            if st.button("Start Recording"):
                text_to_speech("Please describe your symptoms. Please speak when told to do so.")
                symptom = speech_to_text(model)  # Use Whisper STT
                st.session_state.symptom = symptom
                st.success(f"You said: {symptom}")
        else:
            symptom = st.text_area("Describe your symptoms:")
            st.session_state.symptom = symptom  # Store symptom for later use

        if "prescription_ready" not in st.session_state:
            st.session_state.prescription_ready = False  # Flag to check if prescription is ready

        # Start diagnosis and prescription generation
        if st.button("Generate Prescription") and st.session_state.symptom.strip():
            fracture_status = ""
            if xray_image:
                with open("xray_image.jpeg", "wb") as f:
                    f.write(xray_image.read())  # Save uploaded image locally
                fracture_status = predict_fracture("xray_image.jpeg")  # Predict fracture
            else:
                fracture_status = "No X-ray image provided."

            inform_user = "User does not know about the findings in the X-ray image. Please inform them about the findings through your questions. Please do not forget to tell user about their status on X-ray. Just respond in one line. Don't ask any question just inform."

            # Compose messages for initial AI prompt
            messages = [
                {"role": "system", "content": f"User uploaded an X-ray image. Please strongly consider this when generating prescription. We have detected the following fracture status: {fracture_status}"},
                {"role": "system", "content": inform_user},
                {"role": "system", "content": f"You are a professional AI doctor. Start by asking medical follow-up questions (more than 7 questions) to better understand the patient's condition. (Just asks questions nothing more and all the questions should be separated by new lines and questions are to be asked by speech so make sure to use simple language and be professional) {inform_user}"},
                {"role": "user", "content": f"My name is {name}, I am {age} years old and {gender}. I am experiencing: {st.session_state.symptom}"}
            ]

            ai_response = ask_ai(messages)  # Get follow-up questions from AI
            ai_questions = [q.strip() + "?" for q in ai_response.split("?") if q.strip()]  # Clean and split questions

            # Save session state for questions/answers
            st.session_state.messages = messages
            st.session_state.questions = ai_questions
            st.session_state.answers = []
            st.session_state.question_index = 0
            st.session_state.prescription_ready = False
            st.rerun()  # Restart Streamlit run to load questions

        # Question/Answer phase
        if "questions" in st.session_state and not st.session_state.prescription_ready:
            current_index = st.session_state.question_index
            questions = st.session_state.questions
            if current_index < len(questions):
                current_question = questions[current_index]
                st.subheader("🤖 Follow-Up Question")
                st.write(current_question)

                if use_voice == "Yes":
                    text_to_speech(current_question)
                    if st.button("🎤 Record Voice Answer"):
                        answer = speech_to_text(model)  # Voice answer
                        st.session_state.voice_answer = answer
                        st.success(f"You said: {answer}")

                    if "voice_answer" in st.session_state and st.session_state.voice_answer:
                        if st.button("Submit Voice Answer"):
                            st.session_state.answers.append(st.session_state.voice_answer)
                            st.session_state.question_index += 1
                            del st.session_state.voice_answer
                            st.rerun()
                else:
                    temp_key = f"temp_answer_{current_index}"
                    if temp_key not in st.session_state:
                        st.session_state[temp_key] = ""

                    # Manual text answer
                    st.session_state[temp_key] = st.text_input(
                        "Your answer:", value=st.session_state[temp_key], key=f"q_{current_index}"
                    )

                    if st.button("Submit Answer"):
                        answer = st.session_state[temp_key]
                        st.session_state.answers.append(answer)
                        st.session_state.question_index += 1
                        st.rerun()

            else:
                # All questions answered
                st.success("✅ All follow-up questions answered.")
                qna = "\n".join([
                    f"Your question: {st.session_state.questions[i]} My answer: {st.session_state.answers[i]}"
                    for i in range(len(st.session_state.answers))
                ])
                st.session_state.messages.append({"role": "user", "content": qna})

                # OCR on test report (if provided)
                if test_report:
                    test_path = "uploaded_test"
                    if test_report.name.endswith(".json"):
                        with open(f"{test_path}.json", "wb") as f:
                            f.write(test_report.read())
                        test_ocr = extract_text_from_json(f"{test_path}.json")
                    else:
                        with open(f"{test_path}.png", "wb") as f:
                            f.write(test_report.read())
                        perform_ocr(f"{test_path}.png")
                        test_ocr = extract_text_from_json("output/large_res.json")
                    st.session_state.messages.append({
                        "role": "user",
                        "content": f"This is the OCR output of the uploaded medical test report. Please consider this information while generating the prescription. The OCR output is as follows:\n\n{test_ocr}"
                    })

                # Prompt to generate prescription
                today = datetime.date.today().strftime("%B %d, %Y")
                prescription_prompt = f"""
                Based on the information above, generate a complete medical prescription in the following format. Be professional, use generic medication names when possible, and ensure it's understandable by pharmacists.

                ---
                **Medical Prescription**

                **Patient Information**: {name}, {age} years old, Gender: {gender.capitalize()}
                **Date**: {today}

                **Diagnosis**: [Insert accurate diagnosis based on previous discussion]

                **Medication**:  
                - **Name**: [Generic Name] (Brand Name according to Pakistani Market)  
                - **Dosage and Route**: [e.g., 500mg orally]  
                - **Frequency and Duration**: [e.g., Twice a day for 5 days]  
                - **Refills**: [e.g., None / 1 refill]  
                - **Special Instructions**: [e.g., Take with food, avoid alcohol]

                **Non-Pharmacological Recommendations**

                **Medical Tests Recommended**

                **Reasoning**: Please provide a brief reasoning for the diagnosis and medication choices. (The tone should be simple and undersandable by patient as a normal person)

                **Prescriber**: Dr. AI Medic. MD
                ---
                """
                st.session_state.messages.append({"role": "user", "content": prescription_prompt})
                original_response = ask_ai(st.session_state.messages)  # Ask AI for full prescription

                st.subheader("📄 Final Prescription")
                st.markdown(original_response)  # Display full response

                # Extract reasoning part for TTS
                reasoning_start = original_response.find("**Reasoning**:")
                reasoning_end = original_response.find("**Prescriber**")

                reasoning = original_response[reasoning_start + len("**Reasoning**:"):reasoning_end].strip()

                # Trim and prepare final prescription
                final_response = original_response[:reasoning_start].rstrip() + "\n\n**Prescriber**: Dr. AI Medic. MD\n---"

                # Convert reasoning to speech
                text_to_speech(reasoning.replace('e.g.', 'for example').replace('i.e.', 'that is'))

                # Build PDF and allow download
                data = extract_prescription_data(final_response)
                with open("prescription.json", "w") as f:
                    json.dump(data, f, indent=2)

                prescription_path = build_pdf("prescription.json")

                st.session_state.prescription_ready = True
                st.success("✅ Prescription generated successfully! Below is the download link.")

                with open(prescription_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Prescription PDF",
                        data=f,
                        file_name="prescription.pdf",
                        mime="application/pdf"
                    )

# Run app when script is executed directly
if __name__ == "__main__":
    app()
