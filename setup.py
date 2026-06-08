from pathlib import Path

from setuptools import find_packages, setup

setup(
    name="haansaan",
    version="0.1.0",
    description="Purpose-driven verifier and judgment trigger router",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="coreeeeaaaa",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    entry_points={"console_scripts": ["haansaan=haansaan.cli:main"]},
)
