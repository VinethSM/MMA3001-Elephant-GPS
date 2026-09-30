"""Record the software and hardware environment."""

from __future__ import annotations

from importlib.metadata import (
    PackageNotFoundError,
    version,
)
import json
from pathlib import Path
import platform
import sys

import psutil


PROJECT_FOLDER = Path(__file__).resolve().parents[1]
REPORTS_FOLDER = PROJECT_FOLDER / "reports"


def package_version(package_name: str) -> str:
    """Return an installed package version."""

    try:
        return version(package_name)
    except PackageNotFoundError:
        return "not installed"


def main() -> None:
    """Save a reproducible environment summary."""

    memory_gb = (
        psutil.virtual_memory().total
        / 1024**3
    )

    environment = {
        "platform": platform.platform(),
        "operating_system": (
            platform.system()
        ),
        "operating_system_release": (
            platform.release()
        ),
        "processor": platform.processor(),
        "logical_cpu_count": (
            psutil.cpu_count(logical=True)
        ),
        "physical_cpu_count": (
            psutil.cpu_count(logical=False)
        ),
        "total_memory_gb": round(
            memory_gb,
            2,
        ),
        "python_version": (
            sys.version
        ),
        "python_executable": (
            sys.executable
        ),
        "packages": {
            "numpy": package_version(
                "numpy"
            ),
            "pandas": package_version(
                "pandas"
            ),
            "scipy": package_version(
                "scipy"
            ),
            "matplotlib": package_version(
                "matplotlib"
            ),
            "seaborn": package_version(
                "seaborn"
            ),
            "pyyaml": package_version(
                "pyyaml"
            ),
            "pytest": package_version(
                "pytest"
            ),
        },
    }

    output_file = (
        REPORTS_FOLDER
        / "week5_computational_environment.json"
    )

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(
            environment,
            stream,
            indent=2,
        )

    print(
        json.dumps(
            environment,
            indent=2,
        )
    )

    print("Saved:", output_file)


if __name__ == "__main__":
    main()