"""Mac entry point; implementation lives in the installable pkb package."""

from pkb.backup_client import checked_path, main, unpack_verified

if __name__ == "__main__":
    raise SystemExit(main())
