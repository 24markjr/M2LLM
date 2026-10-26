"""Accounts, sessions and roles (v4 Phase 1a).

Accounts live in JARVIS's own database rather than an external identity service, so the product runs
the same in the cloud, on a laptop and air-gapped. Passwords are scrypt-hashed (standard library);
sessions are random tokens kept only as SHA-256 hashes, sent as an HttpOnly cookie so the browser's
EventSource stream carries them too. Every `/api/` route is behind `app/auth/middleware.py`.
"""
