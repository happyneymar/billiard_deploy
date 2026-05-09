import logging

logger = logging.getLogger(__name__)


def send_code(*, phone: str, message: str, code: str | None = None):
    """
    Demo SMS sender.

    Configure `SMS_SEND_FUNCTION=diary.sms.send_code` to enable this demo sender.
    Replace this implementation with your SMS provider integration.
    """
    logger.info("SMS sender demo. phone=%s message=%s code=%s", phone, message, code)
