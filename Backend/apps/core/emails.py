"""Plain-text emails rendered from templates without HTML escaping."""
from django.conf import settings
from django.core.mail import send_mail
from django.template import Context
from django.template.loader import get_template


def render_plain_text(template_name, context):
    template = get_template(template_name).template
    return template.render(Context(context, autoescape=False))


def send_email(user, subject, template_name, context=None):
    """Email `user` the rendered template; users without an address are skipped. Returns whether sent."""
    if not user.email:
        return False
    body = render_plain_text(template_name, {
        'user': user, 'frontend_url': settings.FRONTEND_URL.rstrip('/'), **(context or {}),
    })
    send_mail(f'[Shipyard] {subject}', body, None, [user.email])
    return True
