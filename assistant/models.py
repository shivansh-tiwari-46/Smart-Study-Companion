from django.conf import settings
from django.db import models


class StudySession(models.Model):
    TASK_CHOICES = [
        ("explain", "Explain Concept"),
        ("summarize", "Summarize Text"),
        ("quiz", "Generate Quiz"),
        ("flashcards", "Generate Flashcards"),
        ("study_plan", "Create Study Plan"),
        ("topic_cards", "Topic Cards"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_sessions", null=True, blank=True)
    user_input = models.TextField(blank=True, null=True)
    pdf_file = models.FileField(upload_to="pdfs/", blank=True, null=True)
    task_type = models.CharField(max_length=20, choices=TASK_CHOICES)
    ai_response = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    history_cleared = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class QuizAttempt(models.Model):
    study_session = models.ForeignKey(
        StudySession, on_delete=models.SET_NULL, null=True, blank=True, related_name="quiz_attempts"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts", null=True, blank=True)
    topic = models.CharField(max_length=255, blank=True)
    difficulty = models.CharField(max_length=12, default="medium")
    score = models.PositiveSmallIntegerField()
    total_questions = models.PositiveSmallIntegerField()
    history_cleared = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.score}/{self.total_questions} - {self.topic}"


class Bookmark(models.Model):
    KIND_CHOICES = [
        ("note", "Study Note"),
        ("question", "Quiz Question"),
        ("flashcard", "Flashcard"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks", null=True, blank=True)
    title = models.CharField(max_length=255)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="note")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class QuestionBankItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="question_bank_items")
    source_session = models.ForeignKey(
        StudySession, on_delete=models.SET_NULL, null=True, blank=True, related_name="saved_questions"
    )
    subject = models.CharField(max_length=120, default="General")
    topic = models.CharField(max_length=255, default="General")
    difficulty = models.CharField(max_length=12, default="medium")
    question = models.TextField()
    code = models.TextField(blank=True)
    code_language = models.CharField(max_length=40, blank=True)
    options = models.JSONField(default=dict)
    correct_answer = models.CharField(max_length=1)
    hint = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.topic}: {self.question[:70]}"
