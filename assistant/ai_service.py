import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def object_schema(name, properties, required):
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "code": {"type": "string"},
        "code_language": {"type": "string"},
        "hint": {"type": "string"},
        "options": {
            "type": "object",
            "properties": {letter: {"type": "string"} for letter in "ABCD"},
            "required": list("ABCD"),
            "additionalProperties": False,
        },
        "correct_answer": {"type": "string", "enum": list("ABCD")},
        "explanation": {"type": "string"},
    },
    "required": [
        "question", "code", "code_language", "hint", "options",
        "correct_answer", "explanation",
    ],
    "additionalProperties": False,
}

QUIZ_RESPONSE_FORMAT = object_schema(
    "interactive_quiz",
    {"questions": {"type": "array", "items": QUESTION_SCHEMA}},
    ["questions"],
)

FLASHCARDS_RESPONSE_FORMAT = object_schema(
    "study_flashcards",
    {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "front": {"type": "string"},
                    "back": {"type": "string"},
                },
                "required": ["front", "back"],
                "additionalProperties": False,
            },
        }
    },
    ["cards"],
)

TOPIC_CARDS_RESPONSE_FORMAT = object_schema(
    "topic_cards",
    {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "details": {"type": "string"},
                    "example": {"type": "string"},
                    "takeaway": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["science", "technology", "math", "history", "language", "business", "general"],
                    },
                },
                "required": ["title", "summary", "details", "example", "takeaway", "category"],
                "additionalProperties": False,
            },
        }
    },
    ["cards"],
)

STUDY_PLAN_RESPONSE_FORMAT = object_schema(
    "dated_study_plan",
    {
        "overview": {"type": "string"},
        "schedule": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "topic": {"type": "string"},
                    "tasks": {"type": "string"},
                },
                "required": ["date", "topic", "tasks"],
                "additionalProperties": False,
            },
        },
    },
    ["overview", "schedule"],
)


def call_groq_api(prompt, response_format=None, max_tokens=1000):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise Exception("GROQ_API_KEY is missing from your .env file.")

    client = Groq(api_key=api_key)
    request_options = {}
    if response_format is not None:
        request_options["response_format"] = response_format

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=max_tokens,
        **request_options,
    )
    return response.choices[0].message.content


def explain_concept(concept_text):
    prompt = (
        "You are an intelligent study assistant. Explain the following concept "
        "clearly in simple terms with bullet points and key takeaways for a college student:\n\n"
        f"{concept_text}"
    )
    return call_groq_api(prompt)


def summarize_text(input_text):
    prompt = "Summarize the following study material into clear bullet points and main takeaways:\n\n" + input_text
    return call_groq_api(prompt)


def generate_quiz(topic_or_text, num_questions=5, difficulty="medium", topic_focus=""):
    prompt = f"""
    Create exactly {num_questions} multiple-choice questions based on the study material below.
    Difficulty: {difficulty}.
    Use this meaning for the requested level:
    - easy: direct recall and basic understanding.
    - medium: apply ideas or distinguish between related concepts.
    - hard: multi-step reasoning, analysis, or code tracing when relevant.
    Focus on this topic or chapter when provided: {topic_focus or "the most important concepts"}.
    Return a JSON object matching the required schema.

    Rules:
    - Each question has four options A, B, C, and D, with only one correct answer.
    - Keep ordinary questions and options as clear, natural sentences.
    - For code-output questions, put the question sentence in "question" and the complete source code, without fences, in "code". Put its language in "code_language". Preserve syntax, indentation, line breaks, and punctuation. For non-code questions use empty strings for both fields.
    - Add a short helpful hint that guides recall without giving away the answer.
    - Keep answer choices concise; format code in an option using a fenced block if needed.
    - Base every question on the supplied study material.

    Study material:
    {topic_or_text}
    """
    return call_groq_api(prompt, response_format=QUIZ_RESPONSE_FORMAT, max_tokens=4000)


def generate_flashcards(study_material, topic_focus="", num_cards=10):
    prompt = f"""
    Create {num_cards} concise study flashcards from the material below.
    Focus on this topic or chapter when provided: {topic_focus or "the most important concepts"}.
    Return a JSON object with a cards array. Each card has a front (a focused question or prompt) and a back (a clear, accurate answer). Keep code and scientific notation readable as plain text.

    Study material:
    {study_material}
    """
    return call_groq_api(prompt, response_format=FLASHCARDS_RESPONSE_FORMAT, max_tokens=3000)


def generate_topic_cards(topic, study_material="", num_cards=8):
    prompt = f"""
    Create {num_cards} short, colorful study cards that together cover the important details
    of this topic: {topic}. Use the supplied study material when available. Each card must
    cover one distinct idea and stay easy to scan: a short title, a one-sentence summary,
    2-3 concise detail sentences, a simple example or application, and one takeaway.
    Choose a category for each card from science, technology, math, history, language,
    business, or general. Avoid repeating ideas and keep the language accurate for a student.
    Return only JSON matching the required schema.

    Study material:
    {study_material or "No additional notes were provided."}
    """
    return call_groq_api(prompt, response_format=TOPIC_CARDS_RESPONSE_FORMAT, max_tokens=4000)


def generate_study_plan(topics, exam_date, study_material=""):
    prompt = f"""
    Create a practical study plan for the exam on {exam_date}.
    Topics to cover: {topics}
    Use the study material below when available. Distribute review, practice, and recap tasks
    across dates from today through the exam date. Give every date as YYYY-MM-DD. Include
    manageable tasks for each scheduled day and a final recap before the exam.
    Return a JSON object with an overview and a schedule array. Each schedule entry has
    date, topic, and tasks strings.

    Study material:
    {study_material or "No additional notes were provided."}
    """
    return call_groq_api(prompt, response_format=STUDY_PLAN_RESPONSE_FORMAT, max_tokens=3000)
