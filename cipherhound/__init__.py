"""
CIPHERHOUND - CGT Enterprises Password Security Research Platform
================================================================

An offline, terminal-inspired password-security research tool for authorized,
private cybersecurity education and internal research.

SCOPE / SAFETY
--------------
* 100% local and offline. No network calls are ever made.
* All testing happens against a synthetic, in-memory authentication simulator
  built from operator-supplied *fictional* data.
* No real credentials, tokens, or personal data are collected or stored.
* Generated candidate passwords are never written to disk and are never
  submitted to any external website or real authentication system.

This package is intentionally dependency-free (Python standard library only).
"""

__app_name__ = "CIPHERHOUND"
__company__ = "CGT ENTERPRISES"
__version__ = "1.0.0"
__tagline__ = "Synthetic Password Vulnerability Research Engine"

__all__ = ["__app_name__", "__company__", "__version__", "__tagline__"]
