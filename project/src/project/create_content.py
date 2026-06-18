import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from config import settings
from models import NotificationRequest, NotificationType

logger = logging.getLogger("notification_module.create_content")

# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------
TEMPLATES_DIR = Path(settings.TEMPLATES_DIR)

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ---------------------------------------------------------------------------
# Subject lines (defined in Python for simplicity; could move to templates)
# ---------------------------------------------------------------------------
_SUBJECTS: dict[str, str] = {
    NotificationType.NEW_ASSIGNMENT: "New programming assignment: {{ assignment.title }}",
    NotificationType.DEADLINE_STUDENT: "Reminder: deadline for '{{ assignment.title }}' is approaching",
    NotificationType.DEADLINE_TEACHER: "Deadline summary: {{ assignment.title }}",
    NotificationType.REVIEW_RESULT: "Assignment '{{ assignment.title }}' has been graded",
}


# ---------------------------------------------------------------------------
# ContentBuilder
# ---------------------------------------------------------------------------

# === ContentBuilder ===
# Builds all content variants needed to send a notification.
class ContentBuilder:
    """
    Falls back to inline defaults when template files are missing so the
    prototype runs correctly in a clean environment without pre-created
    template files (templates will still be rendered from the defaults
    embedded below, and written to disk on first run).
    """

    def __init__(self) -> None:
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_default_templates()


    # === Public API ===
    # Render all content for a given NotificationRequest
    # Returns a dict with keys: subject, body_html, body_text, vk_text
    def build(self, request: NotificationRequest) -> dict[str, str]:
        ctx = self._build_context(request)
        ntype = request.notification_type

        subject = self._render_string(_SUBJECTS.get(ntype, "Notification"), ctx)
        body_html = self._render_template(f"{ntype}_email.html", ctx)
        body_text = self._render_template(f"{ntype}_email.txt", ctx)
        vk_text = self._render_template(f"{ntype}_vk.txt", ctx)

        return {
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "vk_text": vk_text,
        }

    
    # === Internal helpers ===
    # Flatten the request into a flat template context dictionary.
    def _build_context(self, request: NotificationRequest) -> dict:
        ctx: dict = {
            "assignment": request.assignment,
            "recipient_id": request.recipient_id,
        }
        if request.student:
            ctx["student"] = request.student
        if request.teacher:
            ctx["teacher"] = request.teacher
        if request.submission_summary:
            ctx["submission"] = request.submission_summary
        return ctx

    def _render_template(self, template_name: str, context: dict) -> str:
        try:
            tmpl = _jinja_env.get_template(template_name)
            return tmpl.render(**context)
        except TemplateNotFound:
            logger.warning("Template '%s' not found; using fallback.", template_name)
            return self._fallback(template_name, context)
        except Exception as exc:
            logger.error("Template render error for '%s': %s", template_name, exc)
            return f"Notification: {context.get('assignment', {})}"

    def _render_string(self, template_str: str, context: dict) -> str:
        try:
            tmpl = _jinja_env.from_string(template_str)
            return tmpl.render(**context)
        except Exception as exc:
            logger.error("Subject render error: %s", exc)
            return "Notification"

    # Minimal inline fallback used when a template file is absent.
    def _fallback(self, template_name: str, ctx: dict) -> str:
        assignment = ctx.get("assignment")
        student = ctx.get("student")
        teacher = ctx.get("teacher")

        if "new_assignment" in template_name:
            name = student.full_name if student else "Student"
            return (
                f"Уважаемый(ая) {name},\n\n"
                f"A new assignment '{assignment.title}' has been published in topic '{assignment.topic}'.\n"
                f"Deadline: {assignment.deadline or 'not specified'}.\n\n"
                "Humanitarian University"
            )
        if "deadline_student" in template_name:
            name = student.full_name if student else "Student"
            return (
                f"Уважаемый(ая) {name},\n\n"
                f"This is a reminder that the deadline for '{assignment.title}' is approaching.\n"
                f"Deadline: {assignment.deadline}.\n\n"
                "Please submit your work before the deadline.\n\n"
                "Humanitarian University"
            )
        if "deadline_teacher" in template_name:
            name = teacher.full_name if teacher else "Instructor"
            submission = ctx.get("submission")
            submitted = ", ".join(submission.submitted) if submission else "-"
            not_submitted = ", ".join(submission.not_submitted) if submission else "-"
            return (
                f"Уважаемый(ая) {name},\n\n"
                f"Submission status for '{assignment.title}' (deadline: {assignment.deadline}):\n\n"
                f"Submitted ({len(submission.submitted) if submission else 0}): {submitted}\n"
                f"Not submitted ({len(submission.not_submitted) if submission else 0}): {not_submitted}\n\n"
                "Humanitarian University"
            )
        if "review_result" in template_name:
            name = student.full_name if student else "Student"
            grade = f"{assignment.grade}/{assignment.max_grade}" if assignment.grade is not None else "N/A"
            return (
                f"Уважаемый(ая) {name},\n\n"
                f"Your assignment '{assignment.title}' has been reviewed.\n"
                f"Grade: {grade}\n"
                f"Feedback: {assignment.feedback or 'No feedback provided.'}\n\n"
                "Humanitarian University"
            )
        return "Notification from Humanitarian University."


    # === Default template files ===
    # Write default Jinja2 template files if they do not exist.
    def _ensure_default_templates(self) -> None:
        defaults = _default_templates()
        for filename, content in defaults.items():
            path = TEMPLATES_DIR / filename
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                logger.debug("Created default template: %s", path)


# ---------------------------------------------------------------------------
# Default template content
# ---------------------------------------------------------------------------

# Returns a mapping of template filename -> content.
# These are written to the templates/ directory on first startup.
def _default_templates() -> dict[str, str]:

    base_html = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; color: #222; background: #f9f9f9; }
  .container { max-width: 600px; margin: 32px auto; background: #fff;
               border-radius: 8px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .header { background: #1a237e; color: #fff; padding: 16px 24px; border-radius: 6px 6px 0 0; }
  .footer { margin-top: 32px; font-size: 12px; color: #888; text-align: center; }
  .badge { display: inline-block; background: #e8f5e9; color: #2e7d32;
           padding: 4px 10px; border-radius: 4px; font-size: 13px; }
  .grade-box { font-size: 28px; font-weight: bold; color: #1a237e; }
  table { border-collapse: collapse; width: 100%; margin-top: 16px; }
  td, th { padding: 8px 12px; border: 1px solid #e0e0e0; text-align: left; }
  th { background: #f5f5f5; }
</style>
</head>
<body>
<div class="container">
"""

    footer_html = """\
<div class="footer">
  АНО ВО &quot;Гуманитарный Университет&quot; &mdash; Система автоматической рассылки<br>
  Это сообщение было сгенерировано автоматически. Пожалуйста, не отвечайте.
</div>
</div></body></html>
"""

    templates = {}

    # ------------------------------------------------------------------
    # new_assignment
    # ------------------------------------------------------------------
    templates["new_assignment_email.html"] = (
        base_html
        + """\
<div class="header"><h2>Опубликовано новое задание</h2></div>
<p>Уважаемый(ая) <strong>{{ student.full_name }}</strong>,</p>
<p>Для вашей <strong>{{ student.group }}</strong> группы опубликовано новое задание по программированию.</p>
<table>
  <tr><th>Задание</th><td>{{ assignment.title }}</td></tr>
  <tr><th>Тема</th><td>{{ assignment.topic }}</td></tr>
  {% if assignment.deadline %}
  <tr><th>Срок сдачи</th><td>{{ assignment.deadline }}</td></tr>
  {% endif %}
</table>
<p>Для просмотра полной информации о задании, пожалуйста, войдите в систему.</p>
"""
        + footer_html
    )

    templates["new_assignment_email.txt"] = """\
Уважаемый(ая) {{ student.full_name }},

Для вашей {{ student.group }} группы опубликовано новое задание по программированию.

Задание : {{ assignment.title }}
Тема : {{ assignment.topic }}
{% if assignment.deadline %}Срок сдачи : {{ assignment.deadline }}{% endif %}

Для просмотра полной информации о задании, пожалуйста, войдите в систему.

АНО ВО \"Гуманитарный университет\" -- Система автоматической рассылки
"""

    templates["new_assignment_vk.txt"] = """\
Уважаемый(ая) {{ student.full_name }}, опубликовано новое задание по программированию.
Задание: {{ assignment.title }}
Тема: {{ assignment.topic }}
{% if assignment.deadline %}Срок сдачи: {{ assignment.deadline }}{% endif %}

Для просмотра полной информации о задании, пожалуйста, войдите в систему.
"""

    # ------------------------------------------------------------------ 
    # deadline_student
    # ------------------------------------------------------------------
    templates["deadline_student_email.html"] = (
        base_html
        + """\
<div class="header"><h2>Напоминание о дедлайне</h2></div>
<p>Уважаемый(ая) <strong>{{ student.full_name }}</strong>,</p>
<p>Это автоматическое напоминание о приближении крайнего срока сдачи вашего задания.</p>
<table>
  <tr><th>Задание</th><td>{{ assignment.title }}</td></tr>
  <tr><th>Тема</th><td>{{ assignment.topic }}</td></tr>
  <tr><th>Срок сдачи</th><td><strong>{{ assignment.deadline }}</strong></td></tr>
</table>
<p>Если вы уже сдали задание, пожалуйста, проигнорируйте это сообщение.</p>
"""
        + footer_html
    )

    templates["deadline_student_email.txt"] = """\
Уважаемый(ая) {{ student.full_name }},

Это автоматическое напоминание о приближении крайнего срока сдачи вашего задания.

Задание:    {{ assignment.title }}
Тема:       {{ assignment.topic }}
Срок сдачи: {{ assignment.deadline }}

Если вы уже сдали задание, пожалуйста, проигнорируйте это сообщение.

АНО ВО \"Гуманитарный университет\" -- Система автоматической рассылки
"""

    templates["deadline_student_vk.txt"] = """\
Уважаемый(ая), {{ student.full_name }}, напоминаем! Срок сдачи задания "{{ assignment.title }}" - {{ assignment.deadline }}.
Сдайте свою работу вовремя.
"""

    # ------------------------------------------------------------------
    # deadline_teacher
    # ------------------------------------------------------------------
    templates["deadline_teacher_email.html"] = (
        base_html
        + """\
<div class="header"><h2>Сводка по заданию</h2></div>
<p>Уважаемый(ая) <strong>{{ teacher.full_name }}</strong>,</p>
<p>Ниже приведена сводка по итогам задания, срок выполнения которого истек.</p>
<table>
  <tr><th>Задание</th><td>{{ assignment.title }}</td></tr>
  <tr><th>Тема</th><td>{{ assignment.topic }}</td></tr>
  <tr><th>Срок сдачи</th><td>{{ assignment.deadline }}</td></tr>
</table>

{% if submission %}
<h3>Сдали&#58; ({{ submission.submitted | length }})</h3>
{% if submission.submitted %}
<ul>{% for s in submission.submitted %}<li>{{ s }}</li>{% endfor %}</ul>
{% else %}<p>Никто.</p>{% endif %}

<h3>Не сдали&#58; ({{ submission.not_submitted | length }})</h3>
{% if submission.not_submitted %}
<ul>{% for s in submission.not_submitted %}<li>{{ s }}</li>{% endfor %}</ul>
{% else %}<p>Все студенты сдали.</p>{% endif %}
{% endif %}
"""
        + footer_html
    )

    templates["deadline_teacher_email.txt"] = """\
Уважаемый(ая) {{ teacher.full_name }},

Статус по заданию "{{ assignment.title }}" (Срок сдачи: {{ assignment.deadline }}):

Сдали ({{ submission.submitted | length }}):
{% for s in submission.submitted %}  - {{ s }}
{% else %}  никто
{% endfor %}
Не сдали ({{ submission.not_submitted | length }}):
{% for s in submission.not_submitted %}  - {{ s }}
{% else %}  все сдали.
{% endfor %}

АНО ВО \"Гуманитарный университет\" -- Система автоматической рассылки
"""

    templates["deadline_teacher_vk.txt"] = """\
Уважаемый(ая) {{ teacher.full_name }}, сводка по итогам задания "{{ assignment.title }}":
Сдали: {{ submission.submitted | join(", ") or "никто" }}
Не сдали: {{ submission.not_submitted | join(", ") or "все сдали" }}
"""

    # ------------------------------------------------------------------
    # review_result
    # ------------------------------------------------------------------
    templates["review_result_email.html"] = (
        base_html
        + """\
<div class="header"><h2>Работа оценена</h2></div>
<p>Уважаемый(ая) <strong>{{ student.full_name }}</strong>,</p>
<p>Ваш преподаватель проверил вашу работу.</p>
<table>
  <tr><th>Задание</th><td>{{ assignment.title }}</td></tr>
  <tr><th>Тема</th><td>{{ assignment.topic }}</td></tr>
  {% if assignment.grade is not none %}
  <tr><th>Оценка</th>
      <td><span class="grade-box">{{ assignment.grade }}{% if assignment.max_grade %} / {{ assignment.max_grade }}{% endif %}</span></td>
  </tr>
  {% endif %}
  {% if assignment.feedback %}
  <tr><th>Комментарий</th><td>{{ assignment.feedback }}</td></tr>
  {% endif %}
</table>
"""
        + footer_html
    )

    templates["review_result_email.txt"] = """\
Уважаемый(ая) {{ student.full_name }},

Ваш преподаватель проверил вашу работу.

Задание     : {{ assignment.title }}
тема        : {{ assignment.topic }}
{% if assignment.grade is not none %}Оценка     : {{ assignment.grade }}{% if assignment.max_grade %} / {{ assignment.max_grade }}{% endif %}{% endif %}
{% if assignment.feedback %}Комментарий : {{ assignment.feedback }}{% endif %}

АНО ВО \"Гуманитарный университет\" -- Система автоматической рассылки
"""

    templates["review_result_vk.txt"] = """\
Уважаемый(ая) {{ student.full_name }}, ваша работа "{{ assignment.title }}" была оценена.
{% if assignment.grade is not none %}Оценка: {{ assignment.grade }}{% if assignment.max_grade %}/{{ assignment.max_grade }}{% endif %}{% endif %}
{% if assignment.feedback %}Комментарий: {{ assignment.feedback }}{% endif %}
"""

    return templates
