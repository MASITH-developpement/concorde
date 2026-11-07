"""Stub de typage minimal de odoo.release.

version_info est un namedtuple jusqu'à Odoo 19, un simple tuple en Odoo 20.
"""

version_info: tuple[int | str, ...]
version: str
