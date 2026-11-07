"""Stub de typage minimal de odoo.api : décorateur model et Environment."""

from collections.abc import Callable
from typing import TypeVar

from odoo.models import BaseModel

_Methode = TypeVar("_Methode", bound=Callable[..., object])

def model(method: _Methode) -> _Methode:
    """Marque une méthode indépendante des enregistrements."""

class Environment:
    """Environnement Odoo : accès aux modèles et à la société courante."""

    company: BaseModel

    def __getitem__(self, model_name: str) -> BaseModel:
        """Rend un recordset vide du modèle demandé."""

    def __contains__(self, model_name: object) -> bool:
        """Indique si le modèle est connu du registre."""
