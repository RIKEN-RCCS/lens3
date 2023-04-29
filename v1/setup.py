from setuptools import setup

setup(
    name="lenticularis",
    version="1.2",
    author="",
    author_email="",
    description="",
    long_description="",
    long_description_content_type="text/markdown",
    url="https://github.com/riken-rccs/lens3",
    packages={
        "lenticularis"
    },
    package_dir={
        "lenticularis": "src/lenticularis"
    },
    package_data={
        "lenticularis": ["webui/*", "webui/scripts/*"],
    },
    entry_points={
        "console_scripts": ["lens3-admin=lenticularis.admintool:main"]
    },
    install_requires=[
        'wheel',
        'jsonschema',
        'pyyaml',
        'redis',
        'gunicorn',
        'uvicorn',
        'fastapi',
        'fastapi_csrf_protect',
        'pytest']
)
