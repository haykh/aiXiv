from enum import Enum
from importlib.resources import files


class ArxivCategoryValue(str, Enum):
    pass


def _enum_name(category: str) -> str:
    return category.replace("-", "_").replace(".", "_")


def _load_arxiv_categories() -> list[str]:
    text = files("aiXiv.arxiv").joinpath("arxiv_categories.csv").read_text()
    categories = [
        cat.strip()
        for cat in text.split(",")
        if cat.strip() and not cat.strip().startswith("#")
    ]

    if len(categories) != len(set(categories)):
        raise ValueError("Duplicate arXiv categories found")

    return categories


ArxivCategory = Enum(
    "ArxivCategory",
    {_enum_name(category): category for category in _load_arxiv_categories()},
    type=ArxivCategoryValue,
)
