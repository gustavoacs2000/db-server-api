# RPA DB Server API 🤖💻

An advanced, all-in-one Robotic Process Automation (RPA) Server API built with **Python** and **FastAPI**. 

This project is designed to be a central orchestrator for automated tasks, offering a comprehensive suite of tools via HTTP endpoints. From browser automation and isolated Python script execution to real-time screen streaming and database management, it provides everything needed to build, manage, and scale complex automation workflows.

---

## 🚀 Key Features

* **🌐 Web Browser Automation (Playwright)**
  * Full programmatic control over Chrome/Chromium.
  * Execute JavaScript, take screenshots, generate PDFs.
  * Manage multiple tabs, downloads, and special contexts (Kiosk, Incognito).
* **🗄️ Database Management**
  * Built-in support for **MariaDB** and **SQLite**.
  * Complete CRUD capabilities with flexible SQL query execution and JSON responses.
* **🐍 Isolated Python Execution**
  * Safely execute Python code dynamically via API requests.
  * Support for both synchronous and asynchronous code blocks with context isolation.
* **⏰ Task Scheduler**
  * Advanced scheduling system using CRON, interval, or date-based triggers.
  * Execute predefined scripts and manage background jobs remotely.
* **🔍 OCR & Document Processing**
  * Optical Character Recognition using **Tesseract**.
  * Extract text from images and PDF files seamlessly.
* **📹 Real-Time Screen Streaming**
  * Live desktop screen broadcasting with adjustable FPS and resolution scaling.
  * Integrated web interface for remote monitoring.
* **🔤 Advanced Regex Processing**
  * Extract structured data from large text files or streams in batches.
* **📋 Comprehensive Logging & Auditing**
  * Advanced logging system filtering by date, status, and text patterns.
  * Distinct tracking for incoming requests and system errors.

---

## 🛠️ Technology Stack

* **Core Backend:** Python 3.11+, FastAPI, Uvicorn
* **Automation:** Playwright, PyAutoGUI
* **Database:** SQLAlchemy, aiosqlite, MariaDB connector
* **Scheduling:** APScheduler
* **Image/OCR:** OpenCV, PyMuPDF, Pillow, pdf2image, PyTesseract
* **Screen Capture:** MSS

---

## ⚙️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/gustavoacs2000/db-server-api.git
   cd db-server-api
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/Mac:
   source venv/bin/activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: For OCR capabilities, ensure you have the Tesseract-OCR binary installed on your system).*

4. **Run the server:**
   ```bash
   python src/main.py
   ```
   The API will start on an automatically assigned free port. You will see a green 🟢 indicator in the console with the local URLs.

---

## 📖 API Documentation
Once the server is running, navigate to the `/docs` endpoint (e.g., `http://127.0.0.1:<port>/docs`) to view the interactive **Swagger UI**. 

This interface allows developers to explore all available routes, view required payloads, and test endpoints directly from the browser. All routes (except stream endpoints) are secured and require a Bearer token.

---

## 💼 Why this project stands out (For Recruiters)
This project demonstrates proficiency in building **scalable backend architectures** and working with **complex system integrations**:
- **API Design**: Adheres to RESTful principles using FastAPI, including dependency injection, middleware security, and OpenAPI documentation.
- **Multithreading & Async**: Leverages Python's `asyncio` for high-concurrency browser actions and database requests.
- **System Resource Management**: Manages isolated contexts, background schedulers, and memory-intensive operations (like OCR and streaming).
- **Problem Solving**: Combines various specialized domains (computer vision, web scraping, data parsing, process automation) into a single, cohesive microservice.