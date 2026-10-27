from django.urls import path
from . import views

urlpatterns = [
    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("", views.index, name="index"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("question-bank/", views.question_bank, name="question_bank"),
    path("question-bank/add/", views.add_question_bank_item, name="add_question_bank_item"),
    path("question-bank/<int:item_id>/delete/", views.delete_question_bank_item, name="delete_question_bank_item"),
    path("quiz-attempt/", views.record_quiz_attempt, name="record_quiz_attempt"),
    path("activity/clear/", views.clear_activity, name="clear_activity"),
    path("bookmarks/add/", views.add_bookmark, name="add_bookmark"),
    path("bookmarks/<int:bookmark_id>/delete/", views.delete_bookmark, name="delete_bookmark"),
    path("export/<str:export_format>/", views.export_document, name="export_document"),
]
