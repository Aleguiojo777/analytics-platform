# Python AI Server Integration

The Analytics Platform now integrates Python for AI-powered insights. This document explains how to set up and run the server.

## Architecture

- **Python Flask Server** (Port 3000): Full web application, SQL Server connectivity, and analytics backend.

The Flask app serves the frontend and handles analytics requests.

## Setup Instructions

### 1. Install Python (Windows)

**Option A: Download from python.org**
- Go to https://www.python.org/downloads/
- Download Python 3.9+ for Windows
- Run installer and check "Add Python to PATH"
- Verify: Open PowerShell and run `python --version`

**Option B: Use Windows Package Manager**
```powershell
winget install Python.Python.3.11
```

**Option C: Use Chocolatey**
```powershell
choco install python
```

### 2. Create Python Virtual Environment

```powershell
# Navigate to project directory
cd d:\analytics-platform

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# If you get execution policy error, run:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

## Running the Application

### Start the Python Flask Server
```powershell
cd d:\analytics-platform
.\venv\Scripts\Activate.ps1
python server.py
# Server will run on http://localhost:3000
```

### Access the App

Open your browser and go to: **http://localhost:3000**

## Features Powered by Python AI

- ✅ **Anomaly Detection** - Z-score based outlier detection with severity levels
- ✅ **Trend Analysis** - Linear regression to detect upward/downward trends
- ✅ **Statistical Analysis** - Mean, median, standard deviation, min/max
- ✅ **Detailed Recommendations** - Specific suggestions for data issues
- ✅ **Data Quality Score** - Overall health score (0-100)
- ✅ **Executive Summary** - High-level insights across all numeric columns

## Troubleshooting

### Python API not responding?
- Check if Python server is running on port 3000
- Check for error messages in Python terminal

### Can't activate virtual environment?
```powershell
# If you get execution policy error, run:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# Then try activating again:
.\venv\Scripts\Activate.ps1
```

### Port already in use?
- Python (3000): Check for other Python processes, or change `PORT` in environment.

## Files

- `server.py` - Flask app entrypoint and API endpoints
- `services/analytics_insights.py` - Standalone Python AI module (reference)
- `requirements.txt` - Python dependencies
- `controllers/analytics_controller.py` - Python analytics endpoint logic
