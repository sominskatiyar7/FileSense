"""FileCategorizer: decides which category folder a file belongs to."""
import os
from typing import Dict, List, Optional

from config import DEFAULT_CATEGORY, FILE_CATEGORIES


class FileCategorizer:
    def __init__(self, categories: Optional[Dict[str, List[str]]] = None) -> None:
        self.categories = categories or FILE_CATEGORIES
        # reverse lookup: ".pdf" -> "Documents"
        self._by_extension = {ext: name for name, exts in self.categories.items() for ext in exts}

    def get_category(self, file_name: str) -> str:
        """'photo.JPG' -> 'Images'. No extension or unknown extension -> 'Others'."""
        extension = os.path.splitext(file_name)[1].lower()
        if not extension:
            return DEFAULT_CATEGORY
        return self._by_extension.get(extension, DEFAULT_CATEGORY)

    def all_categories(self) -> List[str]:
        return list(self.categories.keys()) + [DEFAULT_CATEGORY]
