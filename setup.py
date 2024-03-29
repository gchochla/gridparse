from setuptools import setup, find_packages

setup(
    name="gridparse",
    version="1.4.0",
    description="Grid search directly from argparse",
    author="Georgios Chochlakis",
    author_email="chochlak@usc.edu",
    packages=find_packages(),
    extras_require={"dev": ["black", "pytest"]},
)
