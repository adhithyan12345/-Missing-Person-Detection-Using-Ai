# FindHope - AI Missing Person Detection

A web application to report and find missing persons using AI-powered face recognition.

## Tech Stack
- **Backend**: Python Flask
- **Database**: MySQL
- **AI/ML**: `face_recognition` (dlib), OpenCV
- **Frontend**: HTML5, Tailwind CSS

## Prerequisites
1. **Python 3.8+**
2. **MySQL Server** installed and running.
3. **C++ Build Tools** (Required for `dlib` on Windows).
   - Download "Visual Studio Build Tools".
   - Select "Desktop development with C++".

## Setup Instructions

### 1. Database Setup
1. Open your MySQL Client (Workbench or Command Line).
2. Create the database and tables using the provided schema:
   ```sql
   source schema.sql;
   ```
   (Or copy-paste the contents of `schema.sql` into your query window).

### 2. Configuration
1. Open `config.py`.
2. Update the MySQL credentials if they differ from the defaults:
   ```python
   MYSQL_USER = 'root'
   MYSQL_PASSWORD = 'your_password'
   ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```
*Note: If `dlib` fails to install, ensure you have CMake and C++ Build Tools installed.*

### 4. Run the Application
```bash
python app.py
```
The application will start at `http://127.0.0.1:5000`.

## Usage
1. **Report**: Go to "Report Missing" to add a person to the database. Upload a clear photo.
2. **Search**: Go to "Search" and upload a photo of a person you want to check.
3. **Results**: The AI will compare the facial encoding and return the best match if the confidence is high enough.

ip camera:http:/your ip address/video


