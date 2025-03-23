import os
import openai
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def classify_emails(emails_json):
    """
    Sends a list of email JSON objects to OpenAI for classification.
    Returns the classification result.
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {
                    "role": "system",
                    "content": "Classify the emails and return only the important ones."
                    # "content": "You're an intelligent email filter assistant. You are given a JSON array of emails, where each email includes the fields \"subject\", \"sender\", and \"snippet\". Your task is to analyze each email and output only those that are important—specifically, emails that are either sent by real people or that clearly require user attention or action. Exclude all emails that are advertisements, marketing messages, newsletters, job alerts, or generic promotional offers. Return your output as a well-formatted JSON array of important emails, where each email includes:\n- \"subject\"\n- \"sender\"\n- \"snippet\"\n- \"action_required\": true\n\nOutput only the JSON without any extra commentary."
                },
                {
                    "role": "user",
                    "content": f"Here are the emails: {emails_json}"
                }
            ],
            temperature=0.3
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        return {"error": str(e)}