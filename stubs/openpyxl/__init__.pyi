"""Stub minimal d'openpyxl : seules les API utilisées par CONCORDE."""

from collections.abc import Iterator
from typing import IO, Any

class Worksheet:
    """Feuille de calcul (lecture seule)."""

    # Valeurs de cellules : types dynamiques choisis par openpyxl.
    def iter_rows(
        self, *, values_only: bool = ...
    ) -> Iterator[tuple[Any, ...]]:
        """Parcourt les lignes de la feuille."""

class Workbook:
    """Classeur ouvert."""

    worksheets: list[Worksheet]
    def close(self) -> None:
        """Ferme l'objet."""

def load_workbook(
    filename: str | IO[bytes],
    read_only: bool = ...,
    keep_vba: bool = ...,
    data_only: bool = ...,
    keep_links: bool = ...,
    rich_text: bool = ...,
) -> Workbook:
    """Ouvre un classeur .xlsx."""
