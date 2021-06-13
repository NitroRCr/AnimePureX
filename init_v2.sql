CREATE TABLE illusts IF NOT EXISTS (
    id INT PRIMARY KEY AUTO_INCREAMENT,
    type INT NOT NULL,
    type_id INT NOT NULL,
    title VARCHAR(64) NOT NULL,
    tags TEXT
    image_urls TEXT NOT NULL,
    width INT,
    height INT,
    views_count INT,
    likes_count INT,
    age_limit INT NOT NULL,
    published_time CHAR(19) NOT NULL,
    user INT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE users IF NOT EXISTS (
    id INT PRIMARY KEY AUTO_INCREAMENT,
    type INT NOT NULL,
    type_id INT NOT NULL,
    name VARCHAR(32) NOT NULL,
    intro TEXT,
    gender INT,
    works INT,
    raw_json TEXT NOT NULL
);
