import json
from collections import Counter
from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.http import FileResponse, HttpResponseBadRequest, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from pypdf import PdfReader

from .ai_service import (
    explain_concept,
    generate_flashcards,
    generate_quiz,
    generate_study_plan,
    generate_topic_cards,
    summarize_text,
)
from .exports import make_docx, make_pdf
from .models import Bookmark, QuestionBankItem, QuizAttempt, StudySession


DIFFICULTY_LEVELS = ("easy", "medium", "hard")


def recommended_quiz_difficulty(user):
    """Choose the next adaptive level using the user's latest completed quiz."""
    previous = QuizAttempt.objects.filter(user=user).first()
    if previous is None:
        return "medium", "Your first adaptive quiz starts at medium difficulty. Your score will guide the next one."

    percentage = round(100 * previous.score / previous.total_questions) if previous.total_questions else 0
    current = previous.difficulty if previous.difficulty in DIFFICULTY_LEVELS else "medium"
    level_index = DIFFICULTY_LEVELS.index(current)
    if percentage >= 80:
        next_level = DIFFICULTY_LEVELS[min(level_index + 1, len(DIFFICULTY_LEVELS) - 1)]
        reason = "Great result: your last quiz score was {}%, so the challenge is increasing.".format(percentage)
    elif percentage < 50:
        next_level = DIFFICULTY_LEVELS[max(level_index - 1, 0)]
        reason = "Your last quiz score was {}%, so the next quiz is set to reinforce the basics.".format(percentage)
    else:
        next_level = current
        reason = "Your last quiz score was {}%, so the difficulty stays steady while you build confidence.".format(percentage)
    return next_level, reason


def signup(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("index")
    return render(request, "registration/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get("next") or "index")
    return render(request, "registration/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    sessions = StudySession.objects.filter(user=request.user).order_by("-created_at")
    attempts = list(QuizAttempt.objects.filter(user=request.user))
    bookmarks_count = Bookmark.objects.filter(user=request.user).count()
    total_questions = sum(attempt.total_questions for attempt in attempts)
    total_correct = sum(attempt.score for attempt in attempts)
    average_score = round(100 * total_correct / total_questions) if total_questions else 0

    today = timezone.localdate()
    activity_dates = {
        timezone.localtime(session.created_at).date()
        for session in sessions
        if session.created_at
    }
    activity_dates.update(
        timezone.localtime(attempt.created_at).date()
        for attempt in attempts
        if attempt.created_at
    )

    longest_streak = 0
    current_run = 0
    previous_day = None
    for active_day in sorted(activity_dates):
        if previous_day is not None and active_day == previous_day + timedelta(days=1):
            current_run += 1
        else:
            current_run = 1
        longest_streak = max(longest_streak, current_run)
        previous_day = active_day

    streak_day = today if today in activity_dates else today - timedelta(days=1)
    current_streak = 0
    while streak_day in activity_dates:
        current_streak += 1
        streak_day -= timedelta(days=1)

    recent_days = []
    session_dates = Counter(
        timezone.localtime(session.created_at).date() for session in sessions if session.created_at
    )
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        recent_days.append({
            "label": day.strftime("%a"),
            "date": day.strftime("%b %d"),
            "count": session_dates.get(day, 0),
        })

    max_day_count = max((item["count"] for item in recent_days), default=1) or 1
    for item in recent_days:
        item["percent"] = round(100 * item["count"] / max_day_count) if item["count"] else 4

    next_difficulty, adaptive_hint = recommended_quiz_difficulty(request.user)

    topic_counts = Counter()
    for session in sessions:
        topic = session.metadata.get("topic") or session.metadata.get("topic_focus") or session.user_input
        if topic:
            topic_counts[str(topic).split("\n", 1)[0].strip()[:80]] += 1

    return render(request, "assistant/dashboard.html", {
        "account_name": request.user.get_full_name() or request.user.username,
        "total_sessions": sessions.count(),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "quiz_count": len(attempts),
        "average_score": average_score,
        "bookmarks_count": bookmarks_count,
        "question_bank_count": QuestionBankItem.objects.filter(user=request.user).count(),
        "next_difficulty": next_difficulty,
        "adaptive_hint": adaptive_hint,
        "total_questions": total_questions,
        "recent_days": recent_days,
        "recent_sessions": sessions.filter(history_cleared=False)[:8],
        "top_topics": topic_counts.most_common(5),
    })


@login_required
def question_bank(request):
    items = QuestionBankItem.objects.filter(user=request.user)
    search = request.GET.get("q", "").strip()
    selected_subject = request.GET.get("subject", "").strip()
    selected_topic = request.GET.get("topic", "").strip()

    if selected_subject:
        items = items.filter(subject=selected_subject)
    if selected_topic:
        items = items.filter(topic=selected_topic)
    if search:
        items = items.filter(
            Q(question__icontains=search)
            | Q(code__icontains=search)
            | Q(subject__icontains=search)
            | Q(topic__icontains=search)
        )

    for item in items:
        item.option_rows = [(letter, item.options.get(letter, "")) for letter in "ABCD"]
        item.correct_option = item.options.get(item.correct_answer, "")

    subject_items = QuestionBankItem.objects.filter(user=request.user).exclude(subject="").values_list("subject", flat=True).distinct().order_by("subject")
    topic_items = QuestionBankItem.objects.filter(user=request.user)
    if selected_subject:
        topic_items = topic_items.filter(subject=selected_subject)
    topic_items = topic_items.exclude(topic="").values_list("topic", flat=True).distinct().order_by("topic")

    return render(request, "assistant/question_bank.html", {
        "items": items,
        "search": search,
        "subjects": subject_items,
        "topics": topic_items,
        "selected_subject": selected_subject,
        "selected_topic": selected_topic,
        "bank_count": QuestionBankItem.objects.filter(user=request.user).count(),
        "account_name": request.user.get_full_name() or request.user.username,
    })


@login_required
def index(request):
    result = None
    quiz_data = None
    flashcards_data = None
    topic_cards_data = None
    plan_data = None
    quiz_session_id = None
    task_type = "explain"
    user_input = ""
    error_message = None
    topic_focus = ""
    quiz_subject = ""
    study_topics = ""
    difficulty_mode = "adaptive"
    difficulty, difficulty_hint = recommended_quiz_difficulty(request.user)
    question_count = 5
    exam_date = ""
    topic_cards_topic = ""

    if request.method == "POST":
        user_input = request.POST.get("user_input", "").strip()
        task_type = request.POST.get("task_type", "explain")
        topic_focus = request.POST.get("topic_focus", "").strip()
        quiz_subject = request.POST.get("quiz_subject", "").strip()[:120]
        study_topics = request.POST.get("study_topics", "").strip()
        difficulty_mode = request.POST.get("difficulty", "adaptive")
        if difficulty_mode == "adaptive":
            difficulty, difficulty_hint = recommended_quiz_difficulty(request.user)
        elif difficulty_mode in DIFFICULTY_LEVELS:
            difficulty = difficulty_mode
            difficulty_hint = "Manual difficulty selected: {}.".format(difficulty.title())
        else:
            difficulty_mode = "adaptive"
            difficulty, difficulty_hint = recommended_quiz_difficulty(request.user)
        try:
            question_count = max(1, min(10, int(request.POST.get("question_count", 5))))
        except (TypeError, ValueError):
            question_count = 5
        exam_date = request.POST.get("exam_date", "").strip()
        topic_cards_topic = request.POST.get("topic_cards_topic", "").strip()

        pdf_file = request.FILES.get("pdf_file")
        pdf_text = ""
        if pdf_file:
            try:
                reader = PdfReader(pdf_file)
                pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
                if not pdf_text.strip():
                    error_message = "No readable text found in the PDF."
            except Exception as exc:
                error_message = f"PDF processing error: {exc}"

        if pdf_text.strip():
            user_input = (user_input + "\n\nPDF Content:\n" + pdf_text).strip()

        if task_type == "topic_cards" and topic_cards_topic:
            user_input = topic_cards_topic
        has_study_material = bool(user_input.strip() or study_topics)
        if task_type == "topic_cards" and not topic_cards_topic and not user_input:
            error_message = "Enter a topic to create topic cards."
        elif task_type == "study_plan":
            try:
                parsed_exam_date = date.fromisoformat(exam_date)
                if parsed_exam_date < date.today():
                    raise ValueError
            except ValueError:
                error_message = "Choose an exam date today or later to create a study plan."
            if not (study_topics or user_input):
                error_message = "Enter the topics for your study plan."
        elif not has_study_material and not error_message:
            error_message = "Please enter text or upload a PDF."

        if not error_message:
            try:
                metadata = {}
                saved_response = None
                if task_type == "explain":
                    result = explain_concept(user_input)
                elif task_type == "summarize":
                    result = summarize_text(user_input)
                elif task_type == "quiz":
                    quiz_data = json.loads(generate_quiz(user_input, question_count, difficulty, topic_focus))
                    questions = quiz_data.get("questions") if isinstance(quiz_data, dict) else None
                    if not isinstance(questions, list) or not questions:
                        raise ValueError("The quiz response did not contain questions.")
                    for question in questions:
                        if not isinstance(question, dict):
                            raise ValueError("The quiz response contains an invalid question.")
                        options = question.get("options")
                        if (
                            not question.get("question")
                            or not isinstance(options, dict)
                            or any(not options.get(key) for key in "ABCD")
                            or question.get("correct_answer") not in {"A", "B", "C", "D"}
                        ):
                            raise ValueError("The quiz response contains an incomplete question.")
                        question.setdefault("code", "")
                        question.setdefault("code_language", "")
                        question.setdefault("hint", "")
                        question.setdefault("explanation", "")
                    metadata = {
                        "difficulty": difficulty,
                        "difficulty_mode": difficulty_mode,
                        "question_count": len(questions),
                        "topic_focus": topic_focus,
                        "subject": quiz_subject or "General",
                        "topic": topic_focus or (user_input.splitlines()[0][:255] if user_input.splitlines() else "General"),
                    }
                    saved_response = json.dumps(quiz_data)
                elif task_type == "flashcards":
                    flashcards_data = json.loads(generate_flashcards(user_input, topic_focus))
                    cards = flashcards_data.get("cards") if isinstance(flashcards_data, dict) else None
                    if not isinstance(cards, list) or not cards or any(
                        not isinstance(card, dict) or not card.get("front") or not card.get("back")
                        for card in cards
                    ):
                        raise ValueError("The flashcard response was incomplete.")
                    saved_response = json.dumps(flashcards_data)
                    metadata = {"topic_focus": topic_focus}
                elif task_type == "topic_cards":
                    topic_cards_data = json.loads(generate_topic_cards(topic_cards_topic or user_input, user_input))
                    cards = topic_cards_data.get("cards") if isinstance(topic_cards_data, dict) else None
                    if not isinstance(cards, list) or not cards:
                        raise ValueError("The topic cards response was incomplete.")
                    for card in cards:
                        if (
                            not isinstance(card, dict)
                            or not card.get("title")
                            or not card.get("summary")
                            or not card.get("details")
                            or not card.get("example")
                            or not card.get("takeaway")
                            or card.get("category") not in {"science", "technology", "math", "history", "language", "business", "general"}
                        ):
                            raise ValueError("The topic cards response contains an incomplete card.")
                    saved_response = json.dumps(topic_cards_data)
                    metadata = {"topic": topic_cards_topic or user_input, "card_count": len(cards)}
                elif task_type == "study_plan":
                    plan_topics = study_topics or topic_focus or user_input
                    plan_data = json.loads(generate_study_plan(plan_topics, exam_date, user_input))
                    schedule = plan_data.get("schedule") if isinstance(plan_data, dict) else None
                    if not isinstance(schedule, list) or not schedule:
                        raise ValueError("The study plan response was incomplete.")
                    for item in schedule:
                        if not isinstance(item, dict) or not item.get("date") or not item.get("topic") or not item.get("tasks"):
                            raise ValueError("The study plan response contains an incomplete day.")
                    saved_response = json.dumps(plan_data)
                    metadata = {"exam_date": exam_date, "study_topics": plan_topics}
                else:
                    error_message = "Choose a valid study task."

                if result or saved_response:
                    session = StudySession.objects.create(
                        user=request.user,
                        user_input=user_input or study_topics,
                        task_type=task_type,
                        ai_response=saved_response if saved_response is not None else result,
                        metadata=metadata,
                    )
                    if task_type == "quiz":
                        quiz_session_id = session.pk
            except json.JSONDecodeError:
                error_message = "The AI returned data in an unexpected format. Please try again."
                quiz_data = flashcards_data = topic_cards_data = plan_data = None
            except ValueError as exc:
                error_message = f"Could not use the AI response: {exc}"
                quiz_data = flashcards_data = topic_cards_data = plan_data = None
            except Exception as exc:
                error_message = f"AI Error: {exc}"

    history = StudySession.objects.filter(
        user=request.user,
        history_cleared=False,
    ).order_by("-created_at")[:5]
    attempts = QuizAttempt.objects.filter(
        user=request.user,
        history_cleared=False,
    )[:8]
    progress = [
        {
            "topic": attempt.topic or "Quiz",
            "score": attempt.score,
            "total": attempt.total_questions,
            "percent": round(100 * attempt.score / attempt.total_questions) if attempt.total_questions else 0,
            "created_at": attempt.created_at,
        }
        for attempt in attempts
    ]

    return render(request, "assistant/index.html", {
        "result": result,
        "quiz_data": quiz_data,
        "quiz_session_id": quiz_session_id,
        "flashcards_data": flashcards_data,
        "topic_cards_data": topic_cards_data,
        "plan_data": plan_data,
        "task_type": task_type,
        "user_input": user_input,
        "history": history,
        "bookmarks": Bookmark.objects.filter(user=request.user)[:8],
        "account_name": request.user.get_full_name() or request.user.username,
        "progress": progress,
        "error_message": error_message,
        "topic_focus": topic_focus,
        "quiz_subject": quiz_subject,
        "study_topics": study_topics,
        "difficulty": difficulty,
        "difficulty_mode": difficulty_mode,
        "difficulty_hint": difficulty_hint,
        "question_count": question_count,
        "exam_date": exam_date,
        "topic_cards_topic": topic_cards_topic,
        "quiz_bank_topic": topic_focus or (user_input.splitlines()[0][:255] if user_input.splitlines() else "General"),
    })


@login_required
@require_POST
def record_quiz_attempt(request):
    try:
        payload = json.loads(request.body)
        session_id = int(payload.get("session_id"))
        score = int(payload.get("score"))
        total = int(payload.get("total"))
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return HttpResponseBadRequest("Invalid quiz score data.")
    session = get_object_or_404(StudySession, pk=session_id, task_type="quiz", user=request.user)
    if total < 1 or total > 20 or score < 0 or score > total:
        return HttpResponseBadRequest("Quiz score is outside the allowed range.")
    attempt = QuizAttempt.objects.create(
        study_session=session,
        user=request.user,
        topic=(session.metadata.get("topic") or session.metadata.get("topic_focus") or session.user_input or "Quiz")[:255],
        difficulty=session.metadata.get("difficulty", "medium"),
        score=score,
        total_questions=total,
    )
    next_difficulty, next_hint = recommended_quiz_difficulty(request.user)
    return JsonResponse({
        "saved": True,
        "next_difficulty": next_difficulty,
        "next_hint": next_hint,
        "score_percent": round(100 * attempt.score / attempt.total_questions),
    })


@login_required
@require_POST
def add_question_bank_item(request):
    try:
        payload = json.loads(request.body)
        question = payload.get("question") or {}
        subject = str(payload.get("subject", "General")).strip()[:120] or "General"
        topic = str(payload.get("topic", "General")).strip()[:255] or "General"
        difficulty = str(payload.get("difficulty", "medium")).strip()
        question_text = str(question.get("question", "")).strip()
        code = str(question.get("code", ""))
        code_language = str(question.get("code_language", ""))[:40]
        options = question.get("options")
        correct_answer = question.get("correct_answer")
        hint = str(question.get("hint", ""))
        explanation = str(question.get("explanation", ""))
        session_id = payload.get("session_id")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return HttpResponseBadRequest("Invalid question data.")

    if (
        not question_text or len(question_text) > 15000 or len(code) > 15000
        or not isinstance(options, dict)
        or any(not isinstance(options.get(letter), str) or not options[letter].strip() for letter in "ABCD")
        or correct_answer not in {"A", "B", "C", "D"}
        or difficulty not in DIFFICULTY_LEVELS
        or len(hint) > 5000 or len(explanation) > 5000
    ):
        return HttpResponseBadRequest("Question data is incomplete or too large.")

    source_session = None
    if session_id:
        try:
            session_id = int(session_id)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid source quiz.")
        source_session = get_object_or_404(StudySession, pk=session_id, user=request.user, task_type="quiz")

    existing = QuestionBankItem.objects.filter(
        user=request.user, subject=subject, topic=topic, question=question_text
    ).first()
    if existing:
        return JsonResponse({"saved": True, "already_saved": True, "id": existing.pk})

    item = QuestionBankItem.objects.create(
        user=request.user,
        source_session=source_session,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        question=question_text,
        code=code,
        code_language=code_language,
        options={letter: options[letter][:5000] for letter in "ABCD"},
        correct_answer=correct_answer,
        hint=hint,
        explanation=explanation,
    )
    return JsonResponse({"saved": True, "already_saved": False, "id": item.pk})


@login_required
@require_POST
def delete_question_bank_item(request, item_id):
    item = get_object_or_404(QuestionBankItem, pk=item_id, user=request.user)
    item.delete()
    return redirect("question_bank")


@login_required
@require_POST
def clear_activity(request):
    """Hide recent entries while preserving records used for dashboard totals."""
    cleared_attempts = QuizAttempt.objects.filter(
        user=request.user,
        history_cleared=False,
    ).update(history_cleared=True)
    cleared_sessions = StudySession.objects.filter(
        user=request.user,
        history_cleared=False,
    ).update(history_cleared=True)
    return JsonResponse({
        "cleared_sessions": cleared_sessions,
        "cleared_attempts": cleared_attempts,
    })


@login_required
@require_POST
def add_bookmark(request):
    try:
        payload = json.loads(request.body)
        title = str(payload.get("title", "")).strip()[:255]
        content = str(payload.get("content", "")).strip()
        kind = payload.get("kind", "note")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return HttpResponseBadRequest("Invalid bookmark data.")
    if not title or not content or len(content) > 50000 or kind not in {"note", "question", "flashcard"}:
        return HttpResponseBadRequest("Bookmark needs a title and content.")
    bookmark = Bookmark.objects.create(user=request.user, title=title, content=content, kind=kind)
    return JsonResponse({"saved": True, "id": bookmark.pk, "title": bookmark.title})


@login_required
@require_POST
def delete_bookmark(request, bookmark_id):
    bookmark = get_object_or_404(Bookmark, pk=bookmark_id, user=request.user)
    bookmark.delete()
    return JsonResponse({"deleted": True})


@login_required
@require_POST
def export_document(request, export_format):
    if export_format not in {"pdf", "docx"}:
        return HttpResponseBadRequest("Choose PDF or Word export.")
    try:
        payload = json.loads(request.body)
        title = str(payload.get("title", "Smart Study Companion Export"))[:120]
        content = str(payload.get("content", ""))
    except (json.JSONDecodeError, AttributeError, TypeError):
        return HttpResponseBadRequest("Invalid export content.")
    if not content.strip() or len(content) > 250000:
        return HttpResponseBadRequest("Export content is empty or too large.")
    if export_format == "pdf":
        data = make_pdf(content, title)
        content_type = "application/pdf"
        filename = "study-assistant-notes.pdf"
    else:
        data = make_docx(content, title)
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = "study-assistant-notes.docx"
    return FileResponse(
        BytesIO(data),
        as_attachment=True,
        filename=filename,
        content_type=content_type,
    )
