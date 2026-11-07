"""Stub de typage minimal de odoo.exceptions."""

class UserError(Exception):
    """Erreur affichée à l'utilisateur."""

    def __init__(self, message: str) -> None:
        """Construit l'erreur avec son message."""

class AccessError(UserError):
    """Accès refusé par les droits de l'utilisateur."""
