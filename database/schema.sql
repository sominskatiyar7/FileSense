-- FileSense database schema. Safe to run more than once (IF NOT EXISTS everywhere).
-- Run in MySQL Workbench or:  mysql -u root -p < database/schema.sql

CREATE DATABASE IF NOT EXISTS filesense_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE filesense_db;

-- TABLE 1: one row per scanning session
CREATE TABLE IF NOT EXISTS scan_sessions (
    scan_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    root_path         VARCHAR(1024)   NOT NULL,
    started_at        DATETIME        DEFAULT CURRENT_TIMESTAMP,
    completed_at      DATETIME        NULL,
    status            ENUM('RUNNING','COMPLETED','CANCELLED','FAILED') NOT NULL DEFAULT 'RUNNING',
    total_files       INT UNSIGNED    DEFAULT 0,
    total_bytes       BIGINT UNSIGNED DEFAULT 0,
    duplicate_groups  INT UNSIGNED    DEFAULT 0,
    duplicate_files   INT UNSIGNED    DEFAULT 0,
    reclaimable_bytes BIGINT UNSIGNED DEFAULT 0,
    error_count       INT UNSIGNED    DEFAULT 0,
    PRIMARY KEY (scan_id)
) ENGINE=InnoDB;

-- TABLE 2: metadata of every file seen in a scan (never the file contents)
CREATE TABLE IF NOT EXISTS scanned_files (
    file_id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    scan_id        BIGINT UNSIGNED NOT NULL,
    absolute_path  VARCHAR(1024)   NOT NULL,
    file_name      VARCHAR(255)    NOT NULL,
    extension      VARCHAR(20)     DEFAULT '',
    size_bytes     BIGINT UNSIGNED NOT NULL,
    modified_at    DATETIME        NULL,
    sha256         CHAR(64)        NULL,
    scan_status    ENUM('OK','UNREADABLE','CHANGED','SKIPPED') NOT NULL DEFAULT 'OK',
    PRIMARY KEY (file_id),
    INDEX idx_scan_size (scan_id, size_bytes),
    INDEX idx_scan_sha  (scan_id, sha256),
    CONSTRAINT fk_files_scan FOREIGN KEY (scan_id) REFERENCES scan_sessions(scan_id)
) ENGINE=InnoDB;

-- TABLE 3: history of ORGANIZE / QUARANTINE / RESTORE operations
CREATE TABLE IF NOT EXISTS file_operations (
    operation_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    scan_id          BIGINT UNSIGNED NOT NULL,
    file_id          BIGINT UNSIGNED NULL,
    operation_type   ENUM('ORGANIZE','QUARANTINE','RESTORE') NOT NULL,
    source_path      VARCHAR(1024)   NOT NULL,
    destination_path VARCHAR(1024)   NOT NULL,
    status           ENUM('PENDING','SUCCESS','FAILED','ROLLED_BACK') NOT NULL DEFAULT 'PENDING',
    operation_at     DATETIME        DEFAULT CURRENT_TIMESTAMP,
    error_message    TEXT            NULL,
    PRIMARY KEY (operation_id),
    CONSTRAINT fk_ops_scan FOREIGN KEY (scan_id) REFERENCES scan_sessions(scan_id),
    CONSTRAINT fk_ops_file FOREIGN KEY (file_id) REFERENCES scanned_files(file_id)
        ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Reference: the main queries used by database/repository.py (parameterized,
-- %s is a placeholder filled in safely by mysql-connector).
-- ---------------------------------------------------------------------------
-- Insert a scan:        INSERT INTO scan_sessions (root_path, status) VALUES (%s, 'RUNNING');
-- Insert files:         INSERT INTO scanned_files (scan_id, absolute_path, file_name, extension,
--                           size_bytes, modified_at, sha256, scan_status) VALUES (%s,...);
-- Update scan stats:    UPDATE scan_sessions SET status=%s, completed_at=NOW(), total_files=%s, ... WHERE scan_id=%s;
-- Insert operation:     INSERT INTO file_operations (scan_id, file_id, operation_type, source_path,
--                           destination_path, status) VALUES (%s,%s,%s,%s,%s,'PENDING');
-- Update op status:     UPDATE file_operations SET status=%s, error_message=%s WHERE operation_id=%s;
-- Scan history:         SELECT * FROM scan_sessions ORDER BY scan_id DESC LIMIT %s;
-- Duplicate groups:     SELECT size_bytes, sha256, COUNT(*) AS copies,
--                           SUM(size_bytes) - MAX(size_bytes) AS reclaimable_bytes
--                       FROM scanned_files
--                       WHERE scan_id=%s AND sha256 IS NOT NULL AND scan_status='OK'
--                       GROUP BY size_bytes, sha256 HAVING COUNT(*) > 1;
-- Quarantined files:    SELECT * FROM file_operations q WHERE operation_type='QUARANTINE'
--                       AND status='SUCCESS' AND NOT EXISTS (a later successful RESTORE of the same path);
-- Analytics:            SELECT operation_type, status, COUNT(*) FROM file_operations GROUP BY 1,2;
