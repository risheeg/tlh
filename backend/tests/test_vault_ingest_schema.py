import os
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.constraints import ensure_db_schemas
from models.models import Document


POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")


@unittest.skipUnless(
    POSTGRES_TEST_DATABASE_URL,
    "Set POSTGRES_TEST_DATABASE_URL to run vault_ingest Postgres schema tests.",
)
class VaultIngestSchemaTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(POSTGRES_TEST_DATABASE_URL, pool_pre_ping=True)
        ensure_db_schemas(self.engine)
        Document.__table__.drop(bind=self.engine, checkfirst=True)
        Document.__table__.create(bind=self.engine, checkfirst=True)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        Document.__table__.drop(bind=self.engine, checkfirst=True)
        self.engine.dispose()

    def test_document_round_trip(self):
        document = Document(
            id=uuid.uuid4(),
            upload_date=datetime.now(timezone.utc),
            processed_at=datetime.now(timezone.utc),
            category="tax",
            subcategory="1099",
            r2_original_path="inbox/example.pdf",
            r2_file_path="processed/tax/example.pdf",
            r2_parsed_json_path="parsed/tax/example.json",
            file_size=12345,
            ai_model="@cf/google/gemma-4-26b-a4b-it",
            parsed_json={"category": "tax", "subcategory": "1099"},
        )

        self.db.add(document)
        self.db.commit()

        saved = self.db.get(Document, document.id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.category, "tax")
        self.assertEqual(saved.parsed_json["subcategory"], "1099")


if __name__ == "__main__":
    unittest.main()
