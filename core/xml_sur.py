"""Lecture XML et XML-RPC protégées : seule porte d'entrée XML de CONCORDE.

Les classeurs .xlsx envoyés par les clients et les réponses XML-RPC des
Odoo distants sont des données non fiables. Tout passe par ce module, qui
s'appuie sur defusedxml : un XML piégé (bombe d'entités, entités externes,
DTD) est refusé au lieu d'être interprété.

- `lire_xml` remplace ``xml.etree.ElementTree.fromstring`` ;
- à l'import, ``defusedxml.xmlrpc.monkey_patch()`` protège le lecteur de
  réponses de ``xmlrpc.client`` ; les noms XML-RPC utiles sont ré-exportés
  ici pour que le reste du code n'importe jamais ``xmlrpc.client`` en direct.
"""

from __future__ import annotations

import xmlrpc.client
from collections.abc import Iterator
from typing import Optional, Protocol, TypeVar, overload

import defusedxml.xmlrpc
from defusedxml.ElementTree import ParseError, fromstring

defusedxml.xmlrpc.monkey_patch()

ProxyXmlRpc = xmlrpc.client.ServerProxy
TransportXmlRpc = xmlrpc.client.Transport
TransportXmlRpcSur = xmlrpc.client.SafeTransport
FauteXmlRpc = xmlrpc.client.Fault
ErreurXmlRpc = xmlrpc.client.Error
# Lecteur des réponses XML-RPC (protégé par monkey_patch ci-dessus).
lecteur_reponse_xmlrpc = xmlrpc.client.getparser
ErreurLectureXml = ParseError
ValeurParDefaut = TypeVar("ValeurParDefaut")


class ElementXml(Protocol):
    """Élément XML lu, tel que CONCORDE l'utilise (sous-ensemble d'Element)."""

    text: Optional[str]

    def find(
        self, path: str, namespaces: Optional[dict[str, str]] = ...
    ) -> Optional[ElementXml]:
        """Premier sous-élément qui correspond au chemin, ou None."""

    def iter(self, tag: Optional[str] = ...) -> Iterator[ElementXml]:
        """Parcourt l'élément et ses descendants (filtrés par balise)."""

    def __iter__(self) -> Iterator[ElementXml]:
        """Parcourt les enfants directs de l'élément."""

    @overload
    def get(self, key: str, default: None = None) -> Optional[str]:
        """Valeur d'un attribut, ou None."""

    @overload
    def get(self, key: str, default: ValeurParDefaut) -> str | ValeurParDefaut:
        """Valeur d'un attribut, ou la valeur par défaut donnée."""


def lire_xml(contenu: bytes | str) -> ElementXml:
    """Analyse un document XML non fiable et rend sa racine.

    Rôle : lecture XML sûre (defusedxml) des parties d'un .xlsx.
    Paramètres : contenu (bytes ou str), le document XML complet.
    Retour : l'élément racine.
    Erreurs : ErreurLectureXml (XML mal formé) ; DTDForbidden,
    EntitiesForbidden, ExternalReferenceForbidden (XML piégé).
    Usages : core/mapping.py, core/xlsx_vers_fec.py.
    """
    racine: ElementXml = fromstring(contenu)
    return racine
