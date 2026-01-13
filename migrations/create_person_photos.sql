CREATE TABLE IF NOT EXISTS person_photos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    missing_person_id INT NOT NULL,
    photo_path VARCHAR(255) NOT NULL,
    face_encoding LONGBLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (missing_person_id) REFERENCES missing_persons(id) ON DELETE CASCADE
);