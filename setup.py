from setuptools import setup

setup(
    name="Lenticularis",
    version="0.0.0",
    author="",
    author_email="",
    description="",
    long_description="",
    long_description_content_type="text/markdown",
    url="",
    package_dir={
        "lenticularis": "src/lenticularis"
    },
    packages={
        "lenticularis"
    },
    package_data={
        "lenticularis": ["webui/*", "webui/scripts/*"],
    },
    entry_points={
        "console_scripts": ["lenticularis-admin=lenticularis.admin:main"]
    }
)
