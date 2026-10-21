"""Connect this MCP folder to ASC without modifying or installing ASC."""

import argparse
import json
import os
import tempfile

from config import CONFIG_PATH, check_compatibility


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asc-root", required=True, help="Absolute path to an ASC source checkout.")
    parser.add_argument("--asc-python", help="Absolute ASC Python executable; otherwise retain ASC_PYTHON or saved settings, then use this interpreter.")
    args = parser.parse_args(argv)
    temporary_path = None
    try:
        report = check_compatibility(args.asc_root, args.asc_python)
        settings = {key: report[key] for key in ("asc_root", "asc_python")}
        # Replace only after every check succeeds; preserve a working binding
        # when a new checkout has missing or incompatible commands.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CONFIG_PATH.parent,
            prefix=".config-", suffix=".tmp", delete=False,
        ) as output:
            temporary_path = output.name
            json.dump(settings, output, indent=2)
            output.write("\n")
        os.replace(temporary_path, CONFIG_PATH)
        temporary_path = None
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")
    finally:
        if temporary_path is not None:
            os.unlink(temporary_path)
    report["config_file"] = str(CONFIG_PATH)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
