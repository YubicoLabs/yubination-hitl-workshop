"""
Main entry point for preloop.sync.
"""

from .cli.commands import run
from preloop.models.sentry import init_sentry

if __name__ == "__main__":
    init_sentry()
    run()
