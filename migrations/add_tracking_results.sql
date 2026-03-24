-- Migration: Add tracking_results table for Multi-Layer CCTV Tracking System
USE missing_persons_db;

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
    INDEX idx_session_id (session_id),
    INDEX idx_case_id (case_id)
);
