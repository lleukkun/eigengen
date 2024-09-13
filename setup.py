from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="eigengen",
    version="0.1.2",
    package_dir={"": "src"},  # Tell setuptools packages are under src/
    packages=find_packages(where="src"),  # Look for packages under src/
    entry_points={
        "console_scripts": [
            "eigengen=eigengen.eigengen:main",  # Update if main script location changes
        ],
    },
    author="Lauri Leukkunen",
    author_email="lauri.leukkunen@gmail.com",
    description="EigenGen is a CLI LLM frontend for code generation with support for claude, gpt4 and llama3.1:70b.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/lleukkun/eigengen",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=requirements
)
