"""Stub minimal de psycopg2 : seules les API utilisées par CONCORDE."""

from collections.abc import Iterator, Mapping, Sequence
from types import TracebackType
from typing import Any

class Error(Exception):
    """Erreur PostgreSQL (base de toutes les erreurs psycopg2)."""

class OperationalError(Error):
    """Base injoignable, accès refusé, connexion perdue."""

class cursor:
    """Curseur DB-API ; les valeurs lues ont des types SQL variés."""

    rowcount: int
    itersize: int
    def __enter__(self) -> cursor:
        """Ouvre le bloc with."""

    def __exit__(
        self,
        type_exception: type[BaseException] | None,
        exception: BaseException | None,
        trace: TracebackType | None,
    ) -> bool | None:
        """Ferme le bloc with."""

    def execute(
        self,
        requete: str,
        parametres: Sequence[object] | Mapping[str, object] = ...,
    ) -> None:
        """Exécute un ordre SQL (paramètres passés séparément)."""

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Toutes les lignes restantes."""

    def fetchone(self) -> tuple[Any, ...] | None:
        """La ligne suivante, ou None."""

    def fetchmany(self, size: int = ...) -> list[tuple[Any, ...]]:
        """Les size lignes suivantes."""

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        """Parcourt les lignes lues."""

    def close(self) -> None:
        """Ferme l'objet."""

class connection:
    """Connexion PostgreSQL."""

    autocommit: bool
    def cursor(self, name: str | None = ...) -> cursor:
        """Ouvre un curseur (nommé = côté serveur)."""

    def set_session(
        self, *, readonly: bool | None = ..., autocommit: bool | None = ...
    ) -> None:
        """Règle le mode de la session."""

    def commit(self) -> None:
        """Valide la transaction."""

    def rollback(self) -> None:
        """Annule la transaction."""

    def close(self) -> None:
        """Ferme l'objet."""

def connect(
    dsn: str | None = ...,
    *,
    dbname: str = ...,
    connect_timeout: int = ...,
    **parametres: object,
) -> connection:
    """Ouvre une connexion PostgreSQL."""
