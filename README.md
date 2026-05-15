# DataLens — Data Analytics Platform

A full-stack analytics dashboard for SQL Server. Connect to any SQL Server database, select a table, and instantly generate charts and statistics.

---

## 🗂 Folder Structure

```
analytics-platform/
├── config/
│   └── authMiddleware.js     ← Checks JWT token on protected routes
├── controllers/
│   ├── authController.js     ← Register / Login logic
│   ├── dbController.js       ← SQL Server connection & table listing
│   └── analyticsController.js← Fetches stats and chart data
├── frontend/
│   ├── index.html            ← Main HTML page
│   ├── style.css             ← All styles
│   └── app.js                ← All frontend JavaScript
├── routes/
│   ├── authRoutes.js         ← /api/auth/* endpoints
│   ├── dbRoutes.js           ← /api/db/* endpoints
│   └── analyticsRoutes.js    ← /api/analytics/* endpoints
├── utils/
│   ├── userStore.js          ← In-memory user storage
│   ├── jwtUtils.js           ← JWT sign/verify helpers
│   └── tableFilter.js        ← Hides sensitive tables
├── .env                      ← Environment config (DO NOT commit this)
├── package.json
└── server.js                 ← App entry point
```

---

## ⚡ Setup (Step-by-Step for Beginners)

### 1. Install Node.js
Download and install from: https://nodejs.org (choose LTS version)

### 2. Open a Terminal / Command Prompt
Navigate to the project folder:
```bash
cd path/to/analytics-platform
```

### 3. Install Dependencies
```bash
npm install
```
This downloads all required packages listed in `package.json`.

### 4. Configure Environment
Open the `.env` file and change `JWT_SECRET` to any long random string:
```
JWT_SECRET=MySuper$ecretKey12345!ChangeMeNow
PORT=3000
```
You do NOT need to fill in the DB_ variables — users enter connection details in the UI.

### 5. Start the Server
```bash
npm start
```
You should see:
```
🚀 Analytics Platform running at http://localhost:3000
```

### 5b. Run as a Desktop App
If you want it to behave more like a downloadable desktop app, use Electron:
```bash
npm install
npm run desktop
```
This opens the application in a desktop window on your PC or laptop.

### 5c. Build a Downloadable Installer
To package the app for Windows so others can download and install it, run:
```bash
npm install
npm run dist
```
The packaged installer will be created in the `dist/` folder.

### Download DataLens Installer
After running the build, locate the generated Windows installer in the `dist/` folder. It should be named like `DataLens-1.0.0-x64.exe`.

If you publish a release to GitHub, you can also upload the generated installer under the repository Releases page so users can download it directly.

### 6. Open in Browser
Go to: **http://localhost:3000**

---

## 🔐 How to Use

1. **Register** a new account on the Sign In page
2. Click **Connect**, enter your SQL Server details:
   - Server: your SQL Server hostname or IP (e.g. `localhost`, `192.168.1.10`)
   - Port: usually `1433`
   - Database: name of the database to explore
   - Username / Password: your SQL Server credentials
   - Check **Trust Server Certificate** if using a local/dev server
3. Click **Connect & Fetch Tables**
4. Click any table name to **generate its dashboard**
5. Switch to **Data Table** to preview raw rows

---

## 🔒 Security Features

| Feature | How it works |
|---|---|
| Password hashing | `bcryptjs` with 12 salt rounds |
| Authentication | JWT tokens (8-hour expiry) |
| Sensitive table hiding | Tables with names containing `user`, `password`, `auth`, `token`, etc. are automatically hidden |
| Input validation | Table names are checked before any SQL query |
| Parameterized queries | All user inputs use `mssql` parameterized queries |

---

## 🚀 Development Mode (Auto-Restart)

```bash
npm run dev
```
Uses `nodemon` to restart the server automatically when you save changes.

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, Bootstrap 5, Chart.js 4 |
| Backend | Node.js, Express.js |
| Database | SQL Server (via `mssql` package) |
| Auth | bcryptjs + JWT |
| Fonts | Syne + DM Mono (Google Fonts) |

---

## 🔧 Troubleshooting

**"Connection failed"** — Check your server IP, port, username, and password. Make sure SQL Server allows remote connections and TCP/IP is enabled in SQL Server Configuration Manager.

**"No tables found"** — Your user may not have SELECT permission on any tables, or all tables have sensitive names.

**Port already in use** — Change `PORT=3001` in `.env`.

**npm not found** — Node.js is not installed or not in your PATH. Reinstall from nodejs.org.
