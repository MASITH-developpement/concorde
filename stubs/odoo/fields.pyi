"""Stub de typage minimal de odoo.fields.

Chaque champ est un descripteur : lu sur la classe, il rend le champ ;
lu sur un enregistrement, il rend la valeur (False si vide).
"""

from datetime import date, datetime
from typing import Generic, Literal, SupportsBytes, TypeVar, overload

from typing_extensions import Self

from odoo.models import BaseModel

_Valeur = TypeVar("_Valeur")

class Field(Generic[_Valeur]):
    """Champ Odoo générique."""

    def __init__(self, string: str = ..., **options: object) -> None:
        """Déclare le champ avec son libellé et ses options."""

    @overload
    def __get__(self, record: None, owner: type[BaseModel]) -> Self:
        """Lecture sur la classe : rend le champ."""

    @overload
    def __get__(self, record: BaseModel, owner: type[BaseModel]) -> _Valeur:
        """Lecture sur un enregistrement : rend la valeur."""

class Boolean(Field[bool]):
    """Champ booléen."""

class Integer(Field[int]):
    """Champ entier."""

class Float(Field[float]):
    """Champ décimal."""

class Char(Field[str | Literal[False]]):
    """Champ texte court."""

class Text(Field[str | Literal[False]]):
    """Champ texte long."""

class Html(Field[str | Literal[False]]):
    """Champ HTML."""

class Binary(Field[str | bytes | SupportsBytes | Literal[False]]):
    """Champ binaire : base64 (Odoo <= 19) ou BinaryValue (Odoo 20)."""

class Selection(Field[str | Literal[False]]):
    """Champ liste de choix."""

    def __init__(
        self,
        selection: list[tuple[str, str]],
        string: str = ...,
        **options: object,
    ) -> None:
        """Déclare la liste des choix (valeur, libellé)."""

class Date(Field[date | Literal[False]]):
    """Champ date."""

    @staticmethod
    def today(*args: object) -> date:
        """Date du jour."""

class Datetime(Field[datetime | Literal[False]]):
    """Champ date et heure."""

    @staticmethod
    def now(*args: object) -> datetime:
        """Date et heure courantes."""

class Many2one(Field[BaseModel]):
    """Champ lien vers un enregistrement d'un autre modèle."""

    def __init__(
        self, comodel_name: str, string: str = ..., **options: object
    ) -> None:
        """Déclare le modèle cible."""

class One2many(Field[BaseModel]):
    """Champ liste des enregistrements liés par un Many2one inverse."""

    def __init__(
        self,
        comodel_name: str,
        inverse_name: str,
        string: str = ...,
        **options: object,
    ) -> None:
        """Déclare le modèle cible et le champ inverse."""
