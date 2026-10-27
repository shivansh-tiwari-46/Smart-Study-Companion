"use strict";

const QUIZ_OPTION_LETTERS = ["A", "B", "C", "D"];

/* Shared request and content helpers */
function getCsrfToken() {
    const cookie = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return cookie ? decodeURIComponent(cookie[1]) : "";
}

async function postJson(url, data) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify(data),
    });

    if (!response.ok) {
        throw new Error(await response.text());
    }

    return response.json();
}

function addRichText(element, value) {
    const text = String(value ?? "");

    if (window.marked && window.DOMPurify) {
        const renderedMarkdown = window.marked.parse(text);
        element.innerHTML = window.DOMPurify.sanitize(renderedMarkdown);
        return;
    }

    element.textContent = text;
}

/* Export the currently visible study material */
function getQuizExportContent(quizData) {
    return quizData.questions
        .map((question, index) => {
            const codeSection = question.code
                ? `Code (${question.code_language || "text"}):\n${question.code}`
                : "";
            const choices = QUIZ_OPTION_LETTERS.map(
                (letter) => `${letter}. ${question.options[letter]}`,
            ).join("\n");

            return [
                `Question ${index + 1}: ${question.question}`,
                codeSection,
                choices,
                `Answer: ${question.correct_answer}`,
                question.explanation || "",
            ]
                .filter(Boolean)
                .join("\n");
        })
        .join("\n\n");
}

function getTopicCardsExportContent(topicCardsData) {
    return topicCardsData.cards
        .map((card, index) => [
            `Card ${index + 1}: ${card.title}`,
            card.summary,
            `Details: ${card.details}`,
            `Example: ${card.example}`,
            `Takeaway: ${card.takeaway}`,
        ].join("\n"))
        .join("\n\n");
}

function getExportContent() {
    const notes = document.getElementById("ai-output");
    if (notes) {
        return notes.innerText;
    }

    const quizElement = document.getElementById("quiz-data");
    if (quizElement) {
        return getQuizExportContent(JSON.parse(quizElement.textContent));
    }

    const topicCardsElement = document.getElementById("topic-cards-data");
    if (topicCardsElement) {
        return getTopicCardsExportContent(JSON.parse(topicCardsElement.textContent));
    }

    const flashcardsElement = document.getElementById("flashcards-data");
    if (flashcardsElement) {
        const { cards } = JSON.parse(flashcardsElement.textContent);
        return cards
            .map((card, index) => `Card ${index + 1}\nQ: ${card.front}\nA: ${card.back}`)
            .join("\n\n");
    }

    const planElement = document.getElementById("plan-data");
    if (planElement) {
        const plan = JSON.parse(planElement.textContent);
        const schedule = plan.schedule
            .map((day) => `${day.date} — ${day.topic}\n${day.tasks}`)
            .join("\n\n");
        return `${plan.overview}\n\n${schedule}`;
    }

    return "";
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();

    // Let the browser start the download before releasing the temporary URL.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function initializeExports() {
    document.querySelectorAll(".export-button").forEach((button) => {
        button.addEventListener("click", async () => {
            const content = getExportContent();
            if (!content) {
                return;
            }

            button.disabled = true;

            try {
                const response = await fetch(`/export/${button.dataset.format}/`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCsrfToken(),
                    },
                    body: JSON.stringify({
                        title: "Smart Study Companion",
                        content,
                    }),
                });

                if (!response.ok) {
                    throw new Error("The document could not be created.");
                }

                const filename = button.dataset.format === "pdf"
                    ? "study-assistant-notes.pdf"
                    : "study-assistant-notes.docx";
                downloadBlob(await response.blob(), filename);
            } catch (error) {
                window.alert(error.message);
            } finally {
                button.disabled = false;
            }
        });
    });
}

/* Save and remove bookmarks */
function createBookmarkListItem(bookmark, content) {
    const item = document.createElement("li");
    item.className = "list-group-item p-3";
    item.dataset.bookmarkId = bookmark.id;

    const headingRow = document.createElement("div");
    headingRow.className = "d-flex justify-content-between gap-2";

    const title = document.createElement("strong");
    title.className = "history-text";
    title.textContent = bookmark.title;

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn btn-sm btn-outline-danger delete-bookmark";
    removeButton.setAttribute("aria-label", "Remove bookmark");
    removeButton.textContent = "×";
    headingRow.append(title, removeButton);

    const details = document.createElement("details");
    details.className = "mt-2";

    const summary = document.createElement("summary");
    summary.textContent = "View";

    const savedContent = document.createElement("div");
    savedContent.className = "bookmark-content small mt-2";
    savedContent.textContent = content;
    details.append(summary, savedContent);

    item.append(headingRow, details);
    return item;
}

async function saveBookmark(button, title, content, kind) {
    button.disabled = true;

    try {
        const bookmark = await postJson("/bookmarks/add/", {
            title,
            content,
            kind,
        });
        const list = document.getElementById("bookmark-list");

        document.getElementById("empty-bookmarks")?.remove();
        list.prepend(createBookmarkListItem(bookmark, content));
        button.textContent = "✓ Saved";
    } catch (error) {
        window.alert(`Could not save bookmark: ${error.message}`);
        button.disabled = false;
    }
}

function initializeBookmarkButtons() {
    document.querySelectorAll(".bookmark-button").forEach((button) => {
        button.addEventListener("click", () => {
            saveBookmark(
                button,
                button.dataset.title,
                getExportContent(),
                button.dataset.kind,
            );
        });
    });
}

function initializeActivityRemoval() {
    const clearButton = document.getElementById("clear-history-button");
    if (!clearButton) {
        return;
    }

    clearButton.addEventListener("click", async () => {
        const confirmed = window.confirm(
            "Clear recent study history and quiz progress from the recent lists? Your dashboard totals will remain.",
        );
        if (!confirmed) {
            return;
        }

        clearButton.disabled = true;
        try {
            await postJson("/activity/clear/", {});
            window.location.reload();
        } catch (error) {
            window.alert("Could not clear recent activities. Please try again.");
            clearButton.disabled = false;
        }
    });
}

function initializeBookmarkRemoval() {
    const list = document.getElementById("bookmark-list");
    if (!list) {
        return;
    }

    list.addEventListener("click", async (event) => {
        const button = event.target.closest(".delete-bookmark");
        if (!button) {
            return;
        }

        const item = button.closest("[data-bookmark-id]");
        if (!item) {
            return;
        }

        button.disabled = true;

        try {
            await postJson(`/bookmarks/${item.dataset.bookmarkId}/delete/`, {});
            item.remove();

            if (!list.children.length) {
                const emptyMessage = document.createElement("li");
                emptyMessage.id = "empty-bookmarks";
                emptyMessage.className = "list-group-item text-muted text-center";
                emptyMessage.textContent = "No bookmarks saved yet.";
                list.appendChild(emptyMessage);
            }
        } catch (error) {
            window.alert("Could not remove bookmark.");
            button.disabled = false;
        }
    });
}

/* Study tool settings and generated notes */
function initializeTaskSettings() {
    const taskSelector = document.getElementById("task_type");
    if (!taskSelector) {
        return;
    }

    function updateVisibleSettings() {
        document.querySelectorAll(".task-settings").forEach((group) => {
            const supportedTasks = group.dataset.for.split(" ");
            group.hidden = !supportedTasks.includes(taskSelector.value);
        });
    }

    taskSelector.addEventListener("change", updateVisibleSettings);
    updateVisibleSettings();
}

function initializeGeneratedNotes() {
    const output = document.getElementById("ai-output");
    if (!output) {
        return;
    }

    addRichText(output, output.textContent);

    const copyButton = document.getElementById("copy-button");
    copyButton?.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(output.innerText);
            copyButton.textContent = "✓ Copied!";
            window.setTimeout(() => {
                copyButton.textContent = "📋 Copy Output";
            }, 2000);
        } catch (error) {
            copyButton.textContent = "Copy failed";
        }
    });

    const downloadButton = document.getElementById("download-button");
    downloadButton?.addEventListener("click", () => {
        const notes = new Blob([output.innerText], {
            type: "text/plain;charset=utf-8",
        });
        downloadBlob(notes, "AI_Study_Notes.txt");
    });
}

/* Voice input and read-aloud controls use browser-provided speech APIs. */
function initializeVoiceInteraction() {
    const promptField = document.getElementById("user_input");
    const inputButton = document.getElementById("voice-input-button");
    const inputStatus = document.getElementById("voice-input-status");
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (promptField && inputButton && inputStatus) {
        const localHosts = ["localhost", "127.0.0.1", "[::1]", "::1"];
        const isSecurePage = window.isSecureContext || localHosts.includes(window.location.hostname);

        if (!isSecurePage) {
            inputButton.disabled = true;
            inputStatus.textContent = "Voice typing requires HTTPS or a local address such as http://localhost:8000.";
        } else if (!SpeechRecognition) {
            inputButton.disabled = true;
            inputStatus.textContent = "This browser does not support voice typing. Try an up-to-date desktop Chrome or Edge.";
        } else {
            const recognition = new SpeechRecognition();
            let startingText = "";
            let finalTranscript = "";
            let lastError = "";

            recognition.lang = navigator.language || "en-IN";
            recognition.continuous = false;
            recognition.interimResults = true;

            recognition.onstart = () => {
                lastError = "";
                inputButton.setAttribute("aria-pressed", "true");
                inputButton.textContent = "Listening…";
                inputStatus.textContent = "Speak now. Your prompt will not be submitted automatically.";
            };

            recognition.onresult = (event) => {
                finalTranscript = "";
                let interimTranscript = "";

                for (let index = 0; index < event.results.length; index += 1) {
                    const transcript = event.results[index][0].transcript;
                    if (event.results[index].isFinal) {
                        finalTranscript += transcript;
                    } else {
                        interimTranscript += transcript;
                    }
                }

                const separator = startingText.trim() ? "\n" : "";
                promptField.value = (startingText + separator + finalTranscript).trimEnd();
                inputStatus.textContent = interimTranscript
                    ? "Listening… " + interimTranscript
                    : "Listening…";
            };

            recognition.onerror = (event) => {
                const messages = {
                    "not-allowed": "Microphone access was blocked. Allow microphone access and try again.",
                    "service-not-allowed": "Speech recognition is unavailable. Check your browser settings and try again.",
                    "audio-capture": "No microphone was found. Connect a microphone and try again.",
                    "no-speech": "No speech was detected. Select the microphone to try again.",
                    "network": "The browser could not reach its speech recognition service. Check your connection and retry.",
                    "language-not-supported": "The browser does not support the selected speech language (" + recognition.lang + ").",
                };
                lastError = messages[event.error] || "Voice typing failed (" + (event.error || "unknown error") + "). Please try again.";
                inputStatus.textContent = lastError;
            };

            recognition.onend = () => {
                inputButton.setAttribute("aria-pressed", "false");
                inputButton.textContent = "🎙️ Speak your prompt";
                if (!lastError) {
                    inputStatus.textContent = finalTranscript.trim()
                        ? "Voice text added to your prompt. Review it before submitting."
                        : "No speech was added. Select the microphone to try again.";
                }
            };

            inputButton.addEventListener("click", () => {
                if (inputButton.getAttribute("aria-pressed") === "true") {
                    recognition.stop();
                    return;
                }

                startingText = promptField.value;
                finalTranscript = "";
                lastError = "";

                try {
                    recognition.start();
                } catch (error) {
                    const errorName = error && error.name ? error.name : "unknown error";
                    inputStatus.textContent = "Voice typing could not start (" + errorName + "). Check microphone access and try again.";
                }
            });
        }
    }

    const output = document.getElementById("ai-output");
    const readButton = document.getElementById("read-aloud-button");
    const stopButton = document.getElementById("stop-reading-button");
    const outputStatus = document.getElementById("voice-output-status");

    if (!output || !readButton || !stopButton || !outputStatus) {
        return;
    }

    if (!("speechSynthesis" in window) || !window.SpeechSynthesisUtterance) {
        readButton.disabled = true;
        stopButton.disabled = true;
        outputStatus.textContent = "Read aloud is not supported in this browser.";
        return;
    }

    const speechSynthesis = window.speechSynthesis;
    let isStoppingPlayback = false;
    const setPlaybackState = (isSpeaking) => {
        readButton.disabled = isSpeaking;
        stopButton.disabled = !isSpeaking;
        readButton.textContent = isSpeaking ? "Speaking…" : "🔊 Read aloud";
    };

    readButton.addEventListener("click", () => {
        const text = output.innerText.trim();
        if (!text) {
            outputStatus.textContent = "There is no generated text to read aloud.";
            return;
        }

        isStoppingPlayback = false;
        speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = navigator.language || "en-IN";
        utterance.onstart = () => {
            setPlaybackState(true);
            outputStatus.textContent = "Reading your study notes aloud.";
        };
        utterance.onend = () => {
            if (isStoppingPlayback) {
                isStoppingPlayback = false;
                return;
            }
            setPlaybackState(false);
            outputStatus.textContent = "Read aloud finished.";
        };
        utterance.onerror = () => {
            if (isStoppingPlayback) {
                isStoppingPlayback = false;
                return;
            }
            setPlaybackState(false);
            outputStatus.textContent = "Read aloud could not continue. Try again.";
        };

        speechSynthesis.speak(utterance);
    });

    stopButton.addEventListener("click", () => {
        isStoppingPlayback = true;
        speechSynthesis.cancel();
        setPlaybackState(false);
        outputStatus.textContent = "Read aloud stopped.";
    });
}
/* Interactive multiple-choice quiz */
function initializeQuiz() {
    const dataElement = document.getElementById("quiz-data");
    const container = document.getElementById("quiz-container");
    if (!dataElement || !container) {
        return;
    }

    const quizData = JSON.parse(dataElement.textContent);
    const allQuestions = Array.isArray(quizData.questions) ? quizData.questions : [];

    if (!allQuestions.length) {
        container.textContent = "No quiz questions are available.";
        return;
    }

    let questions = allQuestions;
    let questionIndex = 0;
    let score = 0;
    let missedQuestions = [];
    const savedQuestions = new WeakSet();

    function startQuiz(questionSet) {
        questions = questionSet.slice();
        questionIndex = 0;
        score = 0;
        missedQuestions = [];
        renderQuestion();
    }

    function renderScore() {
        container.replaceChildren();

        const heading = document.createElement("h4");
        heading.textContent = `Quiz complete: ${score} out of ${questions.length}`;

        const percentage = Math.round((score / questions.length) * 100);
        const scoreText = document.createElement("p");
        scoreText.className = "text-muted";
        scoreText.textContent = `Score: ${percentage}%`;
        container.append(heading, scoreText);

        postJson("/quiz-attempt/", {
            session_id: container.dataset.sessionId,
            score,
            total: questions.length,
        }).then((attempt) => {
            const message = document.createElement("div");
            message.className = "alert alert-primary adaptive-result mt-3 mb-0";
            message.setAttribute("role", "status");
            message.textContent = `Next adaptive quiz: ${attempt.next_difficulty}. ${attempt.next_hint}`;
            container.appendChild(message);
        }).catch(() => {
            const message = document.createElement("small");
            message.className = "text-danger d-block";
            message.textContent = "This score could not be added to your progress history.";
            container.appendChild(message);
        });

        if (missedQuestions.length) {
            const retryMissedButton = document.createElement("button");
            retryMissedButton.type = "button";
            retryMissedButton.className = "btn btn-warning me-2";
            retryMissedButton.textContent =
                `Review ${missedQuestions.length} missed question${missedQuestions.length === 1 ? "" : "s"}`;
            retryMissedButton.addEventListener("click", () => {
                startQuiz(missedQuestions);
            });
            container.appendChild(retryMissedButton);
        }

        const retryAllButton = document.createElement("button");
        retryAllButton.type = "button";
        retryAllButton.className = "btn btn-outline-primary";
        retryAllButton.textContent = "Retry full quiz";
        retryAllButton.addEventListener("click", () => startQuiz(allQuestions));
        container.appendChild(retryAllButton);
    }

    function renderQuestion() {
        const question = questions[questionIndex];
        container.replaceChildren();

        const progress = document.createElement("p");
        progress.className = "text-muted mb-2";
        progress.textContent = `Question ${questionIndex + 1} of ${questions.length}`;
        container.appendChild(progress);

        const prompt = document.createElement("div");
        prompt.className = "rich-text mb-3";
        addRichText(prompt, question.question);
        container.appendChild(prompt);

        const codeText = String(question.code || "");
        if (codeText.trim()) {
            const codePanel = document.createElement("div");
            codePanel.className = "code-block mb-4";

            if (question.code_language) {
                const languageLabel = document.createElement("div");
                languageLabel.className = "code-language";
                languageLabel.textContent = question.code_language;
                codePanel.appendChild(languageLabel);
            }

            const preformatted = document.createElement("pre");
            const code = document.createElement("code");
            const languageClass = String(question.code_language || "")
                .toLowerCase()
                .replace(/[^a-z0-9_-]/g, "");

            if (languageClass) {
                code.classList.add(`language-${languageClass}`);
            }

            // textContent keeps code literal and preserves its indentation.
            code.textContent = codeText;
            preformatted.appendChild(code);
            codePanel.appendChild(preformatted);
            container.appendChild(codePanel);
        }

        const saveQuestionButton = document.createElement("button");
        saveQuestionButton.type = "button";
        saveQuestionButton.className = "btn btn-sm btn-outline-primary mb-3 save-question-button";
        saveQuestionButton.textContent = savedQuestions.has(question) ? "Saved to Question Bank" : "☆ Save to Question Bank";
        saveQuestionButton.disabled = savedQuestions.has(question);
        saveQuestionButton.addEventListener("click", async () => {
            saveQuestionButton.disabled = true;
            saveQuestionButton.textContent = "Saving question…";
            try {
                const saved = await postJson("/question-bank/add/", {
                    session_id: container.dataset.sessionId,
                    subject: container.dataset.subject || "General",
                    topic: container.dataset.topic || "General",
                    difficulty: container.dataset.difficulty || "medium",
                    question,
                });
                savedQuestions.add(question);
                saveQuestionButton.textContent = saved.already_saved ? "Already in Question Bank" : "Saved to Question Bank";
                saveQuestionButton.classList.replace("btn-outline-primary", "btn-success");
            } catch (_error) {
                saveQuestionButton.disabled = false;
                saveQuestionButton.textContent = "Could not save — try again";
            }
        });
        container.appendChild(saveQuestionButton);

        const hintButton = document.createElement("button");
        hintButton.type = "button";
        hintButton.className = "btn btn-sm btn-outline-info mb-3";
        hintButton.textContent = "Show hint";

        const hint = document.createElement("div");
        hint.className = "alert alert-info py-2";
        hint.hidden = true;
        addRichText(hint, question.hint || "Think about the key idea in this question.");
        hintButton.addEventListener("click", () => {
            hint.hidden = !hint.hidden;
            hintButton.textContent = hint.hidden ? "Show hint" : "Hide hint";
        });
        container.append(hintButton, hint);

        const choices = document.createElement("div");
        choices.className = "d-grid gap-2";

        const feedback = document.createElement("div");
        feedback.setAttribute("role", "status");

        const nextButton = document.createElement("button");
        nextButton.type = "button";
        nextButton.className = "btn btn-primary mt-3 d-none";
        nextButton.textContent = questionIndex === questions.length - 1
            ? "See score"
            : "Next question";
        nextButton.addEventListener("click", () => {
            questionIndex += 1;
            if (questionIndex < questions.length) {
                renderQuestion();
            } else {
                renderScore();
            }
        });

        let choiceCount = 0;
        QUIZ_OPTION_LETTERS.forEach((letter) => {
            if (!question.options || question.options[letter] === undefined) {
                return;
            }

            choiceCount += 1;
            const choice = document.createElement("button");
            choice.type = "button";
            choice.className = "btn btn-outline-secondary d-flex align-items-start quiz-option";
            choice.dataset.answer = letter;

            const choiceLetter = document.createElement("span");
            choiceLetter.className = "quiz-option-letter";
            choiceLetter.textContent = `${letter}.`;

            const choiceText = document.createElement("span");
            choiceText.className = "rich-text flex-grow-1";
            addRichText(choiceText, question.options[letter]);
            choice.append(choiceLetter, choiceText);

            choice.addEventListener("click", () => {
                const isCorrect = letter === question.correct_answer;
                if (isCorrect) {
                    score += 1;
                } else {
                    missedQuestions.push(question);
                }

                choices.querySelectorAll("button").forEach((option) => {
                    option.disabled = true;
                    if (option.dataset.answer === question.correct_answer) {
                        option.classList.replace("btn-outline-secondary", "btn-success");
                    }
                });

                if (!isCorrect) {
                    choice.classList.replace("btn-outline-secondary", "btn-danger");
                }

                feedback.className = isCorrect
                    ? "alert alert-success mt-3"
                    : "alert alert-warning mt-3";

                const resultLabel = document.createElement("strong");
                resultLabel.textContent = isCorrect ? "Correct! " : "Not quite. ";

                const explanation = document.createElement("div");
                explanation.className = "rich-text d-inline-block";
                addRichText(
                    explanation,
                    question.explanation || `The correct answer is ${question.correct_answer}.`,
                );
                feedback.append(resultLabel, explanation);
                nextButton.classList.remove("d-none");
            });

            choices.appendChild(choice);
        });

        if (!choiceCount) {
            const message = document.createElement("p");
            message.className = "text-danger";
            message.textContent = "The answer choices for this question are unavailable.";
            choices.appendChild(message);
        }

        const bookmarkButton = document.createElement("button");
        bookmarkButton.type = "button";
        bookmarkButton.className = "btn btn-sm btn-outline-secondary mt-3 ms-2";
        bookmarkButton.textContent = "☆ Bookmark question";
        bookmarkButton.addEventListener("click", () => {
            const choiceText = QUIZ_OPTION_LETTERS
                .map((letter) => `${letter}. ${question.options?.[letter] || ""}`)
                .join("\n");
            const content = [
                question.question,
                codeText,
                choiceText,
                `Answer: ${question.correct_answer}`,
                question.explanation || "",
            ]
                .filter(Boolean)
                .join("\n");
            const title = String(question.question || "Quiz question").slice(0, 80);
            saveBookmark(bookmarkButton, title, content, "question");
        });

        container.append(choices, feedback, nextButton, bookmarkButton);
    }

    startQuiz(allQuestions);
}

/* Colorful topic concept cards */
function initializeTopicCards() {
    const dataElement = document.getElementById("topic-cards-data");
    const container = document.getElementById("topic-cards-container");
    if (!dataElement || !container) {
        return;
    }

    const topicCardsData = JSON.parse(dataElement.textContent);
    const cards = Array.isArray(topicCardsData.cards) ? topicCardsData.cards : [];
    const visuals = {
        science: "🔬",
        technology: "💻",
        math: "📐",
        history: "🏛️",
        language: "💬",
        business: "📊",
        general: "💡",
    };
    const colors = [
        ["#fff0f3", "#e85d75"],
        ["#eef4ff", "#4d7cfe"],
        ["#edfff5", "#22a06b"],
        ["#fff8e8", "#d99000"],
        ["#f5efff", "#8957e5"],
    ];

    cards.forEach((card, index) => {
        const [tint, accent] = colors[index % colors.length];
        const article = document.createElement("article");
        article.className = "topic-card";
        article.style.setProperty("--card-tint", tint);
        article.style.setProperty("--card-accent", accent);

        const watermark = document.createElement("div");
        watermark.className = "topic-card-watermark";
        watermark.setAttribute("aria-hidden", "true");
        watermark.textContent = visuals[card.category] || visuals.general;

        const content = document.createElement("div");
        content.className = "topic-card-content";

        const badge = document.createElement("span");
        badge.className = "topic-card-badge";
        badge.textContent = card.category || "general";

        const title = document.createElement("h3");
        title.textContent = card.title;

        const summary = document.createElement("p");
        summary.className = "fw-semibold";
        addRichText(summary, card.summary);

        const detailsLabel = document.createElement("div");
        detailsLabel.className = "topic-card-label";
        detailsLabel.textContent = "Key details";

        const details = document.createElement("p");
        addRichText(details, card.details);

        const exampleLabel = document.createElement("div");
        exampleLabel.className = "topic-card-label";
        exampleLabel.textContent = "Example";

        const example = document.createElement("p");
        addRichText(example, card.example);

        const takeaway = document.createElement("div");
        takeaway.className = "topic-card-takeaway";
        addRichText(takeaway, `Remember: ${card.takeaway}`);

        content.append(badge, title, summary, detailsLabel, details, exampleLabel, example, takeaway);
        article.append(watermark, content);
        container.appendChild(article);
    });

    if (!cards.length) {
        container.textContent = "No topic cards are available.";
    }
}

/* Interactive flashcards */
function initializeFlashcards() {
    const dataElement = document.getElementById("flashcards-data");
    const container = document.getElementById("flashcard-container");
    if (!dataElement || !container) {
        return;
    }

    const flashcardsData = JSON.parse(dataElement.textContent);
    const cards = Array.isArray(flashcardsData.cards) ? flashcardsData.cards : [];
    let cardIndex = 0;
    let answerIsVisible = false;

    function renderCard() {
        container.replaceChildren();

        if (cardIndex >= cards.length) {
            const completionMessage = document.createElement("h4");
            completionMessage.className = "mb-3";
            completionMessage.textContent = `You reviewed ${cards.length} flashcards.`;

            const restartButton = document.createElement("button");
            restartButton.type = "button";
            restartButton.className = "btn btn-primary";
            restartButton.textContent = "Study again";
            restartButton.addEventListener("click", () => {
                cardIndex = 0;
                answerIsVisible = false;
                renderCard();
            });

            container.append(completionMessage, restartButton);
            return;
        }

        const card = cards[cardIndex];
        const progress = document.createElement("p");
        progress.className = "text-muted";
        progress.textContent = `Card ${cardIndex + 1} of ${cards.length}`;

        const face = document.createElement("div");
        face.className = "flashcard rich-text mb-3";
        addRichText(face, answerIsVisible ? card.back : card.front);

        const revealButton = document.createElement("button");
        revealButton.type = "button";
        revealButton.className = "btn btn-primary me-2";
        revealButton.textContent = answerIsVisible ? "Show question" : "Reveal answer";
        revealButton.addEventListener("click", () => {
            answerIsVisible = !answerIsVisible;
            renderCard();
        });

        const nextButton = document.createElement("button");
        nextButton.type = "button";
        nextButton.className = "btn btn-outline-primary me-2";
        nextButton.textContent = "Next card";
        nextButton.addEventListener("click", () => {
            cardIndex += 1;
            answerIsVisible = false;
            renderCard();
        });

        const bookmarkButton = document.createElement("button");
        bookmarkButton.type = "button";
        bookmarkButton.className = "btn btn-outline-secondary";
        bookmarkButton.textContent = "☆ Bookmark card";
        bookmarkButton.addEventListener("click", () => {
            const content = `Q: ${card.front}\nA: ${card.back}`;
            const title = String(card.front || "Flashcard").slice(0, 80);
            saveBookmark(bookmarkButton, title, content, "flashcard");
        });

        container.append(progress, face, revealButton, nextButton, bookmarkButton);
    }

    if (cards.length) {
        renderCard();
    } else {
        container.textContent = "No flashcards are available.";
    }
}

function initializeQuestionBankRemoval() {
    document.querySelectorAll(".delete-question-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm("Remove this question from your bank?")) {
                event.preventDefault();
            }
        });
    });
}

/* Start each page feature after its HTML is ready. */
document.addEventListener("DOMContentLoaded", () => {
    initializeTaskSettings();
    initializeGeneratedNotes();
    initializeVoiceInteraction();
    initializeExports();
    initializeBookmarkButtons();
    initializeBookmarkRemoval();
    initializeActivityRemoval();
    initializeQuiz();
    initializeTopicCards();
    initializeFlashcards();
    initializeQuestionBankRemoval();
});