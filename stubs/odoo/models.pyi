"""Stub de typage minimal de odoo.models : modèles et recordsets."""

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Literal, overload

from typing_extensions import Self

from odoo.api import Environment

_Domaine = Sequence[Sequence[object]]

class BaseModel:
    """Recordset Odoo (ensemble ordonné d'enregistrements d'un modèle)."""

    _name: str
    _description: str
    _order: str
    _inherit: str | list[str]
    env: Environment
    id: int | Literal[False]

    def ensure_one(self) -> Self:
        """Vérifie que le recordset contient un seul enregistrement."""

    def create(
        self, vals_list: Mapping[str, object] | Sequence[Mapping[str, object]]
    ) -> Self:
        """Crée un ou plusieurs enregistrements."""

    def write(self, vals: Mapping[str, object]) -> bool:
        """Modifie les enregistrements du recordset."""

    def search(
        self,
        domain: _Domaine,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> Self:
        """Recherche les enregistrements correspondant au domaine."""

    def search_count(self, domain: _Domaine, limit: int | None = None) -> int:
        """Compte les enregistrements correspondant au domaine."""

    def search_read(
        self,
        domain: _Domaine | None = None,
        fields: Sequence[str] | None = None,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recherche et lit : valeurs dynamiques, propres à chaque champ."""

    def fields_get(
        self,
        allfields: Sequence[str] | None = None,
        attributes: Sequence[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Décrit les champs du modèle (attributs dynamiques par type)."""

    def default_get(self, fields_list: list[str]) -> dict[str, Any]:
        """Rend les valeurs par défaut des champs demandés."""

    @overload
    def __getitem__(self, key: str) -> Any:
        """Valeur d'un champ par son nom (type propre à chaque modèle)."""

    @overload
    def __getitem__(self, key: int) -> Self:
        """Enregistrement à la position donnée."""

    def __iter__(self) -> Iterator[Self]:
        """Parcourt les enregistrements un par un."""

    def __len__(self) -> int:
        """Nombre d'enregistrements."""

    def __bool__(self) -> bool:
        """Vrai si le recordset n'est pas vide."""

class Model(BaseModel):
    """Modèle Odoo persistant."""

class TransientModel(Model):
    """Modèle Odoo temporaire (assistants)."""
