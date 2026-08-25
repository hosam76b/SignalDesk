# Step 2 Quick Start & Testing Guide

## Verify Installation

### 1. Check Virtual Environment
```powershell
# Should show "(venv)" in your prompt
.\venv\Scripts\Activate.ps1

# Verify key packages
pip list | grep -E "fastapi|sqlalchemy|psycopg2|pydantic"
```

### 2. Verify PostgreSQL Connection
```powershell
# Test database connectivity
python -c "from app.db.session import init_db_connection; init_db_connection()"

# Expected output:
# ✅ Database connection successful
```

### 3. Check All Files Created
```powershell
# Verify models exist
Get-ChildItem app\models\*.py

# Output should show:
# keyword.py, post.py, report.py, source.py, user.py

# Verify API endpoints exist
Get-ChildItem app\api\*.py

# Output should show:
# auth.py, users.py

# Verify database files exist
Get-ChildItem app\db\*.py

# Output should show:
# init_db.py, session.py
```

---

## Start the Application

### Command
```powershell
# Make sure virtual environment is active
python main.py
```

### Expected Startup Output
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

⚠️ **If you see errors:**
- Check PostgreSQL is running
- Verify .env DB_URL is correct
- Ensure database `media_monitor` exists
- Check network connectivity to PostgreSQL

---

## Test the API

### Option 1: Swagger UI (Recommended)

1. Open browser: http://localhost:8000/docs
2. You should see all endpoints documented

### Option 2: PowerShell Testing

#### Test 1: Login
```powershell
# Login with default admin credentials
$loginResponse = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/auth/login" `
  -Method Post `
  -ContentType "application/json" `
  -Body @"
{
    "email": "admin@example.com",
    "password": "admin123"
}
"@

# Extract token
$token = $loginResponse.access_token
Write-Host "✅ Login successful!"
Write-Host "Token: $token"
Write-Host "User: $($loginResponse.email) ($($loginResponse.role))"
```

#### Test 2: Get Current User
```powershell
$userResponse = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/auth/me" `
  -Method Get `
  -Headers @{"Authorization"="Bearer $token"}

Write-Host "✅ Current user retrieved!"
Write-Host "Name: $($userResponse.full_name)"
Write-Host "Role: $($userResponse.role)"
Write-Host "Active: $($userResponse.is_active)"
```

#### Test 3: Create New User (Admin Only)
```powershell
$newUserResponse = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/users" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"Authorization"="Bearer $token"} `
  -Body @"
{
    "email": "analyst@example.com",
    "password": "SecurePassword123!",
    "full_name": "John Analyst",
    "role": "analyst"
}
"@

Write-Host "✅ User created successfully!"
Write-Host "User ID: $($newUserResponse.id)"
Write-Host "Email: $($newUserResponse.email)"
Write-Host "Role: $($newUserResponse.role)"
```

#### Test 4: List All Users (Admin Only)
```powershell
$usersResponse = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/users" `
  -Method Get `
  -Headers @{"Authorization"="Bearer $token"}

Write-Host "✅ Total users: $($usersResponse.Count)"
$usersResponse | ForEach-Object {
    Write-Host "  - $($_.full_name) ($($_.email)) - Role: $($_.role)"
}
```

#### Test 5: Get Specific User
```powershell
$userDetailsResponse = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/users/1" `
  -Method Get `
  -Headers @{"Authorization"="Bearer $token"}

Write-Host "✅ User details retrieved!"
Write-Host $userDetailsResponse
```

#### Test 6: Update User (Admin Only)
```powershell
$updateResponse = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/users/2" `
  -Method Put `
  -ContentType "application/json" `
  -Headers @{"Authorization"="Bearer $token"} `
  -Body @"
{
    "full_name": "John Updated",
    "role": "admin"
}
"@

Write-Host "✅ User updated successfully!"
Write-Host "New name: $($updateResponse.full_name)"
Write-Host "New role: $($updateResponse.role)"
```

#### Test 7: Test Unauthorized Access
```powershell
# Try without token - should fail
try {
    Invoke-RestMethod `
      -Uri "http://localhost:8000/api/users" `
      -Method Get `
      -ErrorAction Stop
}
catch {
    Write-Host "✅ Correctly rejected unauthorized request!"
    Write-Host "Error: $($_.Exception.Response.StatusCode)"
}
```

---

## Database Verification

### Check Tables in PostgreSQL
```powershell
# Connect to PostgreSQL
$ConnString = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/media_monitor"

# List tables
psql -U postgres -d media_monitor -c "\dt"

# Expected output:
#             List of relations
#  Schema |       Name        | Type  | Owner
# --------+-------------------+-------+-------
#  public | keywords          | table | postgres
#  public | monitored_sources | table | postgres
#  public | posts             | table | postgres
#  public | reports           | table | postgres
#  public | users             | table | postgres
```

### Check Default Admin User
```powershell
psql -U postgres -d media_monitor -c "SELECT id, email, full_name, role, is_active FROM users;"

# Expected output:
# id |       email        |     full_name      | role  | is_active
# ----+--------------------+--------------------+-------+-----------
#  1 | admin@example.com  | Administrator      | admin | t
```

### Check User Table Structure
```powershell
psql -U postgres -d media_monitor -c "\d users"

# Shows all columns and their types
```

---

## Common Test Scenarios

### Scenario 1: User Login Flow
```powershell
# 1. Login
$token = (Invoke-RestMethod -Uri http://localhost:8000/api/auth/login `
  -Method Post -ContentType application/json `
  -Body '{"email":"admin@example.com","password":"admin123"}').access_token

# 2. Get user info
Invoke-RestMethod -Uri http://localhost:8000/api/auth/me `
  -Method Get -Headers @{"Authorization"="Bearer $token"}

# 3. Create new user
Invoke-RestMethod -Uri http://localhost:8000/api/users `
  -Method Post -ContentType application/json `
  -Headers @{"Authorization"="Bearer $token"} `
  -Body '{"email":"test@example.com","password":"test123","full_name":"Test User","role":"analyst"}'
```

### Scenario 2: Permission Testing
```powershell
# Get analyst token
$analystToken = (Invoke-RestMethod -Uri http://localhost:8000/api/auth/login `
  -Method Post -ContentType application/json `
  -Body '{"email":"analyst@example.com","password":"SecurePassword123!"}').access_token

# Try to create user as analyst (should fail)
try {
    Invoke-RestMethod -Uri http://localhost:8000/api/users `
      -Method Post -ContentType application/json `
      -Headers @{"Authorization"="Bearer $analystToken"} `
      -Body '{"email":"another@example.com","password":"pass123","full_name":"Another","role":"analyst"}' `
      -ErrorAction Stop
} catch {
    Write-Host "✅ Correctly rejected non-admin user!"
    Write-Host ($_.Exception.Response | Select-Object StatusCode, StatusDescription)
}
```

### Scenario 3: Invalid Credentials
```powershell
try {
    Invoke-RestMethod -Uri http://localhost:8000/api/auth/login `
      -Method Post -ContentType application/json `
      -Body '{"email":"admin@example.com","password":"wrongpassword"}' `
      -ErrorAction Stop
} catch {
    Write-Host "✅ Correctly rejected invalid password!"
    Write-Host "Status: $($_.Exception.Response.StatusCode)"
}
```

---

## Expected HTTP Status Codes

| Endpoint | Method | Success | Unauthorized | Forbidden | Not Found |
|----------|--------|---------|--------------|-----------|-----------|
| /api/auth/login | POST | 200 | 401 | - | - |
| /api/auth/me | GET | 200 | 401 | - | - |
| /api/users | POST | 201 | 401 | 403 | - |
| /api/users | GET | 200 | 401 | 403 | - |
| /api/users/{id} | GET | 200 | 401 | 403 | 404 |
| /api/users/{id} | PUT | 200 | 401 | 403 | 404 |
| /api/users/{id} | DELETE | 204 | 401 | 403 | 404 |

---

## Troubleshooting

### Issue: "could not translate host name"
**Cause**: PostgreSQL not running or wrong hostname  
**Solution**:
```powershell
# Check PostgreSQL status
Get-Service postgresql-x64-*

# If stopped, start it
Start-Service postgresql-x64-15  # Adjust version as needed
```

### Issue: "password authentication failed"
**Cause**: Wrong password in .env  
**Solution**: Update DB_URL in .env with correct PostgreSQL password

### Issue: "relation 'users' does not exist"
**Cause**: Tables weren't created  
**Solution**: Delete .env and rebuild, or manually run init_db

### Issue: "token_type is not 'bearer'"
**Cause**: Login endpoint returning wrong format  
**Solution**: Check auth.py returns TokenResponse correctly

### Issue: Port 8000 already in use
**Cause**: Another application using port 8000  
**Solution**:
```powershell
# Run on different port
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

---

## Next Steps

1. ✅ Verify all tests pass
2. ✅ Test with Swagger UI for API documentation
3. ✅ Review database schema in PostgreSQL
4. ✅ Proceed to Step 3: Monitoring Services implementation

---

## Documentation Files

- **DATABASE_GUIDE.md** - Complete database architecture and setup
- **STEP2_COMPLETION.md** - Detailed implementation summary
- **SETUP_GUIDE.md** - Initial project setup instructions

---

**Ready to test? Run:** `python main.py` and visit http://localhost:8000/docs
