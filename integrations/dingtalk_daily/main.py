"""Standalone entry point; does not import or start Streamlit."""
from dingtalk_daily.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
