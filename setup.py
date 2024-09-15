# setup.py
from setuptools import setup, find_packages
from trf.__version__ import version

def read_version():
    with open("trf/__version__.py") as f:
        for line in f:
            if line.startswith("version"):
                # Extract the version string
                return line.split("=")[1].strip().strip("'")

print(f"{read_version = }")

setup(
    name="trf-dgraham",  # Replace with your app's name
    version=read_version(),
    author="Daniel A Graham",  # Replace with your name
    author_email="dnlgrhm@gmail.com",  # Replace with your email
    description="This is a simple application for recording the sequence of occasions on which a task is completed and forecasting when the next completion might be needed.",
    long_description=open("README.md").read(),  # If you have a README file
    long_description_content_type="text/markdown",
    url="https://github.com/dagraham/trf-dgraham",  # Replace with the repo URL if applicable
    packages=find_packages(),
    # py_modules=["trf"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  # Replace with your license
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7.3",  # Specify the minimum Python version
    install_requires=[
        'prompt-toolkit>=3.0.24',
        'ruamel.yaml>=0.15.88',
        'python-dateutil>=2.7.3',
    ],
    entry_points={
        'console_scripts': [
            'trf=trf.__main__:main',  # Correct the path to `main` in `trf/trf.py`
        ],
    },
)
