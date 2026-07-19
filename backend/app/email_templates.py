"""Branded ORTU Fitness email bodies.

Every template returns (plain_text, html) so messages read well in any
client; the HTML uses only inline styles and table layout for broad
email-client compatibility.
"""
from __future__ import annotations

from html import escape

_INK = "#071512"
_LIME = "#ccf34b"
_CREAM = "#f4f2eb"
_BODY = "#39453f"
_MUTED = "#78827d"


def branded(
    title: str,
    paragraphs: list[str],
    *,
    code: str | None = None,
    cta: tuple[str, str] | None = None,
    footer_note: str = "",
) -> tuple[str, str]:
    text_parts = list(paragraphs)
    if code:
        text_parts.append(f"Your code: {code}")
    if cta:
        label, url = cta
        text_parts.append(f"{label}: {url}")
    if footer_note:
        text_parts.append(footer_note)
    text = "\n\n".join(text_parts) + "\n\nORTU Fitness — Stronger together. Healthier for life."

    body_html = "".join(
        f'<p style="margin:0 0 14px;color:{_BODY};font-size:14px;line-height:1.65">{escape(p)}</p>'
        for p in paragraphs
    )
    if code:
        body_html += (
            f'<div style="background:{_CREAM};border:1px solid #dce5df;padding:18px;text-align:center;'
            f'font-size:30px;letter-spacing:8px;font-weight:bold;color:{_INK};margin:6px 0 14px">{escape(code)}</div>'
        )
    if cta:
        label, url = cta
        body_html += (
            f'<a href="{escape(url, quote=True)}" style="display:inline-block;background:{_LIME};color:{_INK};'
            f'font-weight:bold;font-size:14px;padding:14px 26px;text-decoration:none;margin-top:6px">{escape(label)} &#8599;</a>'
        )
    footer_html = f"ORTU Fitness &middot; Stronger together. Healthier for life."
    if footer_note:
        footer_html += f"<br>{escape(footer_note)}"

    html = f"""\
<div style="background:{_CREAM};padding:26px 12px;font-family:Arial,Helvetica,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;border-collapse:collapse">
    <tr>
      <td style="background:{_INK};padding:20px 28px">
        <span style="display:inline-block;border:2px solid {_LIME};border-radius:50%;width:30px;height:30px;line-height:30px;text-align:center;color:{_LIME};font-weight:bold;font-size:16px">O</span>
        <span style="color:#ffffff;font-size:17px;font-weight:800;letter-spacing:1px;margin-left:10px;vertical-align:middle">ORTU <span style="color:{_LIME}">FITNESS</span></span>
      </td>
    </tr>
    <tr>
      <td style="background:#ffffff;padding:30px 28px">
        <h1 style="margin:0 0 16px;font-size:22px;line-height:1.25;color:{_INK}">{escape(title)}</h1>
        {body_html}
      </td>
    </tr>
    <tr>
      <td style="padding:16px 28px;color:{_MUTED};font-size:11px;line-height:1.6">{footer_html}</td>
    </tr>
  </table>
</div>
"""
    return text, html


def signup_received(first_name: str) -> tuple[str, str, str]:
    subject = "We received your ORTU Fitness member record request"
    text, html = branded(
        "Your request is with the club",
        [
            f"Hi {first_name},",
            "Thanks for your interest in joining ORTU Fitness — your member record request has been received and is with the club for review.",
            "You will get another email as soon as the club accepts your sign-up. After that you can log in with your email address and password, choose a membership plan and book classes.",
        ],
        footer_note="You are receiving this because a member record request was made with this email address.",
    )
    return subject, text, html


def signup_approved(first_name: str, site_url: str) -> tuple[str, str, str]:
    subject = "Your ORTU Fitness membership has been accepted"
    text, html = branded(
        "Great news — you're in!",
        [
            f"Hi {first_name},",
            "The club has accepted your member record request.",
            "Log in with your email address and password, choose the membership plan that suits you, and start booking classes. See you in the studio!",
        ],
        cta=("Log in and choose your plan", site_url),
    )
    return subject, text, html


def signup_declined(first_name: str) -> tuple[str, str, str]:
    subject = "About your ORTU Fitness member record request"
    text, html = branded(
        "About your request",
        [
            f"Hi {first_name},",
            "Thank you for your interest in ORTU Fitness. Unfortunately the club has not been able to accept your member record request at this time.",
            "Please contact the studio if you would like to discuss it.",
        ],
    )
    return subject, text, html


def sign_in_code(first_name: str, code: str) -> tuple[str, str, str]:
    subject = "Your ORTU Fitness sign-in code"
    text, html = branded(
        "Your sign-in code",
        [
            f"Hi {first_name},",
            "Use this code to log in to your ORTU Fitness bookings. It is valid for 10 minutes.",
        ],
        code=code,
        footer_note="If you did not request this code, you can safely ignore this email.",
    )
    return subject, text, html


def membership_active(first_name: str, plan_name: str, price: str, credits_line: str, site_url: str) -> tuple[str, str, str]:
    subject = "Your ORTU Fitness membership is active"
    text, html = branded(
        "Welcome to ORTU Fitness!",
        [
            f"Hi {first_name},",
            f"Your Direct Debit is set up and your membership is now active: {plan_name} ({price}).",
            credits_line,
            "Payments are collected securely by GoCardless — they will email you before each collection.",
        ],
        cta=("Book your first class", site_url),
    )
    return subject, text, html
