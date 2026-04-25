import json
import jsonschema

from taxonomy import DOCUMENT_SCHEMA

try:
    jsonschema.Draft7Validator.check_schema(DOCUMENT_SCHEMA)
    print("Schema is perfectly valid!")
except Exception as e:
    print(f"Error validating schema: {e}")
