# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import io
import setuptools

with io.open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setuptools.setup(
    name="sg-otio",
    author="GPL Technologies",
    author_email="pipelinesupport@gpltech.com",
    version="0.0.1",
    description="A library for OpenTimelineIO integration with ShotGrid",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/GPLgithub/sg-otio.git",
    packages=setuptools.find_packages(),
    entry_points={
        "opentimelineio.plugins": "sg_otio = sg_otio"
    },
    package_data={
        "otio_shotgrid_adapter": [
            "plugin_manifest.json",
        ],
    },
    install_requires=[
        "OpenTimelineIO >= 0.12.0",
        "shotgun_api3 @ git+https://github.com/shotgunsoftware/python-api.git",
        "six",
        "pathlib2; python_version < '3.4'",
    ],
    extras_require={
        "dev": [
            "flake8",
            "pytest",
            "pytest-cov",
            "twine",
            "mock; python_version < '3.0.0'"
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Video",
        "Topic :: Multimedia :: Video :: Display",
        "Topic :: Multimedia :: Video :: Non-Linear Editor",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English"
    ]
)
