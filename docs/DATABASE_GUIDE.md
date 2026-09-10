# Database Setup Guide - Media Monitoring Platform

## Overview

This document describes the complete database setup for Step 2: Database Connection & SQLAlchemy Models.

## Database Architecture

### Technology Stack
- **RDBMS**: PostgreSQL
- **ORM**: SQLAlchemy 2.0
- **Connection**: psycopg2-binary
- **Migration Tool**: Alembic (for future schema changes)

### Connection Flow
```
FastAPI Route
    ↓
get_db() Dependency (provides SQLAlchemy Session)
    ↓
SQLAlchemy Session
    ↓
SQLAlchemy Engine (psycopg2)
    ↓
PostgreSQL Database
```

## Database Files

### 1. `app/db/session.py`
Handles database connection and session management.

**Key Components:**
- `engine` - SQLAlchemy engine with PostgreSQL connection
- `SessionLocal` - Session factory for creating DB sessions
- `Base` - Declarative base for all ORM models
- `get_db()` - FastAPI dependency for injecting sessions into routes
- `init_db_connection()` - Test connection on startup
- `drop_all_tables()` - Emergency table reset (dev only)

**Usage in Routes:**
```python
from fastapi import Depends
from sqlalchemy.orm import Session
from app.db.session import get_db

@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

### 2. `app/db/init_db.py`
Database initialization and seeding.

**Key Functions:**
- `create_all_tables()` - Creates all tables from models using `Base.metadata.create_all()`
- `seed_default_admin()` - Creates default admin user (admin@example.com / admin123)
- `init_db()` - Main initialization function called on app startup
- `reset_database()` - DESTRUCTIVE: Drops and recreates all tables (dev only)

**Called During App Startup:**
```python
@app.on_event("startup")
async def startup_event():
    init_db()  # Creates tables + seeds data
```

## Database Models

### 1. User Model (`app/models/user.py`)

**Table:** `users`

**Schema:**
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,  -- 'admin' or 'analyst'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships:**
- One-to-Many with Reports (user can generate many reports)

**Default Data:**
- Email: `admin@example.com`
- Password: `admin123` (hashed with bcrypt)
- Role: `admin`

---

### 2. MonitoredSource Model (`app/models/source.py`)

**Table:** `monitored_sources`

**Schema:**
```sql
CREATE TABLE monitored_sources (
    id INTEGER PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,  -- 'facebook', 'x', 'reddit', 'youtube', 'instagram', 'rss'
    name VARCHAR(255) NOT NULL,
    url_or_handle VARCHAR(500) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_scraped_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships:**
- One-to-Many with Posts (source has many posts)

**Platform Values:**
- `facebook` - Facebook pages/groups
- `x` - Twitter/X accounts
- `reddit` - Subreddits/user posts
- `youtube` - YouTube channels
- `instagram` - Instagram accounts
- `rss` - RSS feeds

---

### 3. Keyword Model (`app/models/keyword.py`)

**Table:** `keywords`

**Schema:**
```sql
CREATE TABLE keywords (
    id INTEGER PRIMARY KEY,
    word_or_phrase VARCHAR(500) UNIQUE NOT NULL,
    category VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships:**
- None (standalone lookup table)

**Category Examples:**
- `violence` - Violence-related keywords
- `child-safety` - Child safety concerns
- `exploitation` - Exploitation indicators
- `general` - General monitoring keywords

---

### 4. Post Model (`app/models/post.py`)

**Table:** `posts`

**Schema:**
```sql
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES monitored_sources(id) ON DELETE CASCADE,
    external_id VARCHAR(500) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    author VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    media_urls JSON NULL,
    post_url VARCHAR(1000) NULL,
    published_at TIMESTAMP NOT NULL,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    violence_category VARCHAR(255) NULL,
    severity_level VARCHAR(20) NULL,  -- 'low', 'medium', 'high', 'critical'
    ai_summary TEXT NULL,
    raw_ai_response JSON NULL,
    is_flagged BOOLEAN DEFAULT FALSE
);
```

**Relationships:**
- Many-to-One with MonitoredSource (post belongs to one source)

**Severity Levels:**
- `low` - Minor concerning content
- `medium` - Moderately concerning content
- `high` - Severely concerning content
- `critical` - Immediate action required

**JSON Fields:**
- `media_urls` - Array of image/video URLs: `["url1", "url2", ...]`
- `raw_ai_response` - Complete AI analysis response with all fields

---

### 5. Report Model (`app/models/report.py`)

**Table:** `reports`

**Schema:**
```sql
CREATE TABLE reports (
    id INTEGER PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    generated_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    summary_text TEXT NULL,
    file_path VARCHAR(1000) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships:**
- Many-to-One with User (report generated by one user)

---

## API Endpoints (Step 2)

### Authentication (`app/api/auth.py`)

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
    "email": "admin@example.com",
    "password": "admin123"
}

Response (200 OK):
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "user_id": 1,
    "email": "admin@example.com",
    "full_name": "Administrator",
    "role": "admin"
}
```

#### Get Current User
```http
GET /api/auth/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

Response (200 OK):
{
    "id": 1,
    "email": "admin@example.com",
    "full_name": "Administrator",
    "role": "admin",
    "is_active": true
}
```

### User Management (`app/api/users.py`)

#### Create User (Admin Only)
```http
POST /api/users
Authorization: Bearer <token>
Content-Type: application/json

{
    "email": "analyst@example.com",
    "password": "secure_password",
    "full_name": "John Analyst",
    "role": "analyst"
}

Response (201 Created):
{
    "id": 2,
    "email": "analyst@example.com",
    "full_name": "John Analyst",
    "role": "analyst",
    "is_active": true
}
```

#### List Users (Admin Only)
```http
GET /api/users?skip=0&limit=10
Authorization: Bearer <token>

Response (200 OK):
[
    {
        "id": 1,
        "email": "admin@example.com",
        "full_name": "Administrator",
        "role": "admin",
        "is_active": true
    },
    {
        "id": 2,
        "email": "analyst@example.com",
        "full_name": "John Analyst",
        "role": "analyst",
        "is_active": true
    }
]
```

#### Get User by ID
```http
GET /api/users/1
Authorization: Bearer <token>

Response (200 OK):
{
    "id": 1,
    "email": "admin@example.com",
    "full_name": "Administrator",
    "role": "admin",
    "is_active": true
}
```

#### Update User
```http
PUT /api/users/2
Authorization: Bearer <token>
Content-Type: application/json

{
    "full_name": "John Updated",
    "role": "admin"
}

Response (200 OK):
{
    "id": 2,
    "email": "analyst@example.com",
    "full_name": "John Updated",
    "role": "admin",
    "is_active": true
}
```

#### Delete User (Admin Only)
```http
DELETE /api/users/2
Authorization: Bearer <token>

Response (204 No Content)
```

## PostgreSQL Setup Instructions

### 1. Install PostgreSQL (Windows)
- Download from: https://www.postgresql.org/download/windows/
- Install with default settings
- Note the password for postgres user

### 2. Create Database

Using pgAdmin:
1. Right-click Databases → Create → Database
2. Name: `media_monitor`
3. Owner: postgres
4. Click Save

Or using Command Line:
```bash
psql -U postgres
CREATE DATABASE media_monitor;
\q
```

### 3. Verify Connection

Test the connection string from .env:
```powershell
$ConnString = "postgresql://postgres:PASSWORD@localhost:5432/media_monitor"
python -c "from sqlalchemy import create_engine; engine = create_engine('$ConnString'); engine.connect(); print('✅ Connected!')"
```

### 4. Update .env

```env
DB_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/media_monitor
```

## Running the Application

### 1. Activate Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

### 2. Start Application
```powershell
python main.py
```

### 3. Watch for Startup Logs
```
================================================================================
🚀 Media Monitoring Platform v1.0.0 starting up...
================================================================================
Debug mode: True
Log level: INFO
✅ Database connection successful
================================================================================
🔄 Creating database tables...
✅ Database tables created/verified successfully
✅ Default admin user created: admin@example.com (ID: 1)
   ℹ️  Default credentials: email=admin@example.com, password=admin123
   ⚠️  IMPORTANT: Change these credentials in production!
================================================================================
✅ Database Initialization Complete
================================================================================
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 4. Test API

**In Swagger UI** (http://localhost:8000/docs):
1. Login with `admin@example.com` / `admin123`
2. Copy the access_token
3. Click "Authorize" button, paste token with "Bearer " prefix
4. Test endpoints

**Or Using PowerShell:**
```powershell
# Login
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/auth/login" `
  -Method Post `
  -Headers @{"Content-Type"="application/json"} `
  -Body (@{email="admin@example.com"; password="admin123"} | ConvertTo-Json)

$token = $response.access_token
Write-Host "Token: $token"

# Get current user
Invoke-RestMethod -Uri "http://localhost:8000/api/auth/me" `
  -Method Get `
  -Headers @{"Authorization"="Bearer $token"}
```

## Database Administration

### View Tables in PostgreSQL
```sql
-- Connect to database
psql -U postgres -d media_monitor

-- List all tables
\dt

-- View table schema
\d users
\d monitored_sources
\d keywords
\d posts
\d reports

-- Query data
SELECT * FROM users;
SELECT * FROM posts LIMIT 5;
```

### Reset Database (Development Only)
```powershell
# This will drop and recreate all tables
python -c "from app.db.init_db import reset_database; reset_database()"
```

### Backup Database
```powershell
# Windows Command Prompt
pg_dump -U postgres -d media_monitor -F c -b -v -f media_monitor_backup.dump

# Restore
pg_restore -U postgres -d media_monitor -v media_monitor_backup.dump
```

## Performance Considerations

### Indexes
Current indexes are on:
- `users.email` - for fast login lookups
- `monitored_sources.platform` - for filtering by platform
- `keywords.word_or_phrase` - for keyword matching
- `posts.source_id` - for foreign key joins
- `posts.platform` - for platform filtering
- `reports.generated_by` - for user report lookups

### Future Optimization
- Add composite indexes for common queries
- Implement database partitioning for large post tables
- Consider materialized views for reports
- Add query caching with Redis

## Common Issues & Troubleshooting

### Issue: "could not connect to server"
**Solution:** Ensure PostgreSQL is running
```powershell
# Windows Service Check
Get-Service postgresql-x64-*
# If stopped: Start-Service postgresql-x64-15 (adjust version)
```

### Issue: "password authentication failed"
**Solution:** Check .env DB_URL password and special characters are properly escaped

### Issue: "relation 'users' does not exist"
**Solution:** Database tables weren't created. Check logs for errors and run:
```powershell
python -c "from app.db.init_db import init_db; init_db()"
```

### Issue: "foreign key constraint violation"
**Solution:** Ensure referenced records exist before inserting
- Create MonitoredSource before creating Posts
- Create User before creating Reports

## Next Steps

- Step 3: Implement monitoring/scraping services
- Step 4: Integrate AI content analysis (Gemini API)
- Step 5: Implement report generation
- Step 6: Add websocket for real-time updates

