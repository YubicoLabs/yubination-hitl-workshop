"""
Scan commands for Preloop Sync CLI.
"""

import click
import datetime
import asyncio

from preloop.models.crud import crud_account, crud_tracker
from preloop.models.db.session import get_db_session

# Import scanner functions
from ..scanner import scan_account, scan_all_accounts  # Import scan_all_accounts
from ..scanner import scan_tracker as scan_tracker_func

# Import service components for the 'scan all' (now service start) command
from ..utils import safe_exit


@click.group()
def scan():
    """
    Commands for scanning issue trackers or starting the continuous sync service.
    """
    pass


@scan.command(name="all")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--force-update",
    "-f",
    is_flag=True,
    help="Force update of all embeddings even if content hasn't changed",
)
def scan_all_cmd(verbose: bool, force_update: bool):
    """
    Perform a ONE-OFF scan for all accounts and trackers.
    Does NOT start the continuous service.
    """
    # Get database session
    db = next(get_db_session())

    try:
        click.echo("Scanning all accounts and trackers...")

        # Scan all accounts (pass force_update)
        start = datetime.datetime.now()
        stats = asyncio.run(
            scan_all_accounts(db=db, verbose=verbose, force_update=force_update)
        )
        end = datetime.datetime.now()

        # Print summary
        click.echo("\n=== Scan Complete ===")
        click.echo(f"Accounts scanned: {stats['accounts_scanned']}")
        click.echo(f"Accounts with errors: {stats['accounts_with_errors']}")
        click.echo(f"Trackers scanned: {stats['trackers_scanned']}")
        click.echo(f"Trackers with errors: {stats['trackers_with_errors']}")
        click.echo(f"Organizations: {stats['organizations']['total']}")
        click.echo(f"Projects: {stats['projects']}")
        click.echo(f"Issues: {stats['issues']}")
        click.echo(f"Embeddings updated: {stats['embeddings_updated']}")
        click.echo(f"Duration: {(end - start).total_seconds():.2f} seconds")
    finally:
        db.close()


@scan.command(name="account")
@click.argument("account_id", type=str)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--force-update",
    "-f",
    is_flag=True,
    help="Force update of all embeddings even if content hasn't changed",
)
def scan_account_cmd(account_id: str, verbose: bool, force_update: bool):
    """
    Perform a ONE-OFF scan for a specific account and all its trackers.
    Does NOT start the continuous service.

    ACCOUNT_ID: The ID of the account to scan (UUID string).
    """
    # Get database session
    db = next(get_db_session())

    try:
        # Check if account exists
        account = crud_account.get(db, id=account_id)
        if not account:
            safe_exit(1, f"Account with ID {account_id} not found")

        click.echo(f"Scanning account: {account.username} (ID: {account.id})...")

        # Scan the account (pass force_update)
        start = datetime.datetime.now()
        stats = asyncio.run(
            scan_account(
                db=db, account_id=account_id, verbose=verbose, force_update=force_update
            )
        )
        end = datetime.datetime.now()

        # Print summary
        click.echo("\n=== Scan Complete ===")
        click.echo(f"Trackers: {stats['trackers']}")
        click.echo(f"Organizations: {stats['organizations']}")
        click.echo(f"Projects: {stats['projects']}")
        click.echo(f"Issues: {stats['issues']}")
        click.echo(f"Embeddings updated: {stats['embeddings_updated']}")
        click.echo(f"Duration: {(end - start).total_seconds():.2f} seconds")
    finally:
        db.close()


@scan.command(name="tracker")
@click.argument("tracker_id", type=str)
@click.option(
    "--force-update",
    "-f",
    is_flag=True,
    help="Force update of all embeddings even if content hasn't changed",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def scan_tracker_cmd(tracker_id: str, force_update: bool, verbose: bool):
    """
    Perform a ONE-OFF scan for a specific tracker.
    Does NOT start the continuous service.

    TRACKER_ID: The ID of the tracker to scan (UUID string).
    """
    # Get database session
    db = next(get_db_session())

    try:
        # Check if tracker exists
        tracker = crud_tracker.get(db, id=tracker_id)
        if not tracker:
            safe_exit(1, f"Tracker with ID {tracker_id} not found")

        click.echo(f"Scanning tracker: ID {tracker.id} ({tracker.tracker_type})...")

        # Scan the tracker (pass force_update)
        start = datetime.datetime.now()
        stats = asyncio.run(
            scan_tracker_func(
                db=db, tracker=tracker, force_update=force_update, verbose=verbose
            )
        )
        end = datetime.datetime.now()

        # Print summary
        click.echo("\n=== Scan Complete ===")
        click.echo(f"Organizations: {stats['organizations']}")
        click.echo(f"Projects: {stats['projects']}")
        click.echo(f"Issues: {stats['issues']}")
        click.echo(f"Embeddings updated: {stats['embeddings_updated']}")
        click.echo(f"Errors: {stats['errors']}")
        click.echo(f"Duration: {(end - start).total_seconds():.2f} seconds")
    finally:
        db.close()
