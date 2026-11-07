"""Stub minimal de defusedxml : seules les API utilisées par CONCORDE."""

__version__: str

class DefusedXmlException(ValueError):
    """Base des refus de defusedxml."""

class DTDForbidden(DefusedXmlException):
    """Le document déclare une DTD."""

class EntitiesForbidden(DefusedXmlException):
    """Le document déclare des entités."""

class ExternalReferenceForbidden(DefusedXmlException):
    """Le document référence une ressource externe."""
