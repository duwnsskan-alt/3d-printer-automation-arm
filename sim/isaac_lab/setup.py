"""Installation script for the 'printer_arm_tasks' package."""

import os
import toml
from setuptools import find_packages, setup

EXTENSION_PATH = os.path.dirname(os.path.realpath(__file__))
EXTENSION_TOML_DATA = toml.load(os.path.join(EXTENSION_PATH, "config", "extension.toml"))

setup(
    name="printer_arm_tasks",
    version=EXTENSION_TOML_DATA["package"]["version"],
    description=EXTENSION_TOML_DATA["package"]["description"],
    keywords=EXTENSION_TOML_DATA["package"]["keywords"],
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[],
    zip_safe=False,
)
