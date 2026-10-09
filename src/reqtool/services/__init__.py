"""Use cases (ARC-03): what the application does, free of HTTP.

A router parses the request, calls a service and returns the result. The service holds the rules that were
once spread across handlers: merge-conflict and version checks, workflow guards, approval, commits, events.
Services raise ``ServiceError`` subclasses; one handler in ``api.py`` turns them into the response.
"""
