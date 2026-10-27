"""Operator CLI for reusable workshop signup codes."""

import argparse
import json
from typing import Sequence
from uuid import UUID

from preloop.models.crud import workshop_signup_code as code_crud
from preloop.models.db import get_session_factory
from preloop.services import workshop_signup_codes


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--count", type=int, default=1)
    create.add_argument("--label")
    commands.add_parser("list")
    delete = commands.add_parser("delete")
    delete.add_argument("id", type=UUID)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "create" and not 1 <= args.count <= 1000:
        _parser().error("--count must be between 1 and 1000")
    if args.command == "create" and args.label is not None and len(args.label) > 200:
        _parser().error("--label must be at most 200 characters")

    with get_session_factory()() as db:
        if args.command == "create":
            output = []
            for _ in range(args.count):
                record, plaintext = workshop_signup_codes.create(db, label=args.label)
                output.append(
                    {
                        "id": str(record.id),
                        "label": record.label,
                        "code": plaintext,
                        "created_at": record.created_at.isoformat(),
                    }
                )
        elif args.command == "list":
            output = [
                {
                    "id": str(record.id),
                    "label": record.label,
                    "created_at": record.created_at.isoformat(),
                }
                for record in code_crud.list_all(db)
            ]
        else:
            code_crud.delete(db, code_id=args.id)
            output = {"deleted": True, "id": str(args.id)}

    print(json.dumps(output, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
