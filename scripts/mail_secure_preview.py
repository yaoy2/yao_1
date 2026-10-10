"""Prepared preview only. No scheduler, M14 write, filing, remote sync or mail cache.

The default plan is offline. Reads require the separately configured local
nsu-mail-reader backend and the explicit --approved-read flag.
"""

import argparse, json, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from utils.mail_secure_source import NoticeReader, SecureSourceError, plan, window


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SecureSourceError("INVALID_ARGUMENTS")


def main(argv=None):
    decode_details = None
    try:
        p = Parser(description=__doc__)
        p.add_argument(
            "mode", choices=("plan", "headers", "body"), nargs="?", default="plan"
        )
        p.add_argument("--approved-read", action="store_true")
        p.add_argument("--role", choices=("inbox", "sent"))
        p.add_argument("--start")
        p.add_argument("--end")
        p.add_argument("--next-uid", type=int, default=1)
        p.add_argument("--upper-uid", type=int)
        p.add_argument("--uidvalidity", type=int)
        p.add_argument("--span", type=int, default=100)
        p.add_argument("--uid", type=int)
        p.add_argument("--offset", type=int, default=0)
        p.add_argument("--chars", type=int, default=6000)
        args = p.parse_args(argv)
        if args.mode == "plan":
            result = plan()
        else:
            if not args.approved_read:
                raise SecureSourceError("SECURE_READ_APPROVAL_REQUIRED")
            if args.role is None:
                raise SecureSourceError("MAIL_FOLDER_NOT_ALLOWED")
            if args.mode == "headers":
                window(args.start, args.end)
            elif args.uid is None or args.uidvalidity is None:
                raise SecureSourceError("INVALID_BODY_REQUEST")
            with NoticeReader(approved=True) as reader:
                if args.mode == "headers":
                    result = reader.header_page(
                        args.role,
                        args.start,
                        args.end,
                        next_uid=args.next_uid,
                        upper_uid=args.upper_uid,
                        uidvalidity=args.uidvalidity,
                        span=args.span,
                    )
                else:
                    result = reader.body(
                        args.role,
                        args.uid,
                        args.uidvalidity,
                        offset=args.offset,
                        chars=args.chars,
                    )
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except SecureSourceError as exc:
        code = str(exc)
        decode_details = exc.decode_details
    except Exception:
        code = "SECURE_PREVIEW_FAILED"
    result = {"status": "error", "code": code, "coverage_advanced": False}
    if decode_details:
        result["decode_details"] = decode_details
    print(json.dumps(result))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
