
DROP DATABASE IF EXISTS missing_persons_db;


CREATE DATABASE IF NOT EXISTS missing_persons_db;


USE missing_persons_db;



CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    phone VARCHAR(20),
    location VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS missing_persons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id VARCHAR(50) UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    age INT,
    gender VARCHAR(50),
    last_seen_date DATE,
    last_seen_location VARCHAR(255),
    latitude FLOAT, 
    longitude FLOAT, 
    description TEXT,
    contact_phone VARCHAR(50),
    photo_path VARCHAR(255), 
    face_encoding LONGBLOB, 
    status VARCHAR(50) DEFAULT 'Missing',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS person_photos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    missing_person_id INT NOT NULL,
    photo_path VARCHAR(255) NOT NULL,
    face_encoding LONGBLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (missing_person_id) REFERENCES missing_persons(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS case_updates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    missing_person_id INT NOT NULL,
    update_type VARCHAR(100), 
    details TEXT,
    source VARCHAR(255),
    location VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (missing_person_id) REFERENCES missing_persons(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS detection_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    person_id INT NOT NULL,
    camera_source VARCHAR(255),
    location VARCHAR(255),
    latitude FLOAT,
    longitude FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_id) REFERENCES missing_persons(id) ON DELETE CASCADE
);

-- Multi-Layer CCTV Tracking Results
CREATE TABLE IF NOT EXISTS tracking_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    case_id INT NULL,
    layer_number INT NOT NULL,
    camera_name VARCHAR(255),
    timestamp_found VARCHAR(20),
    confidence FLOAT,
    video_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id)
);
