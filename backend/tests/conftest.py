import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.docuvault import models as docuvault_models  # noqa: F401
from app.modules.inboxzero import models as inboxzero_models  # noqa: F401
from app.modules.learnloop import models as learnloop_models  # noqa: F401
from app.modules.lifeos import models as lifeos_models  # noqa: F401
from app.modules.mealmind import models as mealmind_models  # noqa: F401
from app.modules.pricepilot import models as pricepilot_models  # noqa: F401
from app.modules.spendwise import models as spendwise_models  # noqa: F401


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
