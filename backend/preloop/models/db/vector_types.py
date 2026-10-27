"""SQLAlchemy types for vector storage and UUID handling."""

from typing import Any, List, Optional

import numpy as np
from sqlalchemy import TypeDecorator, text
from sqlalchemy.engine.interfaces import Dialect

from pgvector.sqlalchemy import Vector

TRUNCATED_VECTOR_SIZE = 128


class VectorType(TypeDecorator):
    """
    SQLAlchemy type for vector embeddings with pgvector support.

    This type automatically uses pgvector's Vector type,
    """

    impl = Vector
    cache_ok = True

    def __init__(self, dimensions: int, **kwargs: Any):
        """Initialize the vector type with dimension information."""
        self.dimensions = dimensions
        super().__init__(**kwargs)

    def process_result_value(
        self, value: Any, dialect: Dialect
    ) -> Optional[List[float]]:
        """Convert the stored value back to a vector."""
        if value is None:
            return None

        if isinstance(value, np.ndarray):
            return value.tolist()
        return value

    @property
    def python_type(self) -> type:
        """Return the Python type for this SQLAlchemy type."""
        return list


def cosine_distance(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine distance between two vectors."""
    a = np.array(v1)
    b = np.array(v2)
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def euclidean_distance(v1: List[float], v2: List[float]) -> float:
    """Calculate euclidean distance between two vectors."""
    a = np.array(v1)
    b = np.array(v2)
    return np.linalg.norm(a - b)


def check_pgvector_extension(engine: Any) -> bool:
    """Check if pgvector extension is installed in PostgreSQL."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar()
        return bool(result)


def install_pgvector_extension(engine: Any) -> bool:
    """Install pgvector extension in PostgreSQL if not already installed."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
