from setuptools import setup, find_packages

setup(
    name="gridparse",
    version="1.0.0",
    description="Grid search directly from argparse",
    author="Georgios Chochlakis",
    author_email="chochlak@usc.edu",
    packages=find_packages(),
    install_requires=[],
    extras_require={"dev": ["black", "pytest"]},
)
