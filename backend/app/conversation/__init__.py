"""The investigation conversation (v4 Phase 3): a case is investigated by asking, turn after turn.

A thread per case keeps every message, the tools each answer used, the findings it referred to and
the stop reason of its loop. An answer is a set of claims, each citing lines of the case's files,
and every claim is verified - by the same verifier a mission uses - before it is shown. Nothing the
model says reaches a person unchecked, and nothing it thought is kept.
"""
