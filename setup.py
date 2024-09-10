from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="eigengen",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "eigengen=eigengen.eigengen:main",
        ],
    },
    author="Lauri Leukkunen",
    author_email="lauri.leukkunen@gmail.com",
    description="EigenGen is a CLI code generator supporting Anthropic Claude 3.5 Sonnet model.",
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

