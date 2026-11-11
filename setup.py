from setuptools import setup, find_namespace_packages

with open("cli_anything/drawio/README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="cli-anything-drawio",
    version="1.0.0",
    description="Stateful CLI harness for draw.io diagrams — rendered by the real draw.io Desktop",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="cli-anything",
    license="Apache-2.0",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_data={"cli_anything.drawio": ["skills/*.md", "README.md"]},
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=["click>=8.0", "prompt_toolkit>=3.0"],
    extras_require={"test": ["pytest>=7"]},
    entry_points={"console_scripts": ["cli-anything-drawio=cli_anything.drawio.drawio_cli:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Environment :: Console",
        "Topic :: Multimedia :: Graphics :: Editors :: Vector-Based",
    ],
    zip_safe=False,
)
