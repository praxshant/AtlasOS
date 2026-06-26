import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from backend.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=1800,
    pool_pre_ping=True,
    pool_timeout=30,
    connect_args={"options": f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}"}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    plan = Column(String, default="free")  # free, pro, enterprise
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="tenant")
    documents = relationship("Document", back_populates="tenant")
    audit_logs = relationship("AuditLog", back_populates="tenant")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index('ix_users_tenant', 'tenant_id', 'id'),
        Index('ix_users_tenant_username', 'tenant_id', 'username'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="engineer") # admin, engineer, viewer
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="users")
    audit_logs = relationship("AuditLog", back_populates="user")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index('ix_documents_tenant', 'tenant_id', 'id'),
        Index('ix_documents_tenant_status', 'tenant_id', 'status'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, unique=True, nullable=False)
    file_type = Column(String, nullable=False) # PDF, DOCX, TXT
    status = Column(String, default="pending") # pending, processing, completed, failed
    source = Column(String, default="upload") # upload, api
    upload_time = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="documents")
    jobs = relationship("ProcessingJob", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    entities = relationship("Entity", back_populates="document", cascade="all, delete-orphan")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index('ix_processing_jobs_tenant', 'tenant_id', 'id'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="pending") # pending, processing, completed, failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="jobs")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index('ix_chunks_tenant_doc', 'tenant_id', 'document_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, default=1)
    chunk_index = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    qdrant_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        Index('ix_entities_tenant_name', 'tenant_id', 'canonical_name'),
        Index('ix_entities_tenant_type', 'tenant_id', 'entity_type'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    canonical_name = Column(String, index=True, nullable=False)
    entity_type = Column(String, index=True, nullable=False) # Asset, Incident, Regulation, etc.
    confidence = Column(Float, default=1.0)
    source_doc_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="entities")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index('ix_audit_logs_tenant_time', 'tenant_id', 'timestamp'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False) # e.g. query_copilot, run_rca, upload_document
    query_text = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(Text, nullable=True) # JSON details represented as string

    tenant = relationship("Tenant", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")


def ensure_default_tenant():
    """
    Bootstrap default tenant if not exists.
    """
    db = SessionLocal()
    try:
        default_id = settings.DEFAULT_TENANT_ID
        tenant = db.query(Tenant).filter(Tenant.id == default_id).first()
        if not tenant:
            tenant = Tenant(
                id=default_id,
                name="Default Organization",
                slug=default_id,
                plan="free",
                is_active=True
            )
            db.add(tenant)
            db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def init_db():
    # Attempt to create tables (will not overwrite if they exist)
    Base.metadata.create_all(bind=engine)
    ensure_default_tenant()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
