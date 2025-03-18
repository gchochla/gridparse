from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gridparse",
    version="1.5.0",
    description="Grid search directly from argparse",
    author="Georgios Chochlakis",
    author_email="georgioschochlakis@gmail.com",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gchochla/gridparse",
    packages=find_packages(),
    install_requires=["omegaconf"],
    extras_require={"dev": ["black", "pytest"]},
)
