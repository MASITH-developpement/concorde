"""Stub minimal de defusedxml.ElementTree."""

from xml.etree.ElementTree import Element
from xml.etree.ElementTree import ParseError as ParseError

def fromstring(
    text: str | bytes,
    forbid_dtd: bool = ...,
    forbid_entities: bool = ...,
    forbid_external: bool = ...,
) -> Element:
    """Analyse un document XML (DTD et entités refusées)."""
