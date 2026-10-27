import click
import asyncio
import logging
from preloop.sync.services.nats_worker import main


@click.option(
    "--log-level",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default="INFO",
    help="Set the logging level.",
    show_default=True,
)
@click.option(
    "--tasks",
    type=str,
    help="Comma-separated list of tasks to run. If not provided, all tasks are run.",
    default=None,
)
@click.command(name="worker")
def worker_cmd(log_level: str, tasks: str):
    """
    Start the Preloop Sync worker service in the foreground.
    """
    logging.basicConfig(level=log_level)
    tasks_list = tasks.split(",") if tasks else []
    asyncio.run(main(tasks_allowlist=tasks_list))
