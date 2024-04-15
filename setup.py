# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import io
import setuptools
import subprocess

with io.open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()


def get_version():
    """
    Helper to extract a version number for this module.

    :returns: A major.minor.patch[.sub] version string or "dev".
    """
    # Try to extract the version number from git
    # this will work when installing from a locally cloned repo, or directly from
    # github, using the syntax:
    #
    # pip install git+https://github.com/GPLgithub/sg-otio@v0.18.32#egg=sg-otio
    #
    # Note: if you install from a cloned git repository
    # (e.g. pip install ./sg-otio), the version number
    # will be picked up from the most recently added tag.
    try:
        version_git = subprocess.check_output(
            ["git", "describe", "--abbrev=0", "--tags"]
        ).decode("utf-8").rstrip()
        print("Extracted version from git: %s" % version_git)
        return version_git
    except Exception as e:
        # Blindly ignore problems, git might be not available, or the user could
        # be installing from zip archive, etc...
        print("Could not extract version from git: %s" % e)

    # If everything fails, return a sensible string highlighting that the version
    # couldn't be extracted. If a version is not specified in `setup`, 0.0.0
    # will be used by default, it seems better to have an explicit keyword for
    # this case, following PEP440
    return "0.0.0.dev0"


setuptools.setup(
    name="sg-otio",
    author="GPL Technologies",
    author_email="pipelinesupport@gpltech.com",
    version=get_version(),
    description="A library for OpenTimelineIO integration with ShotGrid",
    long_description_content_type="text/markdown",
    long_description=readme,
    license="Apache License 2.0",
    license_files=["LICENSE.txt"],
    url="https://github.com/GPLgithub/sg-otio.git",
    packages=setuptools.find_packages(),
    scripts=["bin/sg-otio", "bin/sg-otio.py"],
    entry_points={
        "opentimelineio.plugins": "sg_otio = sg_otio"
    },
    include_package_data=True,
    package_data={
        "sg_otio": [
            "plugin_manifest.json",
        ],
    },
    install_requires=[
        "OpenTimelineIO == 0.12.1",
        "shotgun-api3 >= 3.3.3",
        "pathlib2; python_version < '3.4'",
        "futures; python_version < '3.2'",
    ],
    extras_require={
        "dev": [
            "flake8",
            "pytest",
            "pytest-cov",
            "twine",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Video",
        "Topic :: Multimedia :: Video :: Display",
        "Topic :: Multimedia :: Video :: Non-Linear Editor",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English"
    ]
)
