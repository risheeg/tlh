"""Document taxonomy: categories, schemas, and prompt generation."""

from taxonomy.categories import CATEGORIES
from taxonomy.schemas import (
    FULL_TEXT_SCHEMAS,
    METADATA_SCHEMAS,
    get_targeted_schema,
)
from taxonomy.prompts import (
    DOCUMENT_SCHEMA,
    SYSTEM_PROMPT,
    get_extraction_prompt,
)
