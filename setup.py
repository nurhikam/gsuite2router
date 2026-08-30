from setuptools import setup, find_packages

setup(
    name="gsuite2router",
    version="1.0.0",
    description="Auto Add GSuite accounts to 9Router Antigravity provider",
    packages=find_packages(),
    install_requires=[
        "DrissionPage>=4.0",
        "playwright>=1.40",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "gsuite2router=gsuite2router.cli:main",
        ],
    },
)
