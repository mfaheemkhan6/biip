"""Sphinx configuration file."""

project = "biip"
author = "Stein Magnus Jodal"
copyright = f"2020-2022, {author}"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinx_rtd_theme",
]

html_theme = "sphinx_rtd_theme"

autodoc_member_order = "bysource"
