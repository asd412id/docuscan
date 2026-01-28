# DocuScan - Professional Document Scanner

Aplikasi scan dokumen berbasis web yang profesional dan dapat diandalkan.

## Fitur Utama

- **Auto Edge Detection**: Deteksi tepi dokumen otomatis menggunakan OpenCV
- **Manual Corner Adjustment**: Sesuaikan sudut dokumen secara manual dengan drag & drop
- **Image Enhancement**: Filter warna, grayscale, hitam-putih, brightness, contrast
- **OCR (Optical Character Recognition)**: Ekstrak teks dari dokumen menggunakan Tesseract
- **Multi-page PDF Export**: Gabungkan beberapa scan menjadi satu PDF
- **Batch Processing**: Proses banyak dokumen sekaligus
- **Multi-language UI**: Bahasa Indonesia dan English

## Tech Stack

### Backend
- **Python 3.11** dengan FastAPI
- **OpenCV** untuk image processing
- **Tesseract** untuk OCR
- **PostgreSQL** untuk database
- **Redis** untuk caching dan queue

### Frontend
- **React 18** dengan TypeScript
- **Vite** untuk build tool
- **Tailwind CSS** + **shadcn/ui** untuk UI components
- **Zustand** untuk state management
- **React Query** untuk data fetching

### Infrastructure
- **Docker Compose** untuk production deployment
- **Nginx** sebagai reverse proxy

---

## Development Setup (Native)

### Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **PostgreSQL 16+**
- **Redis 7+**
- **Tesseract OCR**

### 1. Jalankan Database & Redis

Gunakan Docker untuk menjalankan PostgreSQL dan Redis saja:

```bash
docker-compose -f docker-compose.dev.yml up -d
```

Atau install dan jalankan PostgreSQL & Redis secara native.

### 2. Setup Backend

```bash
cd backend

# Buat virtual environment
python -m venv venv

# Aktifkan virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy dan sesuaikan environment variables
cp .env.example .env
# Edit .env sesuai konfigurasi lokal

# Jalankan backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Setup Frontend

```bash
cd frontend

# Install dependencies
npm install

# Jalankan development server
npm run dev
```

### 4. Akses Aplikasi

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **API Docs (ReDoc)**: http://localhost:8000/redoc

---

## Production Deployment (Docker)

### 1. Build dan Jalankan

```bash
# Set SECRET_KEY untuk production
export SECRET_KEY=$(openssl rand -hex 32)

# Build dan jalankan semua services
docker-compose up -d --build
```

### 2. Akses Aplikasi

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000

---

## Environment Variables

### Backend (.env)

```env
# Application
APP_NAME=DocuScan
APP_VERSION=1.0.0
DEBUG=true                    # false untuk production
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# Security
SECRET_KEY=your-secret-key    # Ganti dengan key yang aman untuk production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database
DATABASE_URL=postgresql+asyncpg://docuscan:docuscan@localhost:5432/docuscan

# Redis
REDIS_URL=redis://localhost:6379/0

# File Storage
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=20
FILE_RETENTION_MINUTES=60

# Tesseract OCR
# Windows: C:/Program Files/Tesseract-OCR/tesseract.exe
# Linux/Mac: /usr/bin/tesseract
TESSERACT_CMD=/usr/bin/tesseract
```

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register user baru |
| POST | `/api/auth/token` | Login dan dapatkan token |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/auth/me` | Info user saat ini |
| POST | `/api/auth/logout` | Logout |

### Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/documents/upload` | Upload dokumen |
| POST | `/api/documents/upload-batch` | Upload batch |
| GET | `/api/documents/` | List dokumen |
| GET | `/api/documents/{id}` | Detail dokumen |
| GET | `/api/documents/{id}/original` | Download original |
| GET | `/api/documents/{id}/processed` | Download hasil scan |
| GET | `/api/documents/{id}/thumbnail` | Thumbnail |
| DELETE | `/api/documents/{id}` | Hapus dokumen |

### Scan
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scan/detect/{id}` | Deteksi tepi dokumen |
| POST | `/api/scan/process` | Proses dokumen (crop, enhance) |
| POST | `/api/scan/ocr/{id}` | Ekstrak teks OCR |
| POST | `/api/scan/export` | Export ke PDF/gambar |
| POST | `/api/scan/batch-process` | Batch processing |

---

## Project Structure

```
docuscan/
├── backend/
│   ├── app/
│   │   ├── api/              # API routes
│   │   │   ├── auth.py       # Authentication endpoints
│   │   │   ├── documents.py  # Document management
│   │   │   └── scan.py       # Scan processing
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   │   ├── auth_service.py
│   │   │   ├── scanner_service.py
│   │   │   ├── ocr_service.py
│   │   │   └── pdf_service.py
│   │   ├── config.py         # Configuration
│   │   ├── database.py       # Database setup
│   │   └── main.py           # FastAPI app
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   │   ├── ui/           # shadcn/ui components
│   │   │   ├── FileUpload.tsx
│   │   │   ├── CornerAdjust.tsx
│   │   │   ├── FilterControls.tsx
│   │   │   └── Header.tsx
│   │   ├── pages/            # Page components
│   │   ├── services/         # API services
│   │   ├── store/            # Zustand stores
│   │   ├── i18n/             # Translations (ID + EN)
│   │   └── types/            # TypeScript types
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── docker-compose.yml        # Production deployment
├── docker-compose.dev.yml    # Development (DB + Redis only)
└── README.md
```

---

## Instalasi Tesseract OCR

### Windows
1. Download installer dari: https://github.com/UB-Mannheim/tesseract/wiki
2. Install dan catat path instalasi
3. Update `TESSERACT_CMD` di `.env`:
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

## License

MIT
