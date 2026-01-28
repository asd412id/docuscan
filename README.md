# DocuScan

<p align="center">
  <img src="frontend/public/logo.svg" alt="DocuScan Logo" width="120" height="120">
</p>

<p align="center">
  <strong>Professional Web-Based Document Scanner</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#api-reference">API Reference</a>
</p>

---

## Features

- **Auto Edge Detection** - Automatic document edge detection using OpenCV
- **Manual Corner Adjustment** - Fine-tune document corners with drag & drop
- **Image Enhancement** - Color, grayscale, black & white filters with brightness/contrast control
- **OCR (Optical Character Recognition)** - Extract text from documents using Tesseract
- **Multi-page PDF Export** - Combine multiple scans into a single PDF with customizable page sizes (A4, Letter, Legal, Folio/F4)
- **Batch Processing** - Process multiple documents at once with background task support
- **Multi-language UI** - Indonesian and English interface
- **Rate Limiting** - Built-in API rate limiting for security
- **JWT Authentication** - Secure authentication with access and refresh tokens

---

## Tech Stack

### Backend
| Technology | Purpose |
|------------|---------|
| Python 3.11 | Runtime |
| FastAPI | Web framework |
| OpenCV | Image processing |
| Tesseract | OCR engine |
| PostgreSQL | Database |
| Redis | Cache & message broker |
| Celery | Background task processing |
| SQLAlchemy | ORM |

### Frontend
| Technology | Purpose |
|------------|---------|
| React 19 | UI framework |
| TypeScript | Type safety |
| Vite | Build tool |
| Tailwind CSS | Styling |
| shadcn/ui | UI components |
| Zustand | State management |
| React Query | Data fetching |

### Infrastructure
| Technology | Purpose |
|------------|---------|
| Docker | Containerization |
| Nginx | Reverse proxy |
| Docker Compose | Orchestration |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 16+
- Redis 7+
- Tesseract OCR

### 1. Clone Repository

```bash
git clone https://github.com/asd412id/docuscan.git
cd docuscan
```

### 2. Start Database & Redis

```bash
docker-compose -f docker-compose.dev.yml up -d
```

### 3. Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env as needed

# Run backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Setup Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### 5. Access Application

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |

---

## Deployment

### Production with Docker

DocuScan uses a secure network architecture where only the frontend (Nginx) is exposed to the internet.

```
[Internet] → [Frontend:80] → [Backend] → [DB/Redis]
                   ↓
            (internal only)
```

#### 1. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Generate secure secret key
# Linux/Mac:
sed -i "s/your-super-secret-key-change-this-in-production/$(openssl rand -hex 32)/" .env

# Edit other variables as needed
nano .env
```

#### 2. Deploy

```bash
# Standard deployment
docker-compose up -d --build

# With Celery scheduler (for scheduled tasks)
docker-compose --profile scheduler up -d --build

# With Flower monitoring dashboard
docker-compose --profile monitoring up -d --build

# With both
docker-compose --profile scheduler --profile monitoring up -d --build
```

#### 3. Access

| Service | URL | Notes |
|---------|-----|-------|
| Application | http://localhost | Main entry point |
| Flower | http://localhost:5555 | Monitoring (localhost only, use SSH tunnel) |

#### Network Security

| Network | Type | Services |
|---------|------|----------|
| frontend-network | Public | Frontend only |
| backend-network | Internal | Frontend ↔ Backend |
| data-network | Internal | Backend/Celery ↔ DB/Redis |
| monitoring-network | Internal | Flower ↔ Redis |

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key | `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | Database password | `secure-password` |

### Optional Variables

See [`.env.example`](.env.example) for complete list of configurable options including:

- Application settings
- JWT token expiry
- Database configuration
- Redis configuration
- Celery worker settings
- Rate limiting
- File upload limits
- OCR language support

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/token` | Login and get token |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/auth/me` | Get current user info |
| POST | `/api/auth/logout` | Logout |

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/documents/upload` | Upload document |
| POST | `/api/documents/upload-batch` | Upload multiple documents |
| GET | `/api/documents/` | List documents |
| GET | `/api/documents/{id}` | Get document details |
| GET | `/api/documents/{id}/original` | Download original |
| GET | `/api/documents/{id}/processed` | Download processed |
| GET | `/api/documents/{id}/thumbnail` | Get thumbnail |
| DELETE | `/api/documents/{id}` | Delete document |

### Scan Processing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scan/detect/{id}` | Detect document edges |
| POST | `/api/scan/process` | Process document (crop, enhance) |
| POST | `/api/scan/ocr/{id}` | Extract text via OCR |
| POST | `/api/scan/export` | Export to PDF/image |
| POST | `/api/scan/batch-process` | Batch processing |

### Background Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks/{task_id}` | Get task status |
| DELETE | `/api/tasks/{task_id}` | Cancel task |

---

## Project Structure

```
docuscan/
├── backend/
│   ├── app/
│   │   ├── api/              # API route handlers
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   ├── tasks/            # Celery background tasks
│   │   ├── utils/            # Utilities (rate limiting, security)
│   │   ├── config.py         # Configuration
│   │   ├── database.py       # Database connection
│   │   ├── celery_app.py     # Celery configuration
│   │   └── main.py           # FastAPI app
│   ├── tests/                # Pytest tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   │   └── ui/           # shadcn/ui components
│   │   ├── pages/            # Page components
│   │   ├── services/         # API services
│   │   ├── store/            # Zustand stores
│   │   ├── hooks/            # Custom React hooks
│   │   ├── i18n/             # Translations (ID + EN)
│   │   └── types/            # TypeScript types
│   ├── Dockerfile
│   ├── nginx.conf.template
│   └── package.json
├── docker-compose.yml        # Production deployment
├── docker-compose.dev.yml    # Development (DB + Redis)
├── .env.example              # Environment template
└── AGENTS.md                 # Coding guidelines
```

---

## Tesseract OCR Installation

### Windows
1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Install and note the installation path
3. Update `TESSERACT_CMD` in `.env`:
   ```
   TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
   ```

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-ind
```

### macOS
```bash
brew install tesseract tesseract-lang
```

---

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=app --cov-report=html

# Run specific test file
python -m pytest tests/test_auth.py -v
```

### Frontend Type Check

```bash
cd frontend

# Type check
npx tsc --noEmit

# Lint
npm run lint
```

---

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  Made with ❤️ for document scanning
</p>
