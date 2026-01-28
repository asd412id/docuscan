# AGENTS.md - DocuScan Coding Guidelines

## Project Overview
DocuScan is a professional web-based document scanner application.
- **Backend**: Python 3.11+ / FastAPI / OpenCV / Tesseract OCR / PostgreSQL
- **Frontend**: React 19 / TypeScript / Vite / shadcn/ui / Tailwind CSS

## Build & Run Commands

### Backend (Python/FastAPI)
```bash
cd backend

# Setup virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run development server (port 8000)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run all tests
python -m pytest tests/ -v

# Run single test file
python -m pytest tests/test_auth.py -v

# Run single test function
python -m pytest tests/test_auth.py::TestAuth::test_register_user -v

# Run tests with coverage
python -m pytest tests/ -v --cov=app --cov-report=html
```

### Frontend (React/TypeScript)
```bash
cd frontend

# Install dependencies
npm install

# Run development server (port 5173)
npm run dev

# Build for production
npm run build

# Lint code
npm run lint

# Type check only
npx tsc --noEmit
```

### Docker (Development DB only)
```bash
docker-compose -f docker-compose.dev.yml up -d   # PostgreSQL + Redis
docker-compose up -d --build                      # Full production stack
```

## Code Style Guidelines

### Python (Backend)

**Imports**: Group in order - stdlib, third-party, local. Use absolute imports.
```python
# Standard library
import os
from datetime import datetime, timezone
from typing import Optional, List

# Third-party
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

# Local
from app.database import get_db
from app.models.models import User, Document
from app.schemas.schemas import DocumentResponse
```

**Formatting**: 
- Line length: 88 characters (Black default)
- Use double quotes for strings
- Use trailing commas in multi-line structures

**Type Hints**: Always use type hints for function parameters and returns.
```python
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
```

**Naming Conventions**:
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

**Error Handling**: Use HTTPException with appropriate status codes.
```python
if not document:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Document not found"
    )
```

**Async/Await**: All database operations and I/O must be async.
```python
async with aiofiles.open(file_path, "wb") as f:
    await f.write(content)
```

### TypeScript (Frontend)

**Imports**: Group in order - react, third-party, local (@/ alias).
```typescript
import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import type { Document, CornerPoints } from '@/types';
```

**Type Definitions**: Use `interface` for objects, `type` for unions/primitives.
```typescript
interface AuthState {
  user: User | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
}

type FilterMode = 'color' | 'grayscale' | 'bw';
```

**Component Structure**:
```typescript
interface ComponentProps {
  prop1: string;
  prop2?: number;
  onAction: () => void;
}

export function ComponentName({ prop1, prop2, onAction }: ComponentProps) {
  // hooks first
  const [state, setState] = useState(false);
  
  // callbacks
  const handleClick = useCallback(() => {}, []);
  
  // render
  return <div>...</div>;
}
```

**Naming Conventions**:
- Components: `PascalCase` (files and functions)
- Hooks: `useCamelCase`
- Variables/functions: `camelCase`
- Types/Interfaces: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

**State Management**: Use Zustand stores in `src/store/`.
```typescript
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({ ... }),
    { name: 'auth-storage' }
  )
);
```

**API Calls**: Use service files in `src/services/` with axios.
```typescript
export const documentService = {
  async upload(file: File): Promise<Document> {
    const response = await api.post<Document>('/documents/upload', formData);
    return response.data;
  },
};
```

## Project Structure

```
backend/
├── app/
│   ├── api/           # FastAPI route handlers
│   ├── models/        # SQLAlchemy models
│   ├── schemas/       # Pydantic schemas
│   ├── services/      # Business logic (scanner, ocr, pdf)
│   ├── config.py      # Settings from environment
│   ├── database.py    # Database connection
│   └── main.py        # FastAPI app initialization
├── tests/             # Pytest tests
└── requirements.txt

frontend/
├── src/
│   ├── components/    # React components
│   │   └── ui/        # shadcn/ui components
│   ├── pages/         # Page components (routes)
│   ├── services/      # API service functions
│   ├── store/         # Zustand state stores
│   ├── i18n/          # Translations (en.ts, id.ts)
│   ├── types/         # TypeScript type definitions
│   └── lib/           # Utility functions
└── package.json
```

## Key Patterns

### Backend API Endpoints
- Use UUID for public-facing IDs (security), internal int ID for DB
- Always validate ownership: `Document.user_id == current_user.id`
- Use Pydantic schemas for request/response validation

### Frontend State
- Auth state in `useAuthStore` (persisted)
- Scan workflow state in `useScanStore` (not persisted)
- Use React Query for server state caching

### Image Processing (scanner_service.py)
- Based on OpenCV's official square detection algorithm
- Process at max 1000px dimension for performance
- Scale coordinates back to original size

## Testing

### Backend Tests
- Tests in `backend/tests/` directory
- Use `pytest-asyncio` for async tests
- Fixtures in `conftest.py` provide `client`, `db_session`, `authenticated_client`
- Test database uses SQLite in-memory

### Test File Naming
- `test_*.py` - test files
- `Test*` - test classes
- `test_*` - test functions
