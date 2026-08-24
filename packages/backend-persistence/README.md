# Citeframe Backend Persistence

The neutral `citeframe_persistence` package owns the single SQLAlchemy declarative
base and all API/Research ORM mappings. It has no dependency on `ai_pdf_api` or
Worker business code.
